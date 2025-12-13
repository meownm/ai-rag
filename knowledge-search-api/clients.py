# clients.py
import os
import psycopg2
import psycopg2.extras
import psycopg2.pool
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from typing import Optional
from contextlib import contextmanager

class PostgreSQLClient:
    """Клиент для работы с базой данных PostgreSQL."""

    def __init__(self, db_params: dict):
        self.db_params = db_params
        self.pool: psycopg2.pool.ThreadedConnectionPool | None = None
        self._init_pool()

    def _init_pool(self):
        max_connections = int(os.getenv("DB_MAX_CONNECTIONS", "10"))
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=max_connections,
                **self.db_params,
            )
            print("DB: Успешное подключение к PostgreSQL через пул.")
        except psycopg2.OperationalError as e:
            print(f"DB: КРИТИЧЕСКАЯ ОШИБКА подключения к PostgreSQL: {e}")
            raise

    def close(self):
        if self.pool:
            self.pool.closeall()
            print("PostgreSQL: Все соединения пула закрыты.")

    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """
        Контекстный менеджер для работы с курсором и автоматического
        управления транзакциями.
        """
        if not self.pool or self.pool.closed:
            self._init_pool()

        conn = self.pool.getconn()
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            print(f"DB Transaction Error: {e}. Rolling back...")
            conn.rollback()
            raise
        finally:
            cursor.close()
            self.pool.putconn(conn)
            
class Neo4jClient:
    """Клиент для работы с графовой базой данных Neo4j."""
    def __init__(self, uri, user, password):
        self.driver: Optional[GraphDatabase.driver] = None
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
            print("Neo4j: Успешное подключение.")
        except Exception as e:
            print(f"Neo4j: ОШИБКА подключения: {e}. Функционал графа будет отключен.")
            self.driver = None

    def close(self):
        if self.driver is not None:
            self.driver.close()
            print("Neo4j: Соединение успешно закрыто.")

def load_embedding_model(model_name: str, device: str | None = None) -> SentenceTransformer:
    """Загружает и кэширует embedding-модель."""
    device_to_use = device or "cpu"
    print(
        f"Загружаю embedding модель: {model_name} на устройство {device_to_use} (это может занять время)..."
    )
    model = SentenceTransformer(model_name, device=device_to_use)
    print("Embedding-модель успешно загружена.")
    return model