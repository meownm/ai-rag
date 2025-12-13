# main.py
#
# Версия 3.14: Добавлена валидация LLM_PROVIDER при запуске.
# --------------------------------------------------------------------------

import threading
import torch
import uvicorn
import os
import time
import logging
import logging.handlers
import json
import requests
from fastapi import FastAPI, Request, Response, status as http_status
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from prometheus_client import make_asgi_app
from psycopg2.extras import DictCursor

# Импортируем классы-клиенты
from clients import DatabaseClient, MinioClient, Neo4jClient

# Импортируем функции-воркеры и метрики
from worker import upload_worker_loop, enrichment_worker_loop, deletion_worker_loop, migration_worker_loop, METRICS

# Импортируем функции для health-check
from health_services import check_postgresql, check_minio, check_neo4j, check_llm_service
from db_schema import get_vector_dimension

load_dotenv()

# --- Настройка логирования ---
def setup_logging():
    """Настраивает логирование в консоль и ротируемый файл."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    log_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(threadName)s] - %(name)s (%(filename)s:%(lineno)d) - %(message)s'
    )
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "worker.log"), 
        maxBytes=10*1024*1024, # 10 MB
        backupCount=5
    )
    file_handler.setFormatter(log_formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

# --- Глобальные переменные для управления воркерами ---
shutdown_flag = threading.Event()
worker_threads = []

# --- Приложение FastAPI ---
app = FastAPI(
    title="Document Processor Service (Internal Worker)",
    description="Фоновый сервис-обработчик для конвейера индексации документов.",
    version="3.14.0"
)

app.mount("/metrics", make_asgi_app())

# --- Супервизор для фоновых воркеров ---
def worker_supervisor(worker_func, stop_event: threading.Event, **kwargs):
    """Обертка, которая перезапускает любой воркер при сбое."""
    thread_name = threading.current_thread().name
    logging.info(f"Супервизор для воркера '{thread_name}' ({worker_func.__name__}) запущен.")
    while not stop_event.is_set():
        try:
            worker_func(stop_event=stop_event, **kwargs)
        except Exception as e:
            logging.critical(
                f"Критическая авария в воркере '{thread_name}'! Перезапуск через 15 секунд. Ошибка: {e}",
                exc_info=True
            )
            time.sleep(15)
    logging.info(f"Супервизор для воркера '{thread_name}' завершает работу.")

def is_migration_needed(db_client: DatabaseClient, model_name: str, model_dim: int, generator: str) -> bool:
    """
    Проверяет, нужна ли миграция, и инициализирует конфиг при первом запуске.
    Возвращает True, если нужна миграция, False - если все в порядке.
    """
    with db_client.conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("SELECT value FROM settings WHERE key = 'embedding_config';")
        config_row = cur.fetchone()

        if not config_row:
            logging.info("Конфигурация эмбеддингов в БД не найдена. Инициализация для первого запуска...")
            
            initial_config = {
                "model_name": model_name,
                "dimension": model_dim,
                "version": 1,
                "generator": generator,
            }
            cur.execute(
                """
                INSERT INTO settings (key, value, description) 
                VALUES ('embedding_config', %s, 'Конфигурация модели для генерации эмбеддингов');
                """,
                (json.dumps(initial_config),)
            )
            
            schema_dim = get_vector_dimension(db_client.conn)
            if schema_dim > 0 and schema_dim != model_dim:
                 logging.warning(f"Обнаружено несоответствие размерности в схеме ({schema_dim}) и в модели ({model_dim}). Запускаем миграцию для синхронизации.")
                 cur.execute("DELETE FROM settings WHERE key = 'embedding_config';")
                 db_client.conn.commit()
                 return True

            db_client.conn.commit()
            logging.info(f"Таблица settings успешно инициализирована с моделью '{model_name}'.")
            return False

        db_config = config_row['value']
        db_model_name = db_config.get('model_name')
        db_dim = db_config.get('dimension')
        db_generator = db_config.get('generator')

        if db_model_name != model_name or db_dim != model_dim:
            logging.warning(f"ОБНАРУЖЕНО НЕСООТВЕТСТВИЕ КОНФИГУРАЦИИ: БД={{'model': '{db_model_name}', 'dim': {db_dim}}}, .env={{'model': '{model_name}', 'dim': {model_dim}}}.")
            return True

        if db_generator and db_generator != generator:
            logging.warning(f"Обнаружено различие способа генерации эмбеддингов: в БД '{db_generator}', в окружении '{generator}'. Обновите embedding_config при необходимости.")

    return False

def load_embedding_model_local():
    """Загружает локальную модель эмбеддингов с помощью SentenceTransformers."""
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logging.info(f"Загрузка локальной модели эмбеддингов: {model_name} на {device}")
    try:
        model = SentenceTransformer(model_name, trust_remote_code=True, device=device)
    except TypeError:
        model = SentenceTransformer(model_name, model_kwargs={"device": device})
    except Exception as e:
        logging.exception(f"Не удалось загрузить модель эмбеддингов '{model_name}': {e}")
        raise
    logging.info(f"Локальная модель '{model_name}' успешно загружена.")
    return model

def get_dimension_from_api(api_base: str, model_name: str, generator: str = "service") -> int:
    """Делает тестовый запрос к API, чтобы определить размерность векторов. В случае ошибки пробрасывает исключение."""
    if generator == "ollama":
        endpoint = f"{api_base.rstrip('/')}/api/embeddings"
        payload = {"model": model_name, "prompt": "test"}
    else:
        endpoint = f"{api_base.rstrip('/')}/embeddings"
        payload = {"model": model_name, "input": ["test"]}
    headers = {"Content-Type": "application/json"}
    logging.info(f"Отправка тестового запроса в {endpoint} для определения размерности...")
    
    try:
        response = requests.post(endpoint, json=payload, timeout=30, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        dimension = len(response_data["data"][0]["embedding"])
        if dimension == 0: raise ValueError("API вернул эмбеддинг нулевой длины.")
        return dimension
    except (requests.exceptions.RequestException, ValueError, KeyError, IndexError) as e:
        # Просто пробрасываем исключение, чтобы его поймал вызывающий код
        raise e

# --- Управление жизненным циклом ---
@app.on_event("startup")
def startup_event():
    setup_logging()
    logging.info("Событие 'startup': инициализация ресурсов и проверка режима работы...")

    # ### ИЗМЕНЕНИЕ: Валидация LLM_PROVIDER при старте приложения ###
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    allowed_providers = ['ollama', 'openai', 'vllm']
    if llm_provider not in allowed_providers:
        raise ValueError(f"Некорректное значение для LLM_PROVIDER: '{llm_provider}'. Допустимые значения: {allowed_providers}")
    logging.info(f"LLM провайдер сконфигурирован как: {llm_provider.upper()}")

    db_client = DatabaseClient()
    minio_client = MinioClient()
    
    neo4j_client = None
    if os.getenv("NEO4J_ENABLED", "false").lower() == 'true':
        neo4j_client = Neo4jClient(uri=os.getenv("NEO4J_URI"), user=os.getenv("NEO4J_USER"), password=os.getenv("NEO4J_PASSWORD"))
        if neo4j_client.driver is None: neo4j_client = None

    embedding_mode = os.getenv("EMBEDDING_MODE", "local").strip().lower()
    embedding_generator = os.getenv("EMBEDDING_GENERATOR") or ("service" if embedding_mode == "api" else "local_model")
    model_name_from_env = os.getenv("EMBEDDING_MODEL_NAME")
    if not model_name_from_env:
        raise ValueError("EMBEDDING_MODEL_NAME не задана в .env!")
        
    embedding_model = None
    model_dimension = None
    effective_model_name = model_name_from_env

    if embedding_mode == "api":
        logging.info("Режим работы эмбеддингов: попытка использовать ВНЕШНИЙ API")
        api_base = os.getenv("EMBEDDING_API_BASE")
        if not api_base:
            raise ValueError("Для EMBEDDING_MODE='api' необходимо задать EMBEDDING_API_BASE в .env")
        
        try:
            model_dimension = get_dimension_from_api(api_base, model_name_from_env, embedding_generator)
            logging.info(f"Успешно подключено к API. Динамически определена размерность: {model_dimension}")

            embedding_model = {
                "mode": "api", "api_base": api_base,
                "model_name": model_name_from_env, "dimension": model_dimension,
                "generator": embedding_generator,
            }
            logging.info(f"Генератор эмбеддингов настроен на API: {api_base} с моделью '{model_name_from_env}'")

        except Exception as e:
            logging.warning("="*60)
            logging.warning(f"НЕ УДАЛОСЬ подключиться к API эмбеддингов. Ошибка: {e}")
            logging.warning("!!! ПЕРЕКЛЮЧЕНИЕ НА РЕЗЕРВНУЮ ЛОКАЛЬНУЮ МОДЕЛЬ !!!")
            logging.warning("="*60)
            
            embedding_model_instance = load_embedding_model_local()
            model_dimension = embedding_model_instance.get_sentence_embedding_dimension()
            embedding_model = embedding_model_instance
            effective_model_name = getattr(embedding_model.model_card_data, 'name', model_name_from_env)

    else: # По умолчанию 'local'
        logging.info("Режим работы эмбеддингов: ЛОКАЛЬНАЯ МОДЕЛЬ")
        embedding_model_instance = load_embedding_model_local()
        model_dimension = embedding_model_instance.get_sentence_embedding_dimension()
        embedding_model = embedding_model_instance
        effective_model_name = getattr(embedding_model.model_card_data, 'name', model_name_from_env)
    
    app.state.db_client = db_client
    app.state.minio_client = minio_client
    app.state.neo4j_client = neo4j_client
    app.state.embedding_model = embedding_model

    if is_migration_needed(db_client, effective_model_name, model_dimension, embedding_generator):
        logging.warning("="*50)
        logging.warning("!!! СИСТЕМА ЗАПУСКАЕТСЯ В РЕЖИМЕ МИГРАЦИИ ЭМБЕДДИНГОВ !!!")
        logging.warning("="*50)
        
        thread = threading.Thread(
            target=migration_worker_loop,
            name="MigrationWorker",
            args=(shutdown_flag, db_client, embedding_model),
            daemon=True
        )
        thread.start()
        worker_threads.append(thread)
    else:
        logging.info("Конфигурация соответствует. Запуск в штатном режиме.")
        schema_dim = get_vector_dimension(db_client.conn)
        if schema_dim > 0 and model_dimension != schema_dim:
            raise RuntimeError(f"Критическое несоответствие! Размерность модели ({model_dimension}) не совпадает со схемой БД ({schema_dim}). Миграция могла быть прервана. Проверьте состояние!")
            
        worker_counts = {
            "upload": int(os.getenv("UPLOAD_WORKER_COUNT", "2")),
            "enrichment": int(os.getenv("ENRICHMENT_WORKER_COUNT", "1")),
            "deletion": int(os.getenv("DELETION_WORKER_COUNT", "1")),
        }

        worker_map = {
            "upload": (upload_worker_loop, {"db": db_client, "minio": minio_client, "neo4j": neo4j_client}),
            "enrichment": (enrichment_worker_loop, {"db": db_client, "neo4j": neo4j_client, "embed_model": embedding_model}),
            "deletion": (deletion_worker_loop, {"db": db_client, "minio": minio_client, "neo4j": neo4j_client}),
        }

        for worker_type, count in worker_counts.items():
            if count > 0:
                target_func, kwargs = worker_map[worker_type]
                for i in range(count):
                    thread = threading.Thread(
                        target=worker_supervisor,
                        name=f"{worker_type.capitalize()}Worker-{i+1}",
                        args=(target_func, shutdown_flag),
                        kwargs=kwargs,
                        daemon=True
                    )
                    thread.start()
                    worker_threads.append(thread)
                    logging.info(f"Запущен воркер: {thread.name}")

@app.on_event("shutdown")
def shutdown_event():
    logging.info("Событие 'shutdown': инициировано graceful shutdown...")
    shutdown_flag.set()
    
    for thread in worker_threads:
        logging.info(f"Ожидание завершения работы воркера {thread.name} (до 30 секунд)...")
        thread.join(timeout=30)
        if thread.is_alive():
            logging.warning(f"Воркер {thread.name} не успел завершить работу за 30 секунд.")
        else:
            logging.info(f"Воркер {thread.name} успешно остановлен.")

    if hasattr(app.state, 'neo4j_client') and app.state.neo4j_client:
        app.state.neo4j_client.close()
    if hasattr(app.state, 'db_client') and app.state.db_client:
        app.state.db_client.close()
    
    logging.info("Все ресурсы успешно освобождены. Завершение работы.")

@app.get("/health", tags=["Monitoring"])
def health_check(request: Request, response: Response):
    """Выполняет детальную проверку состояния всех внешних интеграций."""
    services_status = {
        "postgresql": check_postgresql(request.app.state.db_client),
        "minio": check_minio(request.app.state.minio_client),
        "neo4j": check_neo4j(request.app.state.neo4j_client),
        "llm_service": check_llm_service(),
    }
    
    overall_healthy = all(
        status["status"] in ["ok", "disabled"]
        for status in services_status.values()
    )
    
    if not overall_healthy:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
        logging.warning(f"Health check провален. Статус: {services_status}")
        
    return services_status

if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        setup_logging()
    
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=False)