# worker.py
#
# Версия 3.13.1: Исправлена ошибка приведения типов в миграции. Улучшена обработка ошибок LLM.
# --------------------------------------------------------------------------

import time
import os
import logging
import re
import threading
import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import uuid
import gc

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from prometheus_client import Counter, Histogram
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import torch
from psycopg2.extras import DictCursor, execute_values


# Локальные модули
from clients import DatabaseClient, MinioClient, Neo4jClient
from parser_any import parse_any
from chunker import SmartChunker
from enrichment import extract_metadata_with_llm, extract_relations_with_llm

load_dotenv()

# --- Глобальные настройки из .env ---
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
ENRICHMENT_BATCH_SIZE = int(os.getenv("ENRICHMENT_BATCH_SIZE", "10"))
LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "2"))
EMBEDDING_API_TIMEOUT = int(os.getenv("EMBEDDING_API_TIMEOUT", "120"))

# --- Метрики Prometheus ---
METRICS = {
    "docs_processed_total": Counter("docs_processed_total", "Total documents processed (new versions)"),
    "docs_deprovisioned_total": Counter("docs_deprovisioned_total", "Total documents successfully deprovisioned"),
    "chunks_enriched_total": Counter("chunks_enriched_total", "Total chunks enriched by LLM", ["stage"]),
    "processing_errors_total": Counter("processing_errors_total", "Total errors during processing", ["worker_type", "stage"]),
    "doc_processing_duration_seconds": Histogram("doc_processing_duration_seconds", "Histogram of document processing time", ["operation"]),
}

# --- Логгинг-адаптер для добавления контекста ---
class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra_context = self.extra or {}
        context_str = " ".join(f"[{k}:{v}]" for k, v in extra_context.items() if v)
        return f"{context_str} {msg}", kwargs

def get_logger_adapter(base_logger, extra_context={}):
    return ContextLoggerAdapter(base_logger, extra_context)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def normalize_text_block(text: str) -> str:
    """Нормализует текстовый блок, извлеченный из PDF или OCR."""
    if not text: return ""
    text = re.sub(r'-\s*\n', '', text)
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = [p.replace('\n', ' ').strip() for p in paragraphs]
    return '\n\n'.join(p for p in cleaned_paragraphs if p)

def enrich_blocks_with_hierarchy(raw_blocks: List[Dict]) -> List[Dict]:
    current_headings = []
    for block in raw_blocks:
        block_level, block_type = block.get('level', 0), block.get('type', 'paragraph')
        if block_type == 'heading' and block_level > 0:
            while current_headings and current_headings[-1][0] >= block_level:
                current_headings.pop()
            current_headings.append((block_level, block['text']))
        if 'metadata' not in block: block['metadata'] = {}
        block['metadata']['context_path'] = [h[1] for h in current_headings]
    return raw_blocks

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _make_embedding_api_request(api_endpoint: str, payload: dict) -> requests.Response:
    """Делает запрос к API с повторными попытками."""
    headers = {"Content-Type": "application/json"}
    response = requests.post(api_endpoint, json=payload, timeout=EMBEDDING_API_TIMEOUT, headers=headers)
    response.raise_for_status()
    return response

def _generate_embeddings_api(texts: List[str], api_config: Dict, logger: logging.LoggerAdapter) -> List[list]:
    """Генерирует эмбеддинги, вызывая внешний API (OpenAI-совместимый или Ollama)."""
    api_base = api_config['api_base']
    model_name = api_config['model_name']
    generator = api_config.get('generator', 'service')

    if generator == 'ollama':
        endpoint = f"{api_base.rstrip('/')}/api/embeddings"
    else:
        endpoint = f"{api_base}/embeddings"

    all_embeddings = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch_texts = texts[i:i+EMBEDDING_BATCH_SIZE]

        try:
            if generator == 'ollama':
                logger.info(f"Отправка {len(batch_texts)} текстов в Ollama embeddings API...")
                for text in batch_texts:
                    payload = {"model": model_name, "prompt": text}
                    response = _make_embedding_api_request(endpoint, payload)
                    response_data = response.json()
                    embedding = response_data.get('embedding')
                    if not embedding:
                        raise RuntimeError("Ollama не вернул поле embedding")
                    all_embeddings.append(embedding)
            else:
                payload = {"model": model_name, "input": batch_texts}
                logger.info(f"Отправка батча из {len(batch_texts)} текстов в API эмбеддингов...")
                response = _make_embedding_api_request(endpoint, payload)
                response_data = response.json()

                batch_embeddings_sorted = sorted(response_data['data'], key=lambda e: e['index'])
                batch_embeddings = [item['embedding'] for item in batch_embeddings_sorted]
                all_embeddings.extend(batch_embeddings)

        except requests.exceptions.RequestException as e:
            logger.error(f"Сетевая ошибка при вызове API эмбеддингов: {e}", exc_info=True)
            raise RuntimeError(f"Failed to get embeddings from API: {e}")
        except Exception as e:
            logger.error(f"Ошибка при обработке ответа от API эмбеддингов: {e}", exc_info=True)
            raise RuntimeError(f"Error processing API response: {e}")

    return all_embeddings

def generate_embeddings(chunks: List[Dict], embed_model: Any, logger: logging.LoggerAdapter) -> None:
    texts_to_embed = [chunk['text'] for chunk in chunks if chunk.get('text')]
    if not texts_to_embed: return
    
    logger.info(f"Генерация векторов для {len(texts_to_embed)} блоков...")
    embeddings = []

    if isinstance(embed_model, SentenceTransformer):
        logger.info("Используется локальная модель SentenceTransformer.")
        original_device = embed_model.device
        try:
            embeddings = embed_model.encode(texts_to_embed, show_progress_bar=False, batch_size=EMBEDDING_BATCH_SIZE)
        except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
            if "out of memory" in str(e).lower():
                logger.warning("CUDA out of memory! Попытка обработки батча на CPU...")
                torch.cuda.empty_cache()
                embed_model.to('cpu')
                embeddings = embed_model.encode(texts_to_embed, show_progress_bar=False, batch_size=EMBEDDING_BATCH_SIZE)
            else:
                raise
        finally:
            embed_model.to(original_device)
            
    elif isinstance(embed_model, dict) and embed_model.get("mode") == "api":
        logger.info(f"Используется внешний API: {embed_model['api_base']}")
        embeddings = _generate_embeddings_api(texts_to_embed, embed_model, logger)
        
    else:
        raise TypeError(f"Неподдерживаемый тип генератора эмбеддингов: {type(embed_model)}")

    idx = 0
    for chunk in chunks:
        if chunk.get('text'):
            chunk['embedding'] = embeddings[idx]
            idx += 1

# --- ЛОГИКА ОБРАБОТКИ ФАЙЛА ---
def process_and_save_file(db: DatabaseClient, minio: MinioClient, neo4j: Optional[Neo4jClient], task: Dict, logger: logging.LoggerAdapter) -> str:
    """Парсит, чанкует и сохраняет текстовое содержимое документа БЕЗ эмбеддингов."""
    doc_id = str(task['item_uuid'])
    tenant_id = str(task['tenant_id'])
    filename = task['item_name']
    s3_path = task.get('s3_path')
    owner_user_id = str(task['user_id'])
    
    if not s3_path:
        raise ValueError("В задаче отсутствует обязательное поле 's3_path'.")

    if db.document_exists(doc_id):
        logger.warning(f"Документ с doc_id={doc_id} уже существует. Выполняется очистка перед повторной обработкой.")
        if neo4j and os.getenv("NEO4J_ENABLED", "false").lower() == 'true':
            try:
                neo4j.delete_by_doc_id(doc_id, tenant_id)
                logger.info(f"Предыдущие данные для doc_id={doc_id} удалены из Neo4j.")
            except Exception as e:
                raise RuntimeError(f"Не удалось очистить Neo4j для повторной обработки: {e}")
        db.delete_document_cascade(doc_id)
        logger.info(f"Предыдущие данные для doc_id={doc_id} удалены из PostgreSQL.")

    local_path = None
    try:
        local_path = minio.download_file_by_path(s3_path)
        raw_blocks, doc_properties = parse_any(local_path, doc_id)

        if raw_blocks and raw_blocks[0].get("type") == "error":
            raise RuntimeError(f"Ошибка парсинга: {raw_blocks[0]['text']}")

        normalized_blocks = []
        for block in raw_blocks:
            block_type = block.get('type', 'paragraph')
            if block_type in ['paragraph', 'heading', 'image_text', 'section', 'caption']:
                cleaned_text = normalize_text_block(block.get('text', ''))
                if cleaned_text:
                    block['text'] = cleaned_text
                    normalized_blocks.append(block)
            elif block.get('text', '').strip():
                normalized_blocks.append(block)
        
        if not normalized_blocks:
            file_size = doc_properties.get("size_bytes", 0)
            if file_size > 1024:
                raise RuntimeError(f"Парсер не извлек контент из непустого файла (размер: {file_size} байт).")
            else:
                return "Документ пуст, индексация не требуется."

        final_blocks = enrich_blocks_with_hierarchy(normalized_blocks)

        chunker_config = {
            'chunk_tokens': int(os.getenv('CHUNKER_CHUNK_TOKENS', 500)),
            'overlap_tokens': int(os.getenv('CHUNKER_OVERLAP_TOKENS', 80)),
            'section_limit': int(os.getenv('CHUNKER_SECTION_LIMIT', 2000)),
            'table_limit': int(os.getenv('CHUNKER_TABLE_LIMIT', 2000)),
            'list_limit': int(os.getenv('CHUNKER_LIST_LIMIT', 1500)),
            'doc_limit': int(os.getenv('CHUNKER_DOC_LIMIT', 3000)),
        }
        chunker = SmartChunker(**chunker_config)
        
        smart_chunker_input = [{"text": b['text'], "meta": {**b.get('metadata', {}), 'type': b.get('type', 'paragraph')}} for b in final_blocks]
        smart_chunks = chunker.split_document(smart_chunker_input)

        if not smart_chunks:
            return "Документ не содержит достаточно контента для создания чанков."

        final_chunks = [{'doc_id': doc_id, 'chunk_id': i + 1, 'tenant_id': tenant_id, 'text': sc['text'], 'metadata': sc.get('meta', {})} for i, sc in enumerate(smart_chunks)]
        
        db.create_document_and_chunks(
            doc_id=doc_id, tenant_id=tenant_id, owner_user_id=owner_user_id,
            filename=filename, doc_properties=doc_properties, chunks=final_chunks
        )
        
        return f"Успешно сохранен документ и {len(final_chunks)} чанков (без эмбеддингов)."

    finally:
        if local_path and os.path.exists(local_path): os.remove(local_path)

# --- ОСНОВНЫЕ ЦИКЛЫ ВОРКЕРОВ ---
def upload_worker_loop(stop_event: threading.Event, db: DatabaseClient, minio: MinioClient, neo4j: Optional[Neo4jClient]):
    base_logger = logging.getLogger(threading.current_thread().name)
    logger = get_logger_adapter(base_logger)
    logger.info("Upload Worker запущен.")
    while not stop_event.is_set():
        task = None
        try:
            task = db.find_next_task_by_operation('created')
            if not task:
                stop_event.wait(POLL_INTERVAL); continue
            
            log_context = {'task_id': task['id'], 'doc_id': task['item_uuid'], 'tenant_id': task['tenant_id']}
            task_logger = get_logger_adapter(base_logger, log_context)
            task_logger.info("Взята новая задача на обработку")
            db.update_task_status(task['id'], 'processing')

            with METRICS["doc_processing_duration_seconds"].labels(operation='upload').time():
                result_details = process_and_save_file(db, minio, neo4j, task, task_logger)

            db.update_task_status(task['id'], 'done', result_details)
            if "Успешно сохранен" in result_details:
                METRICS["docs_processed_total"].inc()
            task_logger.info(f"Задача успешно завершена. {result_details}")
        except Exception as e:
            context = {'task_id': task.get('id') if task else 'N/A'}
            error_logger = get_logger_adapter(base_logger, context)
            error_logger.error(f"Критическая ошибка при обработке задачи: {e}", exc_info=True)
            if task: db.update_task_status(task['id'], 'failed', str(e))
            METRICS["processing_errors_total"].labels(worker_type='upload', stage='main').inc()
            time.sleep(5)

def enrichment_worker_loop(stop_event: threading.Event, db: DatabaseClient, neo4j: Optional[Neo4jClient], embed_model: Any):
    base_logger = logging.getLogger(threading.current_thread().name)
    logger = get_logger_adapter(base_logger)
    logger.info("Enrichment Worker запущен (включая генерацию эмбеддингов).")
    
    def process_enrichment_stage(chunk_batch: List[Dict], stage: str):
        if not chunk_batch: return
        
        first_chunk = chunk_batch[0]
        log_context = {'doc_id': first_chunk['doc_id'], 'tenant_id': first_chunk['tenant_id'], 'stage': stage, 'batch_size': len(chunk_batch)}
        task_logger = get_logger_adapter(base_logger, log_context)
        
        try:
            if stage == 'embedding_generation':
                task_logger.info(f"Начало генерации эмбеддингов для батча...")
                generate_embeddings(chunk_batch, embed_model, task_logger)
                
                with db.conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute("SELECT value FROM settings WHERE key = 'embedding_config';")
                    config = cur.fetchone()['value']
                    model_version = config.get('version', 1)

                db.update_chunk_embeddings_and_status(chunk_batch, model_version)
                METRICS["chunks_enriched_total"].labels(stage='embedding').inc()
                task_logger.info(f"Эмбеддинги для батча успешно сохранены.")

            elif stage in ['metadata_extraction', 'relation_extraction']:
                for chunk in chunk_batch:
                    single_log_context = {'doc_id': chunk['doc_id'], 'chunk_id': chunk['chunk_id'], 'tenant_id': chunk['tenant_id']}
                    single_task_logger = get_logger_adapter(base_logger, single_log_context)
                    
                    try:
                        if stage == 'metadata_extraction':
                            result = extract_metadata_with_llm(chunk['text'], db, single_log_context)
                            # <<< ИСПРАВЛЕНИЕ: Проверяем, что LLM не вернул ошибку, прежде чем считать успешным
                            if result.get("error"):
                                raise RuntimeError(f"LLM error: {result.get('raw_response', 'No response')}")
                            db.update_chunk_enrichment_status(chunk['doc_id'], chunk['chunk_id'], stage, 'completed', result=result)
                            METRICS["chunks_enriched_total"].labels(stage='metadata').inc()
                        
                        elif stage == 'relation_extraction':
                            relations = extract_relations_with_llm(chunk['text'], db, single_log_context)
                            if relations and neo4j:
                                neo4j.add_structured_relations(relations, str(chunk['tenant_id']), str(chunk['doc_id']))
                            db.update_chunk_enrichment_status(chunk['doc_id'], chunk['chunk_id'], stage, 'completed')
                            METRICS["chunks_enriched_total"].labels(stage='relations').inc()
                    except Exception as e:
                         # <<< ИСПРАВЛЕНИЕ: Ловим ошибку для одного чанка и продолжаем цикл
                        single_task_logger.warning(f"Ошибка при обработке чанка: {e}")
                        db.update_chunk_enrichment_status(chunk['doc_id'], chunk['chunk_id'], stage, 'failed', error=str(e))
                        METRICS["processing_errors_total"].labels(worker_type='enrichment', stage=stage).inc()

        except Exception as e:
            task_logger.warning(f"Ошибка на этапе обогащения '{stage}' для батча: {e}", exc_info=True)
            for chunk in chunk_batch:
                 db.update_chunk_enrichment_status(chunk['doc_id'], chunk['chunk_id'], stage, 'failed', error=str(e))
            METRICS["processing_errors_total"].labels(worker_type='enrichment', stage=stage).inc()

    stages_to_process = ['embedding_generation', 'metadata_extraction']
    if os.getenv("NEO4J_ENABLED", "false").lower() == 'true':
        stages_to_process.append('relation_extraction')

    while not stop_event.is_set():
        processed_in_cycle = 0
        try:
            for stage in stages_to_process:
                batch_size = EMBEDDING_BATCH_SIZE if stage == 'embedding_generation' else ENRICHMENT_BATCH_SIZE
                chunks_to_process = db.get_chunks_for_enrichment(stage, batch_size)
                
                if chunks_to_process:
                    if stage in ['metadata_extraction', 'relation_extraction']:
                        with ThreadPoolExecutor(max_workers=LLM_MAX_CONCURRENCY) as executor:
                            # Группируем по одному чанку для параллельной обработки LLM
                            executor.map(lambda chunk: process_enrichment_stage([chunk], stage), chunks_to_process)
                    else: # Для 'embedding_generation'
                        process_enrichment_stage(chunks_to_process, stage)
                        
                    processed_in_cycle += len(chunks_to_process)
            
            if processed_in_cycle == 0: stop_event.wait(POLL_INTERVAL)
        except Exception as e:
            logger.critical(f"Критическая ошибка в цикле Enrichment Worker: {e}", exc_info=True); time.sleep(15)

def deletion_worker_loop(stop_event: threading.Event, db: DatabaseClient, minio: MinioClient, neo4j: Optional[Neo4jClient]):
    base_logger = logging.getLogger(threading.current_thread().name)
    logger = get_logger_adapter(base_logger)
    logger.info("De-indexing Deletion Worker запущен.")
    
    while not stop_event.is_set():
        task = None
        try:
            task = db.find_next_task_by_operation('deleted')
            if not task:
                stop_event.wait(POLL_INTERVAL); continue

            log_context = {'task_id': task['id'], 'doc_id': task['item_uuid'], 'tenant_id': task['tenant_id']}
            task_logger = get_logger_adapter(base_logger, log_context)
            task_logger.info("Взята новая задача на деиндексацию документа")
            db.update_task_status(task['id'], 'processing')

            doc_id_to_delete = str(task['item_uuid'])
            tenant_id = str(task['tenant_id'])

            with METRICS["doc_processing_duration_seconds"].labels(operation='delete').time():
                if neo4j:
                    neo4j.delete_by_doc_id(doc_id_to_delete, tenant_id)
                    task_logger.info("Данные из Neo4j удалены.")
                
                db.delete_document_cascade(doc_id_to_delete)
                task_logger.info("Записи из PostgreSQL удалены.")

            db.update_task_status(task['id'], 'done', "Документ деиндексирован.")
            METRICS["docs_deprovisioned_total"].inc()
            task_logger.info(f"Задача на деиндексацию успешно завершена.")
        except Exception as e:
            context = {'task_id': task.get('id') if task else 'N/A'}
            error_logger = get_logger_adapter(base_logger, context)
            error_logger.error(f"Критическая ошибка при деиндексации: {e}", exc_info=True)
            if task: db.update_task_status(task['id'], 'failed', str(e))
            METRICS["processing_errors_total"].labels(worker_type='deletion', stage='main').inc()
            time.sleep(5)

def migration_worker_loop(stop_event: threading.Event, db: DatabaseClient, embed_model: Any):
    """Специализированный воркер, выполняющий миграцию эмбеддингов."""
    logger = logging.getLogger(threading.current_thread().name)
    logger.info("Migration Worker запущен.")
    conn = db.conn
    
    target_model_name = ""
    target_dimension = 0
    if isinstance(embed_model, SentenceTransformer):
        target_model_name = getattr(embed_model.model_card_data, 'name', 'unknown_local_model')
        target_dimension = embed_model.get_sentence_embedding_dimension()
    else: # Режим API
        target_model_name = embed_model['model_name']
        target_dimension = embed_model['dimension']

    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("SELECT value FROM settings WHERE key = 'embedding_config';")
        db_config_row = cur.fetchone()
        db_version = db_config_row['value']['version'] if db_config_row else 0
    
    target_version = db_version + 1
    logger.info(f"Цель миграции: модель='{target_model_name}', размерность={target_dimension}, версия={target_version}.")

    with conn.cursor() as cur:
        cur.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_new;")
        cur.execute(f"ALTER TABLE chunks ADD COLUMN embedding_new vector({target_dimension});")
    conn.commit()

    batch_size = int(os.getenv("MIGRATION_BATCH_SIZE", "128"))
    while not stop_event.is_set():
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT count(*) FROM chunks WHERE embedding_version < %s;", (target_version,))
            remaining = cur.fetchone()[0]

        if remaining == 0: break
        logger.info(f"Осталось обработать {remaining} чанков...")
        
        with conn.cursor() as cur:
            cur.execute( "SELECT doc_id, chunk_id, text FROM chunks WHERE embedding_version < %s LIMIT %s;", (target_version, batch_size))
            batch = cur.fetchall()

        if not batch: time.sleep(5); continue
        texts = [row[2] for row in batch]
        
        new_embeddings = None
        if isinstance(embed_model, SentenceTransformer):
            try:
                with torch.no_grad():
                    new_embeddings = embed_model.encode(texts, show_progress_bar=False, batch_size=batch_size)
            finally:
                del texts
                gc.collect()
                if torch.cuda.is_available(): torch.cuda.empty_cache()
        else: # Режим API
            new_embeddings = _generate_embeddings_api(texts, embed_model, logger)

        update_data = [
            (
                new_embeddings[i] if isinstance(new_embeddings[i], list) else new_embeddings[i].tolist(),
                target_version,
                row[0], # doc_id
                row[1]  # chunk_id
            )
            for i, row in enumerate(batch)
        ]
        
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                UPDATE chunks SET
                    embedding_new = data.embedding_new,
                    embedding_version = data.embedding_version
                FROM (VALUES %s) AS data (embedding_new, embedding_version, doc_id, chunk_id)
                -- <<< ИСПРАВЛЕНИЕ: Добавлено явное приведение типа к UUID, чтобы избежать ошибки.
                WHERE chunks.doc_id = data.doc_id::uuid AND chunks.chunk_id = data.chunk_id;
                """,
                update_data,
                page_size=batch_size
            )
        conn.commit()
        
        del batch, new_embeddings, update_data
        gc.collect()
    
    if stop_event.is_set(): logger.warning("Миграция прервана."); return

    logger.info("Атомарная замена колонок...")
    with conn.cursor() as cur:
        cur.execute("BEGIN;")
        cur.execute("ALTER TABLE chunks DROP COLUMN embedding;")
        cur.execute("ALTER TABLE chunks RENAME COLUMN embedding_new TO embedding;")
        cur.execute("COMMIT;")

    new_config = {"model_name": target_model_name, "dimension": target_dimension, "version": target_version}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO settings (key, value, description) 
            VALUES ('embedding_config', %s, 'Конфигурация модели для генерации эмбеддингов')
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """,
            (json.dumps(new_config),)
        )
    conn.commit()
    
    logger.info("="*50)
    logger.info("МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА!")
    logger.info("Перезапустите сервис для перехода в штатный режим.")
    logger.info("="*50)
    stop_event.set()