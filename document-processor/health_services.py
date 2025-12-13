# health_services.py
#
# Версия 3.5: Проверка LLM-сервиса теперь использует LLM_PROVIDER из .env.
# --------------------------------------------------------------------------

import os
import requests
import logging
from typing import Dict, Any, Optional

# Импортируем типы клиентов для подсказок (type hinting),
# чтобы избежать циклических зависимостей во время выполнения.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from clients import DatabaseClient, MinioClient, Neo4jClient

# ### ИЗМЕНЕНИЕ: Используем переменные, определенные для всего проекта ###
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://localhost:11434") 
LLM_HEALTH_TIMEOUT = int(os.getenv("LLM_HEALTH_TIMEOUT", "10"))

def check_postgresql(db_client: "DatabaseClient") -> Dict[str, Any]:
    """Проверяет подключение к PostgreSQL."""
    try:
        # Выполняем самый простой и быстрый запрос для проверки живости
        with db_client.conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        logging.warning(f"Health check: PostgreSQL недоступен. Ошибка: {e}")
        return {"status": "error", "details": str(e)}

def check_minio(minio_client: "MinioClient") -> Dict[str, Any]:
    """Проверяет подключение к MinIO и наличие бакета."""
    try:
        if minio_client.client.bucket_exists(minio_client.bucket_name):
            return {"status": "ok"}
        else:
            details = f"Бакет '{minio_client.bucket_name}' не существует."
            logging.warning(f"Health check: MinIO недоступен. {details}")
            return {"status": "error", "details": details}
    except Exception as e:
        logging.warning(f"Health check: MinIO недоступен. Ошибка: {e}")
        return {"status": "error", "details": str(e)}

def check_neo4j(neo4j_client: Optional["Neo4jClient"]) -> Dict[str, Any]:
    """Проверяет подключение к Neo4j, если он включен."""
    if not neo4j_client or not neo4j_client.driver:
        return {"status": "disabled"}
    try:
        neo4j_client.driver.verify_connectivity()
        return {"status": "ok"}
    except Exception as e:
        logging.warning(f"Health check: Neo4j недоступен. Ошибка: {e}")
        return {"status": "error", "details": str(e)}

# ### ИЗМЕНЕНИЕ: Логика проверки полностью переписана на основе LLM_PROVIDER ###
def check_llm_service() -> Dict[str, Any]:
    """
    Проверка LLM-сервиса на основе LLM_PROVIDER из .env.
    """
    if not LLM_API_BASE:
        return {"status": "disabled", "details": "LLM_API_BASE не задан в .env"}

    base_url = LLM_API_BASE.rstrip('/')
    
    if LLM_PROVIDER in ['openai', 'vllm']:
        endpoint = f"{base_url}/v1/models"
        try:
            response = requests.get(endpoint, timeout=LLM_HEALTH_TIMEOUT)
            if response.status_code == 200 and "data" in response.json():
                model_ids = [m.get("id", "N/A") for m in response.json().get("data", [])]
                details = f"Provider: {LLM_PROVIDER.upper()}. Найдено {len(model_ids)} моделей: {model_ids}"
                return {"status": "ok", "details": details}
            else:
                 details = f"Provider: {LLM_PROVIDER.upper()}. Ошибка ответа от {endpoint} (status: {response.status_code}): {response.text}"
                 logging.warning(f"Health check: LLM Service. {details}")
                 return {"status": "error", "details": details}
        except requests.exceptions.RequestException as e:
            details = f"Provider: {LLM_PROVIDER.upper()}. Не удалось подключиться к {endpoint}. Ошибка: {e}"
            logging.warning(f"Health check: LLM Service. {details}")
            return {"status": "error", "details": details}

    elif LLM_PROVIDER == 'ollama':
        endpoint = f"{base_url}/api/tags"
        try:
            response = requests.get(endpoint, timeout=LLM_HEALTH_TIMEOUT)
            if response.status_code == 200 and "models" in response.json():
                model_names = [m.get("name", "N/A") for m in response.json().get("models", [])]
                details = f"Provider: Ollama. Найдено {len(model_names)} моделей: {model_names}"
                return {"status": "ok", "details": details}
            else:
                 details = f"Provider: Ollama. Ошибка ответа от {endpoint} (status: {response.status_code}): {response.text}"
                 logging.warning(f"Health check: LLM Service. {details}")
                 return {"status": "error", "details": details}
        except requests.exceptions.RequestException as e:
            details = f"Provider: Ollama. Не удалось подключиться к {endpoint}. Ошибка: {e}"
            logging.warning(f"Health check: LLM Service. {details}")
            return {"status": "error", "details": details}
    
    else:
        details = f"Неизвестный LLM_PROVIDER: '{LLM_PROVIDER}'. Проверка невозможна."
        logging.error(f"Health check: LLM Service. {details}")
        return {"status": "error", "details": details}