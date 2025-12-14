# clients.py
#
# Версия 3.7.1: Исправлена ошибка приведения типов в массовом UPDATE (uuid = text).
# --------------------------------------------------------------------------

import logging
import os
import time
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

import psycopg2
import psycopg2.extras
from minio import Minio
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from db_schema import initialize_database_schema

load_dotenv()

class DatabaseClient:
    """Клиент для работы с PostgreSQL."""
    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
                dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD")
            )
            register_vector(self.conn)
            logging.info("DB: Успешное подключение к PostgreSQL и регистрация pgvector.")
            initialize_database_schema(self.conn)
        except psycopg2.OperationalError as e:
            logging.critical(f"DB: КРИТИЧЕСКАЯ ОШИБКА подключения к PostgreSQL: {e}", exc_info=True)
            raise

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()
            logging.info("DB: Соединение с PostgreSQL успешно закрыто.")

    def _reconnect(self):
        """Попытка переподключения к базе данных."""
        logging.warning("DB: Попытка переподключения к базе данных...")
        self.close()
        time.sleep(5)
        self.__init__()

    def find_next_task_by_operation(self, operation: str) -> Optional[Dict[str, Any]]:
        query = "SELECT id, item_uuid, tenant_id, user_id, item_name, operation, s3_path FROM public.knowledge_events WHERE status = 'new' AND operation = %s ORDER BY operation_time ASC LIMIT 1 FOR UPDATE SKIP LOCKED;"
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query, (operation,))
                task = cur.fetchone()
                return dict(task) if task else None
        except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
            logging.error(f"DB: Потеряно соединение с БД при поиске задачи. {e}")
            self._reconnect()
            return None

    def get_chunks_for_enrichment(self, stage: str, batch_size: int) -> List[Dict]:
        now_str = datetime.utcnow().isoformat()
        query = f"""
            UPDATE chunks c
            SET enrichment_status = jsonb_set(
                c.enrichment_status,
                '{{{stage}}}',
                '{{"status": "processing", "updated_at": "{now_str}"}}'::jsonb,
                true
            )
            FROM (
                SELECT ct.doc_id, ct.chunk_id
                FROM chunks ct
                WHERE ct.enrichment_status -> '{stage}' ->> 'status' = 'pending'
                LIMIT %s FOR UPDATE SKIP LOCKED
            ) AS selected
            WHERE c.doc_id = selected.doc_id AND c.chunk_id = selected.chunk_id
            RETURNING c.doc_id, c.chunk_id, c.tenant_id, c.text;
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, (batch_size,))
            chunks = cur.fetchall()
            self.conn.commit()
            return [dict(c) for c in chunks]

    def document_exists(self, doc_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM documents WHERE doc_id = %s;", (doc_id,))
            return cur.fetchone() is not None

    def update_task_status(self, task_id: int, status: str, content: Optional[str] = None):
        with self.conn.cursor() as cur:
            cur.execute("UPDATE public.knowledge_events SET status = %s, content = %s WHERE id = %s;", (status, content, task_id))
            self.conn.commit()

    def update_chunk_enrichment_status(self, doc_id: str, chunk_id: int, stage: str, status: str, result: Optional[dict] = None, error: Optional[str] = None):
        now = datetime.utcnow().isoformat()
        status_obj = json.dumps({"status": status, "updated_at": now, "error_message": error})
        
        if result and not result.get("error"):
            metadata_update = json.dumps({f"llm_{stage}": result})
            query = "UPDATE chunks SET metadata = metadata || %s::jsonb, enrichment_status = jsonb_set(enrichment_status, %s, %s::jsonb, true) WHERE doc_id = %s AND chunk_id = %s;"
            params = (metadata_update, f'{{{stage}}}', status_obj, doc_id, chunk_id)
        else:
            query = "UPDATE chunks SET enrichment_status = jsonb_set(enrichment_status, %s, %s::jsonb, true) WHERE doc_id = %s AND chunk_id = %s;"
            params = (f'{{{stage}}}', status_obj, doc_id, chunk_id)

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            self.conn.commit()
            
    def delete_document_cascade(self, doc_id: str):
        """Полностью удаляет документ и все его чанки (через ON DELETE CASCADE)."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE doc_id = %s;", (doc_id,))
            self.conn.commit()
            logging.info(f"DB: Документ doc_id={doc_id} и связанные чанки удалены.")

    def create_document_and_chunks(self, doc_id, tenant_id, owner_user_id, filename, doc_properties, chunks):
        """
        Атомарно создает запись о документе и все его чанки (БЕЗ ЭМБЕДДИНГОВ) в одной транзакции.
        Эмбеддинги будут сгенерированы и добавлены позже фоновым процессом.
        """
        with self.conn.cursor() as cur:
            try:
                cur.execute(
                    """INSERT INTO documents (doc_id, tenant_id, owner_user_id, filename, title, author, metadata) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s);""",
                    (doc_id, tenant_id, owner_user_id, filename, doc_properties.get('title'), doc_properties.get('author'), json.dumps(doc_properties))
                )

                if chunks:
                    initial_status = {
                        "embedding_generation": {"status": "pending"},
                        "metadata_extraction": {"status": "pending"}
                    }
                    if os.getenv("NEO4J_ENABLED", "false").lower() == 'true':
                        initial_status["relation_extraction"] = {"status": "pending"}
                    
                    chunk_data_tuples = [
                        (
                            c['doc_id'], c['chunk_id'], c['tenant_id'],
                            c.get('section'), c.get('type'), c.get('block_type'),
                            c['text'], json.dumps(c.get('metadata', {}), ensure_ascii=False),
                            json.dumps(initial_status)
                        )
                        for c in chunks
                    ]

                    psycopg2.extras.execute_values(
                        cur,
                        "INSERT INTO chunks (doc_id, chunk_id, tenant_id, section, type, block_type, text, metadata, enrichment_status) VALUES %s;",
                        chunk_data_tuples
                    )
                
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logging.error(f"DB: Ошибка при атомарном создании документа {doc_id}. Транзакция отменена. Ошибка: {e}")
                raise
    
    def update_chunk_embeddings_and_status(self, chunks_with_embeddings: List[Dict], model_version: int):
        """
        Выполняет массовое обновление эмбеддингов и статуса для обработанного батча чанков.
        """
        now = datetime.utcnow().isoformat()
        status_obj_str = json.dumps({"status": "completed", "updated_at": now})

        update_data = [
            (
                chunk['embedding'] if isinstance(chunk['embedding'], list) else chunk['embedding'].tolist(),
                model_version,
                status_obj_str,
                chunk['doc_id'],
                chunk['chunk_id']
            )
            for chunk in chunks_with_embeddings if 'embedding' in chunk
        ]
        
        if not update_data:
            logging.warning("Нет данных для обновления эмбеддингов.")
            return

        with self.conn.cursor() as cur:
            try:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    UPDATE chunks SET
                        embedding = data.embedding,
                        embedding_version = data.embedding_version,
                        enrichment_status = jsonb_set(enrichment_status, '{embedding_generation}', data.status::jsonb)
                    FROM (VALUES %s) AS data (embedding, embedding_version, status, doc_id, chunk_id)
                    -- <<< ИСПРАВЛЕНИЕ: Добавлено явное приведение типа к UUID, чтобы избежать ошибки.
                    WHERE chunks.doc_id = data.doc_id::uuid AND chunks.chunk_id = data.chunk_id;
                    """,
                    update_data,
                    page_size=len(update_data)
                )
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logging.error(f"DB: Ошибка при массовом обновлении эмбеддингов. Транзакция отменена. Ошибка: {e}")
                raise

    def log_llm_request(self, log_data: Dict):
        query = "INSERT INTO llm_requests_log (request_timestamp_start, request_timestamp_end, duration_seconds, is_success, request_type, model_name, prompt, raw_response, error_message, prompt_tokens, completion_tokens, tenant_id, doc_id, chunk_id) VALUES (%(start_time)s, %(end_time)s, %(duration)s, %(is_success)s, %(request_type)s, %(model_name)s, %(prompt)s, %(raw_response)s, %(error_message)s, %(prompt_tokens)s, %(completion_tokens)s, %(tenant_id)s, %(doc_id)s, %(chunk_id)s);"
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, log_data)
                self.conn.commit()
        except Exception as e:
            logging.error(f"DB: Не удалось записать лог LLM-запроса в базу данных! Ошибка: {e}", exc_info=True)
            self.conn.rollback()

class MinioClient:
    def __init__(self):
        try:
            self.client = Minio(os.getenv("MINIO_ENDPOINT"), access_key=os.getenv("MINIO_ACCESS_KEY"), secret_key=os.getenv("MINIO_SECRET_KEY"), secure=False)
            self.bucket_name = os.getenv("MINIO_BUCKET_NAME")
            if not self.client.bucket_exists(self.bucket_name):
                 raise ConnectionError(f"Бакет '{self.bucket_name}' не найден в MinIO!")
            logging.info("MinIO: Успешное подключение.")
        except Exception as e:
            logging.critical(f"MinIO: КРИТИЧЕСКАЯ ОШИБКА подключения: {e}", exc_info=True)
            raise

    def download_file_by_path(self, object_path: str) -> str:
        """Скачивает файл по полному пути объекта (без имени бакета)."""
        filename = os.path.basename(object_path)
        local_path = f"./temp_{uuid.uuid4()}_{filename}" 
        logging.info(f"MinIO: Загрузка объекта: {self.bucket_name}/{object_path}")
        self.client.fget_object(self.bucket_name, object_path, local_path)
        return local_path

class Neo4jClient:
    ALLOWED_NODE_LABELS = {"PERSON", "ORGANIZATION", "LOCATION", "DATE", "PRODUCT", "EVENT", "CONCEPT", "ENTITY"}

    def __init__(self, uri, user, password):
        self.driver: Optional[GraphDatabase.driver] = None
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
            logging.info("Neo4j: Успешное подключение.")
        except Exception as e:
            logging.error(f"Neo4j: КРИТИЧЕСКАЯ ОШИБКА подключения: {e}", exc_info=True)
            self.driver = None

    def close(self):
        if self.driver is not None:
            self.driver.close()
            logging.info("Neo4j: Соединение успешно закрыто.")
    
    def add_structured_relations(self, relations: list, tenant_id: str, doc_id: str):
        if not self.driver or not relations: return
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                for rel in relations:
                    s_type = rel.get('subject_type', 'ENTITY').upper()
                    o_type = rel.get('object_type', 'ENTITY').upper()
                    r_type = rel.get('relation', 'RELATED_TO').replace(" ", "_").upper()
                    r_type = ''.join(c for c in r_type if c.isalnum() or c == '_')

                    query = (f"MERGE (s:{s_type} {{name: $s_name, tenant_id: $tenant_id}}) ON CREATE SET s.doc_id = $doc_id "
                             f"MERGE (o:{o_type} {{name: $o_name, tenant_id: $tenant_id}}) ON CREATE SET o.doc_id = $doc_id "
                             f"MERGE (s)-[r:{r_type}]->(o)")
                    tx.run(query, s_name=str(rel.get('subject')).strip(), o_name=str(rel.get('object')).strip(), tenant_id=tenant_id, doc_id=doc_id)
            logging.info(f"Neo4j: [{doc_id}] Добавлено/обновлено {len(relations)} отношений в граф.")

    def delete_by_doc_id(self, doc_id: str, tenant_id: str):
        if not self.driver: return
        with self.driver.session() as session:
            session.run("MATCH (n {doc_id: $doc_id, tenant_id: $tenant_id}) DETACH DELETE n", doc_id=doc_id, tenant_id=tenant_id)
        logging.info(f"Neo4j: Удалены данные для doc_id={doc_id}, tenant_id={tenant_id}")