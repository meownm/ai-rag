# worker.py - ФИНАЛЬНАЯ ВЕРСИЯ: Асинхронный воркер с адаптивным батчингом и логированием
import time
import threading
import logging
import gc
from typing import Dict, Any, List, Union, Tuple
import uuid
import asyncio
import os
import sys

# --- ЗАГРУЗКА .ENV (ДО ИМПОРТОВ, ТРЕБУЮЩИХ ENV) ---
try:
    from dotenv import load_dotenv
    load_dotenv() 
except ImportError:
    pass

# Импорты сторонних библиотек
try:
    from sentence_transformers import SentenceTransformer
    from transformers import AutoModel, AutoTokenizer
    import torch
    import torch.nn.functional as F
    from fastapi import FastAPI
    from fastapi.concurrency import run_in_threadpool
    import asyncpg
    from openai import OpenAI
    from openai import APIError, Timeout as OpenAITimeout 
except ImportError:
    print("FATAL: Необходимые библиотеки не установлены. Пожалуйста, установите: poetry install.")
    sys.exit(1)

# --- Настройка Логгирования и Глобальные Проверки ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
# Logging Adapter для добавления request_id
class ContextAdapter(logging.LoggerAdapter):
    """Автоматически добавляет 'request_id' ко всем сообщениям лога."""
    def process(self, msg, kwargs):
        return '[%s] %s' % (self.extra.get('request_id', 'N/A'), msg), kwargs

# Инициализация адаптеров
global_logger = logging.getLogger("EmbedWorker")
manager_logger_base = logging.getLogger("ModelManager")
logger = ContextAdapter(global_logger, {'request_id': 'N/A'})
manager_logger = ContextAdapter(manager_logger_base, {'request_id': 'N/A'})

_CUDA_AVAILABLE = torch.cuda.is_available() 
try:
    _DML_AVAILABLE = hasattr(torch, 'dml') and torch.dml.is_available()
    _DML_DEVICE = torch.dml.get_device(0) if _DML_AVAILABLE else None
except AttributeError:
    _DML_AVAILABLE = False
    _DML_DEVICE = None
_GPU_AVAILABLE = _CUDA_AVAILABLE or _DML_AVAILABLE 

# --- Константы и Конфигурация Воркера (Из ENV) ---
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://user:password@host:5432/dbname")
WORKER_POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", 5))
WORKER_BATCH_SIZE = int(os.environ.get("WORKER_BATCH_SIZE", 64)) 
WORKER_TYPE = os.environ.get("WORKER_TYPE", "gpu" if _GPU_AVAILABLE else "cpu").lower() 
WORKER_ID = f"{WORKER_TYPE}-worker-{uuid.uuid4().hex[:4]}" 

WORKER_MODEL_TYPE = os.environ.get("WORKER_MODEL_TYPE", "local_torch").lower()
WORKER_POOLING_METHOD = os.environ.get("WORKER_POOLING_METHOD", "mean").lower() 
DB_CHUNKS_TABLE = os.environ.get("DB_CHUNKS_TABLE", "public.chunks")
DB_LOG_TABLE = os.environ.get("DB_LOG_TABLE", "public.worker_log")
DB_SETTINGS_TABLE = os.environ.get("DB_SETTINGS_TABLE", "public.settings")

TRUSTED_MODELS = {"ai-sage/Giga-Embeddings-instruct"}
RAW_TRANSFORMERS_MODELS = {"ai-sage/Giga-Embeddings-instruct"}

# --- Кастомные Ошибки ---
class OOMError(Exception): pass


# --- Model Manager (Управление кэшем) ---

class ModelCacheEntry:
    def __init__(self, model_name: str, device: str):
        self.model_name = model_name
        self.device = device
        self.model: Any = None
        self.last_accessed: float = time.time()
        self.lock = threading.Lock()

class ModelManager:
    def __init__(self, preferred_device: str, unload_timeout_seconds: int = 1800):
        self.preferred_device = preferred_device
        self.unload_timeout = unload_timeout_seconds
        self.cache: Dict[str, ModelCacheEntry] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._stop_event = threading.Event()

        if self.preferred_device == "gpu":
            if _CUDA_AVAILABLE:
                self.device = "cuda:0"
                gpu_name = torch.cuda.get_device_name(0) if _CUDA_AVAILABLE else "N/A"
                manager_logger.info(f"[Startup-GPU] Manager will use CUDA device: {self.device} ({gpu_name})")
            elif _DML_AVAILABLE:
                self.device = str(_DML_DEVICE)
                manager_logger.info(f"[Startup-GPU] Manager will use DirectML device: {self.device}")
            else:
                self.device = "cpu"
                manager_logger.warning("[Startup-GPU] CUDA/ROCm/DirectML not available. Falling back to CPU for GPU queue.")
        else:
            self.device = "cpu"
            manager_logger.info("[Startup-CPU] Manager will use device: CPU")

    def get_model(self, model_name: str, request_id: str = "N/A", model_type: str = "local_torch") -> Any:
        with self._lock:
            key = f"{model_type}:{model_name}"
            if key not in self.cache:
                manager_logger.info(f"[{request_id}-{self.preferred_device.upper()}] Model '{model_name}' (Type: {model_type}) not in cache. Creating new entry.")
                self.cache[key] = ModelCacheEntry(model_name, self.device)
        
        entry = self.cache[key]
        
        if entry.model is not None:
            entry.last_accessed = time.time()
            return entry.model

        with entry.lock:
            if entry.model is not None:
                entry.last_accessed = time.time()
                return entry.model
            
            start_time = time.perf_counter()
            try:
                if model_type == "local_torch":
                    if model_name in RAW_TRANSFORMERS_MODELS:
                        trust_code = model_name in TRUSTED_MODELS
                        tokenizer = AutoTokenizer.from_pretrained(model_name)
                        model_load_kwargs = {'trust_remote_code': trust_code}
                        if self.device.startswith("cuda") and torch.cuda.is_bf16_supported():
                            model_load_kwargs['torch_dtype'] = torch.bfloat16
                            
                        model = AutoModel.from_pretrained(model_name, **model_load_kwargs)
                        model.to(self.device)
                        model.eval()
                        entry.model = (model, tokenizer)
                    else:
                        model_kwargs = {'trust_remote_code': True} if model_name in TRUSTED_MODELS else {}
                        sbert_model = SentenceTransformer(model_name, device=self.device, **model_kwargs)
                        entry.model = sbert_model
                        
                elif model_type == "remote_openai":
                    manager_logger.info(f"[{request_id}] Initializing OpenAI client for model '{model_name}'...")
                    if not os.environ.get("OPENAI_API_KEY"):
                         raise EnvironmentError("OPENAI_API_KEY environment variable not set for remote_openai model.")
                    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=60)
                    entry.model = client
                
                else:
                    raise ValueError(f"Unsupported model_type: {model_type}")
                
                duration = time.perf_counter() - start_time
                manager_logger.info(f"[{request_id}] Model '{model_name}' loaded/initialized in {duration:.2f} seconds.")
                
            except Exception as e:
                with self._lock:
                    if key in self.cache:
                        del self.cache[key]
                manager_logger.error(f"[{request_id}] Failed to load model '{model_name}' (Type: {model_type}): {e}", exc_info=True)
                raise
        
        entry.last_accessed = time.time()
        return entry.model

    def get_model_dimension(self, model_name: str, model_type: str = "local_torch") -> Union[int, None]:
        if model_type != "local_torch":
            return None 

        key = f"{model_type}:{model_name}"
        with self._lock:
            if key not in self.cache:
                return None
            
            entry = self.cache[key]
            with entry.lock:
                if entry.model is None:
                    return None
                
                try:
                    if model_name in RAW_TRANSFORMERS_MODELS:
                        model, _ = entry.model
                        return model.config.hidden_size
                    else:
                        sbert_model = entry.model
                        return sbert_model.get_sentence_embedding_dimension()
                except Exception as e:
                    manager_logger.error(f"[DimCheck] Failed to get dimension for '{model_name}': {e}")
                    return None
                    
    def unload_model(self, model_name: str, model_type: str = "local_torch"):
        key = f"{model_type}:{model_name}"
        if not model_name: return
        with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                with entry.lock: 
                    if entry.model is not None:
                        manager_logger.warning(f"[Unload-{self.preferred_device.upper()}] Explicitly unloading model '{model_name}' (Type: {model_type}) due to config change.")
                        del self.cache[key]
                        entry.model = None 
                        if self.device.startswith("cuda"):
                            torch.cuda.empty_cache()

    def _cleanup_worker(self):
        manager_logger.info(f"[Cleanup-{self.preferred_device.upper()}] Cache cleanup thread started for {self.device}.")
        while not self._stop_event.is_set():
            self._stop_event.wait(60)
            now = time.time()
            models_to_unload = []
            with self._lock:
                for key, entry in self.cache.items():
                    if entry.model is not None and (now - entry.last_accessed) > self.unload_timeout:
                        models_to_unload.append(key)

                for key in models_to_unload:
                    if key in self.cache:
                        entry = self.cache[key]
                        model_name = entry.model_name
                        idle_time = now - entry.last_accessed
                        manager_logger.warning(f"[Cleanup-{self.preferred_device.upper()}] Unloading model '{model_name}' due to inactivity ({idle_time:.0f}s).")
                        del self.cache[key]
                        if self.device.startswith("cuda"):
                            torch.cuda.empty_cache()

    def start_cleanup_thread(self): self._cleanup_thread.start()
    def stop_cleanup_thread(self):
        manager_logger.info(f"[Shutdown-{self.preferred_device.upper()}] Stopping cache cleanup thread for {self.device}.")
        self._stop_event.set()
        self._cleanup_thread.join()


# --- Вспомогательные функции для вычислений ---

def mean_pooling(model_output: Any, attention_mask: torch.Tensor) -> torch.Tensor:
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

def cls_pooling(model_output: Any) -> torch.Tensor:
    return model_output.last_hidden_state[:, 0]

def get_pooling_function(method: str):
    method = method.lower()
    if method == "cls":
        return cls_pooling
    return mean_pooling

def _create_embeddings_sync(
    texts: List[str],
    model_mgr: ModelManager, 
    request_model: str, 
    request_id: str,
    pooling_method: str 
) -> Tuple[List[List[float]], int, None]:
    """Синхронная функция для выполнения Local (CPU/GPU) вычислений. Бросает OOMError."""
    total_tokens = 0
    try:
        loaded_model = model_mgr.get_model(model_name=request_model, request_id=request_id, model_type="local_torch")
        effective_device = model_mgr.device
        
        if request_model in RAW_TRANSFORMERS_MODELS:
            model, tokenizer = loaded_model
            
            tokenized = tokenizer(texts, padding=True, truncation=True, return_tensors='pt', add_special_tokens=False)
            total_tokens = sum(len(ids) for ids in tokenized['input_ids']) + len(texts) 
            
            encoded_input = tokenizer(texts, padding=True, truncation=True, return_tensors='pt').to(effective_device)
            with torch.no_grad():
                model_output = model(**encoded_input)
                
            pooling_func = get_pooling_function(pooling_method)
            
            if pooling_method.lower() == "mean":
                sentence_embeddings = pooling_func(model_output, encoded_input['attention_mask'])
            else:
                sentence_embeddings = pooling_func(model_output)
                
            normalized_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)
            embeddings = normalized_embeddings.tolist() 
            
        else:
            sbert_model: SentenceTransformer = loaded_model
            
            tokenized = sbert_model.tokenizer(texts, add_special_tokens=False)
            total_tokens = sum(len(ids) for ids in tokenized['input_ids'])
            
            embeddings = sbert_model.encode(texts, normalize_embeddings=True, convert_to_numpy=False, convert_to_tensor=True).tolist() 

        return embeddings, total_tokens, None
    except RuntimeError as e:
        if "out of memory" in str(e).lower() or "allocate" in str(e).lower():
            manager_logger.error(f"[{request_id}] OOM detected during local processing! Raising OOMError.")
            if effective_device.startswith("cuda"):
                torch.cuda.empty_cache()
            raise OOMError(str(e))
        raise
    except Exception as e:
        manager_logger.error(f"[{request_id}-{model_mgr.preferred_device.upper()}] Failed to create embedding batch (Local). Error: {e}", exc_info=True)
        return None, 0, str(e)
    finally:
        gc.collect()

async def _create_remote_embeddings_async(
    texts: List[str],
    model_mgr: ModelManager, 
    request_model: str, 
    request_id: str
) -> Tuple[List[List[float]], int, None]:
    """Асинхронный I/O-bound обработчик для удаленных API-моделей (с Retry)."""
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        try:
            loaded_client: OpenAI = model_mgr.get_model(request_model, request_id, model_type="remote_openai")
            
            def api_call_sync():
                response = loaded_client.embeddings.create(
                    input=texts,
                    model=request_model,
                )
                embeddings = [d.embedding for d in response.data]
                usage = response.usage
                total_tokens = usage.total_tokens
                return embeddings, total_tokens, None
                
            embeddings, total_tokens, error = await run_in_threadpool(api_call_sync)
            
            return embeddings, total_tokens, error

        except (APIError, OpenAITimeout, Exception) as e:
            error_msg = str(e)
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt
                logger.warning(f"[{request_id}-REMOTE] API Error (Attempt {attempt + 1}/{MAX_RETRIES}). Retrying in {wait_time}s. Error: {error_msg}")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"[{request_id}-REMOTE] Final API call failed after {MAX_RETRIES} attempts. Error: {error_msg}", exc_info=True)
                return None, 0, error_msg

    return None, 0, "Unknown error during remote processing (unreachable)"


# --- Класс Воркера (Task Processor) ---

class WorkerApp:
    
    # ФИКС: УДАЛЕН ПРЕФИКС 'f' перед строкой, чтобы избежать SyntaxError f-string
    _CREATE_LOG_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS {} (
            log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            worker_id varchar(20) NOT NULL,
            request_id varchar(10) NOT NULL,
            model_name varchar(100) NOT NULL,
            embedding_version int4 NOT NULL,
            device_type varchar(10) NOT NULL,
            batch_size int4 NOT NULL,
            texts_snippet text NULL,
            embedding_dimension int4 NULL,
            
            start_time timestamptz DEFAULT now() NULL,
            duration_seconds numeric(8, 3) NULL,
            
            result_status varchar(20) NOT NULL,
            error_message text NULL,
            
            tasks_processed int4 DEFAULT 0 NOT NULL,
            tasks_failed int4 DEFAULT 0 NOT NULL,
            total_tokens int8 DEFAULT 0 NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_worker_log_request_id ON {} (request_id);
        CREATE INDEX IF NOT EXISTS ix_worker_log_model_name ON {} (model_name);
    """

    def __init__(self, preferred_device: str, worker_id: str, poll_interval: int, dsn: str, batch_size: int, 
                 model_type: str, pooling_method: str, chunks_table: str, log_table: str, settings_table: str):
        self.worker_id = worker_id
        self.poll_interval = poll_interval
        self.dsn = dsn
        self.preferred_device = preferred_device
        self.batch_size = batch_size
        
        self.model_type: str = model_type
        self.pooling_method: str = pooling_method
        
        # Абстракция таблиц
        self.CHUNKS_TABLE = chunks_table
        self.LOG_TABLE = log_table
        self.SETTINGS_TABLE = settings_table
        
        # Динамические параметры
        self.model_name: str = ""
        self.embedding_version: int = 0 
        self.current_batch_size = batch_size
        self._config_last_updated: float = 0.0
        self._config_refresh_interval: int = 60 

        self.model_manager = ModelManager(preferred_device=preferred_device)
        self.db_pool: Any = None
        self._stop_event = asyncio.Event()
        self._worker_task: Any = None
        
        logger.info(f"[{self.worker_id}] Initializing worker on device: {self.preferred_device.upper()}. Batch Size: {self.batch_size}.")

    async def _get_db_pool(self) -> asyncpg.Pool:
        if self.db_pool is None:
            self.db_pool = await asyncpg.create_pool(self.dsn)
        return self.db_pool
        
    async def _ensure_log_table_exists(self):
        try:
            pool = await self._get_db_pool()
            async with pool.acquire() as conn:
                logger.info(f"[{self.worker_id}] Checking for existence of '{self.LOG_TABLE}' table...")
                sql_to_execute = self._CREATE_LOG_TABLE_SQL.format(self.LOG_TABLE, self.LOG_TABLE, self.LOG_TABLE)
                await conn.execute(sql_to_execute)
                logger.info(f"[{self.worker_id}] '{self.LOG_TABLE}' table check/creation successful.")
        except Exception as e:
            logger.critical(f"[{self.worker_id}] FATAL: Failed to create/check '{self.LOG_TABLE}' table. Check DB permissions/DSN. Error: {e}")
            raise

    async def _get_db_vector_dimension(self, conn: asyncpg.Connection) -> Union[int, None]:
        query = f"""
            SELECT 
                split_part(typname::text, 'vector', 2)::integer
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_type t ON t.oid = a.atttypid
            WHERE 
                n.nspname || '.' || c.relname = '{self.CHUNKS_TABLE}' AND 
                a.attname = 'embedding' AND
                t.typname LIKE 'vector%';
        """
        try:
            dimension = await conn.fetchval(query) 
            return dimension
        except Exception as e:
            logger.error(f"[{self.worker_id}] Failed to read DB vector dimension for {self.CHUNKS_TABLE}: {e}")
            return None

    async def _refresh_config(self, conn: asyncpg.Connection):
        """Читает model_name и version из settings. Остальные параметры - из ENV."""
        now = time.time()
        if now - self._config_last_updated < self._config_refresh_interval:
            return

        try:
            query = f"SELECT value FROM {self.SETTINGS_TABLE} WHERE key = 'embedding_config'"
            record = await conn.fetchrow(query)
            if record:
                config = record['value']
                new_model_name = config.get('model_name')
                new_version = config.get('version')
                
                if not new_model_name or not isinstance(new_version, int):
                    logger.error(f"Invalid embedding_config format: missing model_name or version.")
                    return
                
                if new_model_name != self.model_name or new_version != self.embedding_version:
                    old_model = self.model_name
                    old_type = self.model_type
                    
                    self.model_name = new_model_name
                    self.embedding_version = new_version
                    
                    self.model_manager.unload_model(old_model, old_type) 
                    
                    if old_model:
                         logger.warning(f"[Refresh] Model config updated! Old: {old_model} ({old_type}) -> New: {new_model_name} ({self.model_type}).")
                    
                self._config_last_updated = now
        except Exception as e:
            logger.error(f"[{self.worker_id}] Failed to refresh config from DB: {e}", exc_info=True)
            
    async def _mark_batch_failed(self, conn: asyncpg.Connection, task_batch: List[Dict[str, Any]], error_detail: str):
        failed_updates = []
        now = time.time()
        
        failed_status_jsonb = {
            "status": "FAILED", 
            "processor": self.worker_id, 
            "model": self.model_name, 
            "device": self.model_manager.device if self.model_type == "local_torch" else "remote", 
            "error": error_detail, 
            "failed_at": now
        }
        
        for task_info in task_batch:
            update_sql = f"""
                UPDATE {self.CHUNKS_TABLE}
                SET 
                    enrichment_status = jsonb_set(
                        COALESCE(enrichment_status, '{}'::jsonb),
                        '{{embedding_generation}}',
                        $4::jsonb,
                        true
                    )
                WHERE doc_id = $2 AND chunk_id = $3;
            """
            failed_updates.append(conn.execute(update_sql, error_detail, task_info['doc_id'], task_info['chunk_id'], failed_status_jsonb))
            
        await asyncio.gather(*failed_updates)

    async def _log_to_db(self, conn: asyncpg.Connection, request_id: str, status: str, batch_size: int, text_snippet: str, dim: int, duration: float, error: str, start_time: float, total_tokens: int = 0) -> Union[uuid.UUID, None]:
        try:
            query = f"""
                INSERT INTO {self.LOG_TABLE} (
                    worker_id, request_id, model_name, embedding_version, device_type, batch_size, 
                    texts_snippet, embedding_dimension, start_time, duration_seconds, result_status, error_message, total_tokens
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING log_id;
            """
            snippet = text_snippet[:250] + "..." if text_snippet and len(text_snippet) > 250 else text_snippet
            start_ts = time.time() if start_time else None
            device_for_log = self.model_manager.device if self.model_type == "local_torch" else self.model_type 
            
            log_id = await conn.fetchval(query, 
                self.worker_id, request_id, self.model_name, self.embedding_version, device_for_log, 
                batch_size, snippet, dim, start_ts, duration, status, error, total_tokens
            )
            return log_id
        except Exception as e:
            logger.error(f"[LogInsert] Failed to insert log entry into DB: {e}")
            return None


    async def _update_log_in_db(self, conn: asyncpg.Connection, log_id: uuid.UUID, status: str, duration: float, error: str, tasks_processed: int, tasks_failed: int, total_tokens: int = 0):
        if not log_id: return
        try:
            query = f"""
                UPDATE {self.LOG_TABLE}
                SET duration_seconds = $2, 
                    result_status = $3, 
                    error_message = $4,
                    tasks_processed = $5,
                    tasks_failed = $6,
                    total_tokens = $7
                WHERE log_id = $1;
            """
            await conn.execute(query, log_id, duration, status, error, tasks_processed, tasks_failed, total_tokens)
        except Exception as e:
            logger.error(f"[LogUpdate] Failed to update log entry {log_id}: {e}")

    async def _fetch_and_process_task(self):
        
        request_id = str(uuid.uuid4().hex[:8])
        # Устанавливаем request_id в адаптеры для всего цикла
        global_logger.extra['request_id'] = request_id
        manager_logger.extra['request_id'] = request_id

        task_batch: List[Dict[str, Any]] = [] 
        log_id = None 
        
        current_attempt_size = self.current_batch_size
        max_attempts = 3 

        for attempt in range(max_attempts):
            
            try:
                # 1. Захват батча (с использованием current_attempt_size)
                async with self.db_pool.acquire() as conn:
                    await self._refresh_config(conn)
                    if not self.model_name: 
                        break

                    actual_dimension = self.model_manager.get_model_dimension(self.model_name, self.model_type)
                    
                    if actual_dimension is None and self.model_type == "local_torch":
                        logger.critical(f"Local model '{self.model_name}' failed to report dimension. BLOCKED.")
                        break

                    db_dimension = await self._get_db_vector_dimension(conn)
                    
                    # --- ЛОГИКА БЛОКИРОВКИ/ОЖИДАНИЯ МИГРАЦИИ (Для Local models) ---
                    if self.model_type == "local_torch" and actual_dimension != db_dimension:
                        migration_required_msg = (
                            f"CRITICAL DIMENSION MISMATCH! Local Model dim={actual_dimension} != DB dim={db_dimension}. "
                            "Worker BLOCKED, WAITING FOR EXTERNAL DB MIGRATION (ALTER TABLE...)."
                        )
                        logger.critical(migration_required_msg)
                        
                        update_config_query = f"UPDATE {self.SETTINGS_TABLE} SET value = jsonb_set(value, '{{dimension}}', $1::text::jsonb) WHERE key = 'embedding_config';"
                        await conn.execute(update_config_query, str(actual_dimension))
                        
                        await self._log_to_db(conn, request_id, "BLOCKED", self.batch_size, "Migration Required", actual_dimension, 0, migration_required_msg, time.time())
                        await asyncio.sleep(self.poll_interval) 
                        break 

                    # Захват батча
                    capture_query = f"""
                        WITH task_to_process AS (
                            SELECT doc_id, chunk_id FROM {self.CHUNKS_TABLE}
                            WHERE 
                                embedding IS NULL 
                                OR embedding_version < {self.embedding_version}
                            ORDER BY doc_id, chunk_id ASC 
                            LIMIT {current_attempt_size}
                            FOR UPDATE SKIP LOCKED
                        )
                        UPDATE {self.CHUNKS_TABLE} c
                        SET 
                            enrichment_status = jsonb_set(
                                COALESCE(c.enrichment_status, '{{}}'::jsonb), 
                                '{{embedding_generation}}',
                                '{{"status": "PROCESSING", "processor": "{self.worker_id}", "model": "{self.model_name}", "device": "{self.model_manager.device if self.model_type == "local_torch" else "remote"}"}}'::jsonb,
                                true
                            )
                        FROM task_to_process t
                        WHERE c.doc_id = t.doc_id AND c.chunk_id = t.chunk_id
                        RETURNING c.doc_id, c.chunk_id, c.text;
                    """
                    records = await conn.fetch(capture_query)
                    if not records: 
                        break 
                    
                    task_batch = [dict(r) for r in records]
                    texts_to_embed = [t['text'] for t in task_batch]
                    
                    log_id = await self._log_to_db(
                        conn, request_id, "PROCESSING", len(task_batch), task_batch[0]['text'], 
                        actual_dimension if actual_dimension else 0, 0, None, time.time(), 0
                    )

                # 2. Выполнение батча (Offload)
                start_embed_time = time.perf_counter()
                
                embeddings_batch = None
                total_tokens = 0
                error_message = None

                if self.model_type == "local_torch":
                    embeddings_batch, total_tokens, error_message = await run_in_threadpool(
                        _create_embeddings_sync, texts_to_embed, self.model_manager, self.model_name, request_id, self.pooling_method
                    )
                elif self.model_type == "remote_openai":
                    embeddings_batch, total_tokens, error_message = await _create_remote_embeddings_async(
                        texts_to_embed, self.model_manager, self.model_name, request_id
                    )
                else:
                    error_message = f"Unsupported model_type: {self.model_type}"
                
                end_embed_time = time.perf_counter()
                duration = end_embed_time - start_embed_time
                texts_count = len(task_batch)

                # 3. Обновление текущего батча (Успех)
                if current_attempt_size < self.batch_size:
                    self.current_batch_size = min(self.batch_size, current_attempt_size * 2)
                    logger.info(f"Batch size successfully restored to {self.current_batch_size}")
                    
                # 4. Обновление логов и chunks (Успех/Провал)
                final_status = "SUCCESS" if embeddings_batch is not None and len(embeddings_batch) == texts_count else "FAILED"
                tasks_success = texts_count if final_status == "SUCCESS" else 0
                tasks_fail = texts_count if final_status == "FAILED" else 0
                final_error = error_message if final_status == "FAILED" else None
                
                if actual_dimension is None and final_status == "SUCCESS" and embeddings_batch and embeddings_batch[0]:
                    actual_dimension = len(embeddings_batch[0])

                async with self.db_pool.acquire() as conn:
                    await self._update_log_in_db(
                        conn, log_id, final_status, duration, final_error, tasks_success, tasks_fail, total_tokens
                    )
                    
                    if final_status == "SUCCESS":
                        update_tasks = []
                        now = time.time()
                        
                        completed_status_jsonb = {
                            "status": "COMPLETED", 
                            "processor": self.worker_id, 
                            "model": self.model_name, 
                            "device": self.model_manager.device if self.model_type == "local_torch" else "remote", 
                            "completed_at": now
                        }
                        
                        for task_info, embedding in zip(task_batch, embeddings_batch):
                            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                            
                            update_sql = f"""
                                UPDATE {self.CHUNKS_TABLE}
                                SET 
                                    embedding = $1::vector, 
                                    embedding_version = $4,
                                    enrichment_status = jsonb_set(
                                        COALESCE(enrichment_status, '{}'::jsonb), 
                                        '{{embedding_generation}}',
                                        $5::jsonb,
                                        true
                                    )
                                WHERE doc_id = $2 AND chunk_id = $3;
                            """
                            update_tasks.append(conn.execute(update_sql, embedding_str, task_info['doc_id'], task_info['chunk_id'], self.embedding_version, completed_status_jsonb))
                            
                        await asyncio.gather(*update_tasks)
                        
                    else:
                        await self._mark_batch_failed(conn, task_batch, final_error)

                    speed = texts_count / duration
                    logger.info(
                        f"BATCH {final_status}. Count: {texts_count}/{tasks_success}, Time: {duration:.3f}s, Speed: {speed:.1f} texts/sec. Tokens: {total_tokens}"
                    )
                
                return # Успех или Финальный Провал (не OOM) - выход из цикла for
            
            # --- ЛОГИКА АДАПТИВНОГО БАТЧИНГА И OOM ---
            except OOMError as e:
                # Если это не последняя попытка (attempt < max_attempts - 1)
                if current_attempt_size == 1 or attempt == max_attempts - 1:
                    logger.critical(f"FATAL OOM detected. Cannot process this task at batch_size={current_attempt_size}. Marking as FAILED.")
                    async with self.db_pool.acquire() as conn:
                        await self._mark_batch_failed(conn, task_batch, f"FATAL OOM at batch_size={current_attempt_size}. Task abandoned.")
                    break # Выход из for
                
                # Уменьшаем размер батча и повторяем
                new_size = max(1, current_attempt_size // 2)
                self.current_batch_size = new_size
                current_attempt_size = new_size # Устанавливаем новый размер для следующего LIMIT
                logger.warning(f"OOM Error. Reducing current batch size to {new_size}. Retrying in next loop iteration.")
                
                # Помечаем текущий захват как отмененный (FAILED), чтобы он был перехвачен снова с меньшим LIMIT.
                async with self.db_pool.acquire() as conn:
                    await self._mark_batch_failed(conn, task_batch, f"OOM detected. Batch size reduced to {new_size}.")
                
            except Exception as e:
                logger.error(f"Unhandled error during fetch/process loop: {e}", exc_info=True)
                break # Общая ошибка - выход из for
        


    async def worker_loop(self):
        await self._get_db_pool()
        logger.info(f"Worker loop started on {self.model_manager.device}. Polling every {self.poll_interval}s.")
        
        async with self.db_pool.acquire() as conn:
             await self._refresh_config(conn)
        
        while not self._stop_event.is_set():
            try:
                await self._fetch_and_process_task()
                
            except Exception as e:
                logger.error(f"Unhandled exception in worker loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.poll_interval)


    async def start(self):
        await self._ensure_log_table_exists()
        self.model_manager.start_cleanup_thread()
        self._worker_task = asyncio.create_task(self.worker_loop())

    async def stop(self):
        logger.info(f"Shutting down worker...")
        self.model_manager.stop_cleanup_thread()
        self._stop_event.set()
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=self.poll_interval + 1)
            except asyncio.TimeoutError:
                logger.warning(f"Worker task did not stop gracefully.")
            except asyncio.CancelledError:
                 pass
                 
        if self.db_pool:
            await self.db_pool.close()

def start_uvicorn():
    """Точка входа Poetry для запуска Uvicorn."""
    import uvicorn
    # Используем порт 8000, который зафиксирован в pyproject.toml
    port = int(os.environ.get("UVICORN_PORT", 8000)) 
    uvicorn.run("worker:app", host="0.0.0.0", port=port, log_level="info")

# --- Настройка FastAPI (только для Health Check и управления жизненным циклом) ---

# Инициализация WorkerApp
worker_app = WorkerApp(
    preferred_device=WORKER_TYPE,
    worker_id=WORKER_ID,
    poll_interval=WORKER_POLL_INTERVAL,
    dsn=POSTGRES_DSN,
    batch_size=WORKER_BATCH_SIZE,
    model_type=WORKER_MODEL_TYPE, 
    pooling_method=WORKER_POOLING_METHOD,
    chunks_table=DB_CHUNKS_TABLE,     
    log_table=DB_LOG_TABLE,           
    settings_table=DB_SETTINGS_TABLE  
)

app = FastAPI(title=f"Worker: {WORKER_ID}", description="Worker для асинхронного создания эмбеддингов.", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...")
    await worker_app.start()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown...")
    await worker_app.stop()

@app.get("/health", tags=["Health"])
async def health_check():
    db_status = "ok"
    try:
        if worker_app.db_pool:
            conn = await worker_app.db_pool.acquire()
            await conn.fetchval("SELECT 1")
            await worker_app.db_pool.release(conn)
        else:
             db_status = "pending_connection" 
    except Exception:
        db_status = "error"
        
    return {
        "status": "ok",
        "worker_id": worker_app.worker_id,
        "worker_type": worker_app.preferred_device.upper(),
        "current_model": worker_app.model_name,
        "current_version": worker_app.embedding_version,
        "current_pooling": worker_app.pooling_method,
        "current_model_type": worker_app.model_type,
        "db_status": db_status,
        "manager_info": {
            "effective_device": str(worker_app.model_manager.device),
            "cuda_available": _CUDA_AVAILABLE,
            "dml_available": _DML_AVAILABLE,
            "cached_models_count": len(worker_app.model_manager.cache)
        }
    }