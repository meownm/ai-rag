import os
import json
import time
import uvicorn
import torch
import re
from fastapi import Depends, FastAPI, Request, Response, status as http_status, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Generator, List
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, CrossEncoder

# --- Локальные модули ---
from schemas import (
    AnswerRequest, AnswerResponse, HISTORY_TABLES_DDL,
    InternalChunk, HighlightedCitation, StreamTextChunk, StreamMetadataChunk,
    ConversationInfo, FullHistoryResponse, TokenIdentity
)
from clients import PostgreSQLClient, Neo4jClient, load_embedding_model
from retrieval import retrieve, retrieve_graph
from context_builder import build_context
from llm_provider import generate_answer, generate_answer_stream
from history import (
    get_or_create_conversation, get_conversation_history, save_search_result,
    get_history_list_for_user, get_full_history_by_query_id
)
from highlighter import verify_and_highlight_citations
from health_services import check_postgresql, check_neo4j, check_ollama
from auth import get_token_identity

load_dotenv()

# --- Управление жизненным циклом приложения ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     Событие 'startup': инициализация ресурсов...")
    
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    print(f"INFO:     Выбрано устройство для моделей: {device}")
    
    db_params = {
        "host": os.getenv("DB_HOST"), "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("DB_NAME"), "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD")
    }
    app.state.db_client = PostgreSQLClient(db_params)
    
    app.state.neo4j_client = None
    if os.getenv("NEO4J_ENABLED", "false").lower() == 'true':
        app.state.neo4j_client = Neo4jClient(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD")
        )
        if app.state.neo4j_client.driver is None:
            app.state.neo4j_client = None
    
    app.state.embedding_model = load_embedding_model(
        os.getenv("EMBEDDING_MODEL_NAME"), device=device
    )

    app.state.reranker_model = None
    if os.getenv("RERANKER_ENABLED", "false").lower() == 'true':
        reranker_name = os.getenv("RERANKER_MODEL_NAME")
        print(f"INFO:     Загрузка реранкер-модели: {reranker_name} на устройство '{device}'...")
        app.state.reranker_model = CrossEncoder(reranker_name, device=device)
        print("INFO:     Реранкер-модель успешно загружена.")
    
    with app.state.db_client.get_cursor() as cur:
        cur.execute(HISTORY_TABLES_DDL)
    print("INFO:     Таблицы истории поиска проверены/созданы.")
    
    print("INFO:     Все ресурсы успешно инициализированы.")
    
    yield
    
    print("INFO:     Событие 'shutdown': закрытие ресурсов...")
    if hasattr(app.state, 'neo4j_client') and app.state.neo4j_client:
        app.state.neo4j_client.close()
    if hasattr(app.state, 'db_client') and app.state.db_client:
        app.state.db_client.close()
    print("INFO:     Все ресурсы успешно освобождены.")

app = FastAPI(
    title="Knowledge Search API",
    description="API для интеллектуального поиска по базе знаний.",
    version="1.7.0", # Обновляем версию
    lifespan=lifespan
)

# --- Настройка CORS Middleware ---
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if not allowed_origins:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Вспомогательная функция ---
def _filter_used_citations(answer_text: str, all_citations: List[HighlightedCitation]) -> List[HighlightedCitation]:
    """Фильтрует список цитат, оставляя только те, на которые есть ссылки в тексте ответа."""
    used_ids = set()
    matches = re.findall(r'\[(\d+(?:,\s*\d+)*)\]', answer_text)
    for match in matches:
        ids = [int(sid.strip()) for sid in match.split(',')]
        used_ids.update(ids)
    return sorted([c for c in all_citations if c.source_id in used_ids], key=lambda c: c.source_id)


def _build_citation_fallback(retrieved_chunks: List[InternalChunk]) -> tuple[str, List[HighlightedCitation]]:
    """Возвращает безопасный fallback-ответ и список цитат, если Ollama/LLM недоступен."""
    fallback_answer = "Не удалось сгенерировать сводный ответ, но вот наиболее релевантные фрагменты:\n\n"
    citations_for_response = [
        HighlightedCitation(highlighted_text=chunk.text, **chunk.dict(exclude={"metadata"}))
        for chunk in retrieved_chunks
    ]
    for citation in citations_for_response:
        fallback_answer += f"**[Источник {citation.source_id}: {citation.filename}]**\n{citation.highlighted_text}\n\n"
    return fallback_answer, citations_for_response

# --- Эндпоинты API ---

@app.post("/v1/answer", tags=["Search"])
async def get_answer(req: AnswerRequest, request: Request, identity: TokenIdentity = Depends(get_token_identity)):
    start_time = time.time()
    
    db_client = request.app.state.db_client
    neo4j_client = request.app.state.neo4j_client
    embedding_model = request.app.state.embedding_model
    reranker_model = request.app.state.reranker_model
    
    conv_id = get_or_create_conversation(
        db_client,
        req.conversation_id,
        user_id=identity.user_id,
        org_id=identity.org_id,
        first_query=req.query,
    )
    conversation_history = get_conversation_history(db_client, conv_id)

    graph_context_str, graph_status = "", "disabled"
    if "graph" in req.mode:
        if neo4j_client:
            graph_context_str = retrieve_graph(neo4j_client, req.query, req.graph_depth)
            graph_status = "ok" if graph_context_str else "empty"
        else:
            graph_status = "unavailable"

    retrieved_chunks: List[InternalChunk] = []
    text_search_mode = req.mode.replace("+graph", "")
    if text_search_mode in ["dense", "bm25", "hybrid"]:
        retrieved_chunks = retrieve(
            mode=text_search_mode, db_client=db_client, embedding_model=embedding_model,
            reranker_model=reranker_model, query=req.query, top_k=req.top_k, filters=req.filters
        )

    if not retrieved_chunks and not graph_context_str:
        final_answer = "К сожалению, в базе знаний не найдено релевантной информации по вашему запросу."
        latency = int((time.time() - start_time) * 1000)
        response_data = AnswerResponse(
            answer=final_answer, conversation_id=conv_id, citations=[], graph_status=graph_status,
            enrichment_used=False, used_chunks=0, used_tokens=0, latency_ms=latency
        )
        save_search_result(
            db_client,
            conv_id,
            req.query,
            response_data,
            [],
            success=False,
            user_id=identity.user_id,
            org_id=identity.org_id,
        )
        return response_data
        
    context_data = build_context(retrieved_chunks, conversation_history, graph_context_str)

    if req.stream:
        async def stream_generator():
            full_answer = ""
            stream_error = None
            citations_for_response: List[HighlightedCitation] = []

            try:
                for token in generate_answer_stream(
                    query=req.query, context=context_data["context_str"],
                    history_str=context_data["history_str"], max_tokens=req.max_tokens
                ):
                    full_answer += token
                    yield f"data: {StreamTextChunk(content=token).json()}\n\n"
            except Exception as exc:
                stream_error = exc
                print(f"Streaming generation failed, using fallback: {exc}")

            if stream_error or not full_answer.strip():
                full_answer, citations_for_response = _build_citation_fallback(retrieved_chunks)
                for chunk in full_answer.split("\n\n"):
                    if chunk.strip():
                        yield f"data: {StreamTextChunk(content=chunk + '\n\n').json()}\n\n"

            is_success = not stream_error and bool(full_answer.strip())
            verified_answer, all_highlighted = verify_and_highlight_citations(full_answer, retrieved_chunks, embedding_model) if is_success else (full_answer, citations_for_response)
            final_citations = citations_for_response if not is_success else _filter_used_citations(verified_answer, all_highlighted)
            latency = int((time.time() - start_time) * 1000)

            metadata_chunk = StreamMetadataChunk(
                conversation_id=conv_id, citations=final_citations,
                graph_context=[{"content": graph_context_str}] if graph_context_str else None,
                graph_status=graph_status, enrichment_used=context_data["enrichment_used"],
                used_chunks=context_data["used_chunks"], used_tokens=context_data["used_tokens"],
                latency_ms=latency
            )
            yield f"data: {metadata_chunk.json()}\n\n"

            final_response = AnswerResponse(answer=verified_answer or "Failed to generate stream.", **metadata_chunk.dict())
            history_citations_json = [c.dict() for c in final_citations]
            save_search_result(
                db_client,
                conv_id,
                req.query,
                final_response,
                history_citations_json,
                success=is_success,
                user_id=identity.user_id,
                org_id=identity.org_id,
            )

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    else:
        is_success = False
        generated_answer = generate_answer(
            query=req.query, context=context_data["context_str"],
            history_str=context_data["history_str"], max_tokens=req.max_tokens
        )

        if not generated_answer:
            final_answer, citations_for_response = _build_citation_fallback(retrieved_chunks)
            is_success = False
        else:
            final_answer, citations_for_response_all = verify_and_highlight_citations(generated_answer, retrieved_chunks, embedding_model)
            citations_for_response = _filter_used_citations(final_answer, citations_for_response_all)
            is_success = True
        
        latency = int((time.time() - start_time) * 1000)
        
        response = AnswerResponse(
            answer=final_answer, conversation_id=conv_id, citations=citations_for_response,
            graph_context=[{"content": graph_context_str}] if graph_context_str else None,
            graph_status=graph_status, enrichment_used=context_data["enrichment_used"],
            used_chunks=context_data["used_chunks"], used_tokens=context_data["used_tokens"],
            latency_ms=latency
        )
        
        history_citations_json = [c.dict() for c in citations_for_response]
        save_search_result(
            db_client,
            conv_id,
            req.query,
            response,
            history_citations_json,
            success=is_success,
            user_id=identity.user_id,
            org_id=identity.org_id,
        )
        return response

@app.get("/health", tags=["Monitoring"])
def health_check(request: Request, response: Response):
    services_status = {
        "postgresql": check_postgresql(request.app.state.db_client),
        "neo4j": check_neo4j(request.app.state.neo4j_client),
        "ollama": check_ollama(),
    }
    
    overall_healthy = all(status["status"] in ["ok", "disabled"] for status in services_status.values())
    
    if not overall_healthy:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
        
    return services_status

@app.get("/v1/history", response_model=List[ConversationInfo], tags=["History"])
async def get_history_list(limit: int = 20, offset: int = 0, request: Request = None, identity: TokenIdentity = Depends(get_token_identity)):
    db_client = request.app.state.db_client
    history_data = get_history_list_for_user(db_client, identity.user_id, identity.org_id, limit, offset)
    return [
        ConversationInfo(
            conversation_id=str(row['conversation_id']), user_id=row['user_id'], org_id=row['org_id'],
            title=row['title'], created_at=row['created_at']
        ) for row in history_data
    ]

@app.get("/v1/history/{query_id}", response_model=FullHistoryResponse, tags=["History"])
async def get_history_details(query_id: int, request: Request = None, identity: TokenIdentity = Depends(get_token_identity)):
    db_client = request.app.state.db_client
    full_history = get_full_history_by_query_id(db_client, query_id, identity.user_id, identity.org_id)

    if not full_history:
        raise HTTPException(status_code=404, detail="Query ID not found")
        
    citations_data = full_history.get('citations') or []
    full_history['citations'] = [HighlightedCitation(**c) for c in citations_data]
    full_history['created_at'] = full_history['created_at']
    full_history['conversation_id'] = str(full_history['conversation_id'])
    
    return FullHistoryResponse(**full_history)

if __name__ == "__main__":
    print("INFO:     Запуск FastAPI сервиса...")
    uvicorn.run("main:app", host="0.0.0.0", port=8020, reload=True)
