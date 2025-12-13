# clients.py
import os
import psycopg2
import psycopg2.extras
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from typing import Optional
from contextlib import contextmanager  # <-- ИСПРАВЛЕНИЕ: Добавлен этот импорт

class PostgreSQLClient:
    """Клиент для работы с базой данных PostgreSQL."""
    def __init__(self, db_params: dict):
        self.db_params = db_params
        self.conn = None
        try:
            self.conn = psycopg2.connect(**self.db_params)
            print("DB: Успешное подключение к PostgreSQL.")
        except psycopg2.OperationalError as e:
            print(f"DB: КРИТИЧЕСКАЯ ОШИБКА подключения к PostgreSQL: {e}")
            raise

    def close(self):
        if self.conn:
            self.conn.close()
            print("PostgreSQL: Соединение успешно закрыто.")

    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """
        Контекстный менеджер для работы с курсором и автоматического
        управления транзакциями.
        """
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(**self.db_params)

        cursor = self.conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            self.conn.commit()
        except Exception as e:
            print(f"DB Transaction Error: {e}. Rolling back...")
            self.conn.rollback()
            raise
        finally:
            cursor.close()
            
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

def load_embedding_model(model_name: str) -> SentenceTransformer:
    """Загружает и кэширует embedding-модель."""
    print(f"Загружаю embedding модель: {model_name} (это может занять время)...")
    model = SentenceTransformer(model_name)
    print("Embedding-модель успешно загружена.")
    return model