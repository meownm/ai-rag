# src/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Union
import logging
import time
import uuid
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer
from .model_manager import model_manager, RAW_TRANSFORMERS_MODELS

# ... (Настройка FastAPI и Pydantic моделей остается прежней) ...
logger = logging.getLogger(__name__)
app = FastAPI(title="Сервис для создания эмбеддингов", description="Унифицированный сервис для получения эмбеддингов.", version="1.0.0")
class EmbeddingRequest(BaseModel):
    model: str = Field(..., description="Имя модели с Hugging Face")
    input: Union[str, List[str]] = Field(..., description="Текст или список текстов")
class EmbeddingData(BaseModel):
    object: str = "embedding"; embedding: List[float]; index: int
class Usage(BaseModel):
    prompt_tokens: int; total_tokens: int
class EmbeddingResponse(BaseModel):
    object: str = "list"; data: List[EmbeddingData]; model: str; usage: Usage

# --- НОВАЯ ХЕЛПЕР-ФУНКЦИЯ ДЛЯ ПУЛИНГА ---
def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
# ---------------------------------------------

@app.on_event("startup")
async def startup_event(): logger.info("[Startup] Приложение запускается..."); model_manager.start_cleanup_thread()
@app.on_event("shutdown")
async def shutdown_event(): logger.info("[Shutdown] Приложение останавливается..."); model_manager.stop_cleanup_thread()

@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest):
    request_id = str(uuid.uuid4())[:8]
    texts = [request.input] if isinstance(request.input, str) else request.input
    if not texts or not all(isinstance(t, str) for t in texts):
        raise HTTPException(status_code=400, detail="Input must be a non-empty string or a list of non-empty strings.")

    logger.info(f"[{request_id}] Получен запрос на эмбеддинги для модели '{request.model}' с {len(texts)} текстом(ами).")

    try:
        logger.info(f"[{request_id}] Запрос модели '{request.model}' из менеджера...")
        loaded_model = model_manager.get_model(request.model, request_id=request_id)
    except Exception as e:
        logger.error(f"[{request_id}] Не удалось загрузить или найти модель '{request.model}'.")
        raise HTTPException(status_code=404, detail=f"Model '{request.model}' not found or failed to load.")

    try:
        start_time = time.perf_counter()
        embeddings = []
        total_tokens = 0

        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: ВЫБИРАЕМ СПОСОБ СОЗДАНИЯ ЭМБЕДДИНГОВ ---
        if request.model in RAW_TRANSFORMERS_MODELS:
            logger.info(f"[{request_id}] Используем прямой путь 'transformers' для модели '{request.model}'.")
            model, tokenizer = loaded_model
            
            encoded_input = tokenizer(texts, padding=True, truncation=True, return_tensors='pt').to(model.device)
            with torch.no_grad():
                model_output = model(**encoded_input)
            
            sentence_embeddings = mean_pooling(model_output, encoded_input['attention_mask'])
            normalized_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)
            embeddings = normalized_embeddings.tolist()
            total_tokens = sum(len(tokenizer.encode(t, add_special_tokens=False)) for t in texts)
        else:
            logger.info(f"[{request_id}] Используем стандартный путь 'sentence-transformers' для модели '{request.model}'.")
            sbert_model: SentenceTransformer = loaded_model
            embeddings = sbert_model.encode(texts, normalize_embeddings=True).tolist()
            total_tokens = sum(len(sbert_model.tokenizer.encode(t, add_special_tokens=False)) for t in texts)
        # -----------------------------------------------------------------

        duration = time.perf_counter() - start_time
        logger.info(f"[{request_id}] Эмбеддинги созданы за {duration:.4f} секунд.")

        embedding_data = [EmbeddingData(embedding=emb, index=i) for i, emb in enumerate(embeddings)]
        response = EmbeddingResponse(
            data=embedding_data,
            model=request.model,
            usage=Usage(prompt_tokens=total_tokens, total_tokens=total_tokens)
        )
        logger.info(f"[{request_id}] Запрос успешно обработан. Отправлено {len(embeddings)} эмбеддингов.")
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Произошла внутренняя ошибка во время создания эмбеддингов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during embedding creation.")

@app.get("/health")
async def health_check(): return {"status": "ok"}