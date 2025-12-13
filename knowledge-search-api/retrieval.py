import os
import requests
import json
import psycopg2.extras
from collections import defaultdict
from typing import List, Dict, Literal, Optional, Tuple

from sentence_transformers import SentenceTransformer, CrossEncoder

from schemas import InternalChunk, Filters
from clients import PostgreSQLClient, Neo4jClient
import re

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# --- Вспомогательные функции ---

def _build_filter_clause(filters: Optional[Filters], doc_ids: Optional[List[str]] = None) -> Tuple[str, list]:
    clauses = []
    params = []

    if doc_ids:
        clauses.append("c.doc_id = ANY(%s)")
        params.append(doc_ids)
        
    if filters:
        if filters.author:
            clauses.append("d.author ILIKE ANY(%s)")
            params.append(tuple(filters.author))

        if filters.date_from:
            clauses.append("d.uploaded_at >= %s")
            params.append(filters.date_from)
        if filters.date_to:
            clauses.append("d.uploaded_at <= %s")
            params.append(filters.date_to)

        if filters.doc_type:
            doc_type_clauses = [f"d.filename ILIKE %s" for _ in filters.doc_type]
            clauses.append("(" + " OR ".join(doc_type_clauses) + ")")
            params.extend([f"%.{dt.lstrip('.')}" for dt in filters.doc_type])
            
        if filters.space:
            clauses.append("c.block_type = ANY(%s)")
            params.append(tuple(filters.space))
    
    if not clauses:
        return "", []
    
    return "WHERE " + " AND ".join(clauses), params

def _rerank_results(reranker_model: Optional[CrossEncoder], query: str, chunks: List[InternalChunk], top_k: int) -> List[InternalChunk]:
    if not chunks:
        return []
    if not reranker_model:
        return sorted(chunks, key=lambda c: c.score, reverse=True)[:top_k]

    print(f"Reranking: Переранжирование {len(chunks)} кандидатов...")
    pairs = [[query, chunk.text] for chunk in chunks]
    scores = reranker_model.predict(pairs, show_progress_bar=False)
    
    for chunk, score in zip(chunks, scores):
        chunk.score = float(score)
        
    return sorted(chunks, key=lambda c: c.score, reverse=True)[:top_k]

def _find_and_reconstruct_table(db_client: PostgreSQLClient, chunk: InternalChunk) -> str:
    sql = "SELECT text, type FROM chunks WHERE doc_id = %s AND section = %s AND (type LIKE 'table%%' OR block_type LIKE 'table%%') ORDER BY chunk_id;"
    
    with db_client.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, (chunk.doc_id, chunk.section))
        rows = cur.fetchall()
        if not rows: return chunk.text

        if all(r['type'] == 'table_row' for r in rows):
            try:
                headers = [item.split(':')[0].strip() for item in rows[0]['text'].split(', ')]
                md_table = "| " + " | ".join(headers) + " |\n"
                md_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in rows:
                    values = [item.split(':', 1)[1].strip() for item in row['text'].split(', ')]
                    md_table += "| " + " | ".join(values) + " |\n"
                return md_table
            except IndexError:
                return "\n".join([row['text'] for row in rows])
        else:
            return "\n".join([row['text'] for row in rows])

def _post_process_chunks(db_client: PostgreSQLClient, chunks: List[InternalChunk]) -> List[InternalChunk]:
    final_blocks = []
    processed_objects = set()

    for chunk in chunks:
        is_table_fragment = chunk.type in ['table_part', 'table_row', 'table_cell']
        if is_table_fragment:
            table_key = (chunk.doc_id, chunk.section)
            if table_key not in processed_objects:
                full_table_text = _find_and_reconstruct_table(db_client, chunk)
                chunk.text = f"[Из таблицы '{chunk.section}']:\n{full_table_text}"
                chunk.block_type = "reconstructed_table"
                final_blocks.append(chunk)
                processed_objects.add(table_key)
        else:
            final_blocks.append(chunk)
            
    return final_blocks

# --- Основные методы поиска (Retrieval) ---

def retrieve_dense(db_client: PostgreSQLClient, embedding_model: SentenceTransformer, query: str, top_k: int, filters: Optional[Filters], allowed_doc_ids: Optional[List[str]]) -> List[InternalChunk]:
    query_embedding = embedding_model.encode(query)
    filter_clause, params = _build_filter_clause(filters, allowed_doc_ids)
    
    sql_query = f"""
        SELECT c.doc_id, c.chunk_id, c.text, d.filename, c.metadata, c.type, c.block_type,
               1 - (c.embedding::vector <=> %s::vector) AS score
        FROM chunks c JOIN documents d ON c.doc_id = d.doc_id
        {filter_clause} ORDER BY score DESC LIMIT %s;
    """
    
    results = []
    with db_client.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql_query, params + [query_embedding.tolist(), top_k])
        rows = cur.fetchall()
        for row in rows:
            results.append(InternalChunk(source_id=-1, **row))
    return results

def retrieve_bm25(db_client: PostgreSQLClient, query: str, top_k: int, filters: Optional[Filters], allowed_doc_ids: Optional[List[str]]) -> List[InternalChunk]:
    # --- НОВАЯ ЛОГИКА ОЧИСТКИ ---
    # 1. Оставляем только буквы, цифры и пробелы
    clean_query = re.sub(r'[^\w\s]', '', query)
    # 2. Разбиваем на слова и отбрасываем пустые
    words = [word for word in clean_query.strip().split() if word]
    # 3. Объединяем через '&' для tsquery
    ts_query = " & ".join(words)

    if not ts_query: # Если после очистки ничего не осталось
        print("BM25 search skipped: query is empty after cleaning.")
        return []
    # ---------------------------
    filter_clause, params = _build_filter_clause(filters, allowed_doc_ids)
    where_conjunction = "AND" if filter_clause else "WHERE"
    
    sql_query = f"""
        SELECT c.doc_id, c.chunk_id, c.text, d.filename, c.metadata, c.type, c.block_type,
               ts_rank(c.text_tsv, to_tsquery('russian', %s)) as score
        FROM chunks c JOIN documents d ON c.doc_id = d.doc_id
        {filter_clause} {where_conjunction} c.text_tsv @@ to_tsquery('russian', %s)
        ORDER BY score DESC LIMIT %s;
    """
    
    results = []
    with db_client.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql_query, params + [ts_query, ts_query, top_k])
        rows = cur.fetchall()
        for row in rows:
            results.append(InternalChunk(source_id=-1, **row))
    return results

def retrieve_hybrid(db_client: PostgreSQLClient, embedding_model: SentenceTransformer, query: str, top_k: int, filters: Optional[Filters], allowed_doc_ids: Optional[List[str]]) -> List[InternalChunk]:
    dense_results = retrieve_dense(db_client, embedding_model, query, top_k, filters, allowed_doc_ids)
    bm25_results = retrieve_bm25(db_client, query, top_k, filters, allowed_doc_ids)

    k = 60
    rrf_scores = defaultdict(float)
    
    for rank, chunk in enumerate(dense_results):
        rrf_scores[(chunk.doc_id, chunk.chunk_id)] += 1 / (k + rank + 1)

    for rank, chunk in enumerate(bm25_results):
        rrf_scores[(chunk.doc_id, chunk.chunk_id)] += 1 / (k + rank + 1)
        
    all_chunks = { (c.doc_id, c.chunk_id): c for c in dense_results + bm25_results }
    sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    
    candidates = [all_chunks[cid] for cid in sorted_chunk_ids]
    for c in candidates:
        c.score = rrf_scores.get((c.doc_id, c.chunk_id), 0.0)
        
    return candidates

# --- "Фасадная" функция для текстового поиска ---
SearchMode = Literal["dense", "bm25", "hybrid"]

def retrieve(
    mode: SearchMode,
    db_client: PostgreSQLClient,
    embedding_model: SentenceTransformer,
    reranker_model: Optional[CrossEncoder],
    query: str,
    top_k: int,
    filters: Optional[Filters]
) -> List[InternalChunk]:
    
    # Пре-фильтрация по метаданным документов
    allowed_doc_ids = None
    if filters and (filters.author or filters.date_from or filters.date_to):
        doc_filters_only = Filters(author=filters.author, date_from=filters.date_from, date_to=filters.date_to)
        doc_filter_clause, doc_params = _build_filter_clause(doc_filters_only)
        doc_filter_clause = doc_filter_clause.replace("d.", "")
        
        with db_client.get_cursor() as cur:
            cur.execute(f"SELECT doc_id FROM documents {doc_filter_clause}", doc_params)
            allowed_doc_ids = [row[0] for row in cur.fetchall()]
            if not allowed_doc_ids: return []

    candidate_k = top_k * 5 if reranker_model else top_k
    chunk_filters = Filters(doc_type=filters.doc_type if filters else None, space=filters.space if filters else None)
    
    candidates: List[InternalChunk] = []
    if mode == "dense":
        candidates = retrieve_dense(db_client, embedding_model, query, candidate_k, chunk_filters, allowed_doc_ids)
    elif mode == "bm25":
        candidates = retrieve_bm25(db_client, query, candidate_k, chunk_filters, allowed_doc_ids)
    elif mode == "hybrid":
        candidates = retrieve_hybrid(db_client, embedding_model, query, candidate_k, chunk_filters, allowed_doc_ids)
    else:
        raise ValueError(f"Неизвестный режим поиска: {mode}")

    reranked_chunks = _rerank_results(reranker_model, query, candidates, top_k)
    reconstructed_chunks = _post_process_chunks(db_client, reranked_chunks)
        
    for i, chunk in enumerate(reconstructed_chunks):
        chunk.source_id = i + 1
        
    return reconstructed_chunks

# --- Логика для графа знаний ---
def _extract_entities_from_query(query: str) -> List[str]:
    system_prompt = "You are an API for named entity recognition. Your only output is a JSON array of strings."
    user_prompt = f"""
    Extract key entities (people, organizations, concepts, regulations) from the user query.
    Return only a JSON array of strings. If no entities are found, return an empty array [].

    Query: "{query}"
    """
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "system": system_prompt, "prompt": user_prompt,
            "stream": False, "format": "json", "options": {"temperature": 0.0}
        }, timeout=60)
        response.raise_for_status()
        entities = json.loads(response.json().get("response", "[]"))
        return [str(e) for e in entities if isinstance(e, str)]
    except Exception as e:
        print(f"Graph Entity Extraction Error: {e}")
        return []

def retrieve_graph(neo4j_client: Neo4jClient, query: str, graph_depth: int) -> str:
    print(f"Выполняется graph поиск для запроса: '{query[:50]}...'")
    if not neo4j_client or not neo4j_client.driver:
        return ""

    entities = _extract_entities_from_query(query)
    if not entities:
        return ""

    print(f"Найденные сущности для графа: {entities}")
    
    cypher_query = f"""
        MATCH (e:Entity)
        WHERE e.name IN $entities
        MATCH path = (e)-[*1..{graph_depth}]-(related)
        UNWIND relationships(path) as r
        RETURN DISTINCT r
    """
    
    verbalized_context = set()
    with neo4j_client.driver.session() as session:
        result = session.run(cypher_query, entities=entities)
        for record in result:
            rel = record["r"]
            start_node = rel.start_node
            end_node = rel.end_node
            relation_type = rel.get("type", "RELATED_TO")
            verbalized_context.add(f"{start_node['name']} -> [{relation_type}] -> {end_node['name']}")
            
    return "\n".join(sorted(list(verbalized_context)))