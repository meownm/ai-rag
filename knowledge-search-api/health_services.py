import os
import requests
from typing import Dict, Any, Optional

# Импортируем типы клиентов для подсказок типов, но не создаем экземпляры.
# Это помогает избежать циклических зависимостей.
from clients import PostgreSQLClient, Neo4jClient

# Читаем URL Ollama из переменных окружения
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

def check_postgresql(db_client: PostgreSQLClient) -> Dict[str, Any]:
    """
    Проверяет подключение к PostgreSQL путем выполнения простого запроса.
    """
    if not db_client or not db_client.pool:
        return {"status": "error", "details": "Database client not initialized."}
    try:
        # Выполняем самый простой и быстрый запрос для проверки живости соединения
        with db_client.get_cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        # В случае ошибки возвращаем ее описание для диагностики
        return {"status": "error", "details": str(e)}

def check_neo4j(neo4j_client: Optional[Neo4jClient]) -> Dict[str, Any]:
    """
    Проверяет подключение к Neo4j, если он включен в конфигурации.
    """
    # Если Neo4j отключен в .env, клиент будет None. Это не ошибка.
    if not neo4j_client or not neo4j_client.driver:
        return {"status": "disabled"}
    try:
        # Встроенный метод драйвера для проверки подключения
        neo4j_client.driver.verify_connectivity()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "details": str(e)}

def check_ollama() -> Dict[str, Any]:
    """

    Проверяет доступность Ollama API, отправляя запрос на его корневой URL.
    """
    try:
        # Извлекаем базовый URL (хост и порт) из полного URL API
        # Пример: 'http://localhost:11434/api/generate' -> 'http://localhost:11434'
        ollama_base_url = OLLAMA_URL.rsplit('/api/', 1)[0]
        
        # Отправляем простой GET-запрос на базовый URL. Ollama должен ответить.
        response = requests.get(ollama_base_url, timeout=5)
        response.raise_for_status() # Вызовет ошибку для статусов 4xx/5xx
        
        # Убедимся, что ответ содержит ожидаемый текст
        if "Ollama is running" in response.text:
            return {"status": "ok"}
        else:
            return {"status": "error", "details": "Unexpected response from Ollama root URL."}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "details": f"Connection to Ollama failed: {e}"}
    except Exception as e:
        return {"status": "error", "details": str(e)}