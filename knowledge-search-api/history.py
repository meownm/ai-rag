# history.py
#
# Финальная, исправленная версия. Устранен NameError (использование db_client вместо db).
# -------------------------------------------------------------------------------------
import uuid
import json
from typing import List, Dict, Optional
import psycopg2.extras
from datetime import datetime

from clients import PostgreSQLClient
from schemas import AnswerResponse

def get_or_create_conversation(
    db: PostgreSQLClient,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    first_query: Optional[str] = None
) -> str:
    if conversation_id:
        return conversation_id

    new_conv_id = str(uuid.uuid4())
    title = (first_query[:100] + '...') if first_query and len(first_query) > 100 else first_query
    
    # ИСПРАВЛЕНО: db_client -> db
    with db.get_cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (%s, %s, %s)",
            (new_conv_id, user_id, title)
        )
    print(f"Создан новый диалог: {new_conv_id}")
    return new_conv_id

def get_conversation_history(db: PostgreSQLClient, conversation_id: str) -> List[Dict]:
    history = []
    if not conversation_id:
        return history
        
    query = "SELECT q.query, r.answer FROM search_queries q JOIN search_results r ON q.id = r.query_id WHERE q.conversation_id = %s ORDER BY q.created_at ASC;"
    
    # ИСПРАВЛЕНО: db_client -> db
    with db.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(query, (conversation_id,))
        rows = cur.fetchall()
        for row in rows:
            history.append({"query": row['query'], "answer": row['answer']})
    return history

def save_search_result(
    db: PostgreSQLClient,
    conv_id: str,
    query: str,
    response: AnswerResponse,
    citations_json: list,
    success: bool
):
    # ИСПРАВЛЕНО: db_client -> db
    with db.get_cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO search_queries (conversation_id, query) VALUES (%s, %s) RETURNING id",
                (conv_id, query)
            )
            query_id = cur.fetchone()[0]
            
            cur.execute(
                """
                INSERT INTO search_results (
                    query_id, answer, success, citations, graph_context, graph_status,
                    enrichment_used, used_chunks, used_tokens, latency_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    query_id, response.answer, success,
                    json.dumps(citations_json, ensure_ascii=False),
                    json.dumps(response.graph_context, ensure_ascii=False) if response.graph_context else None,
                    response.graph_status, response.enrichment_used,
                    response.used_chunks, response.used_tokens, response.latency_ms
                )
            )
            print(f"Результат для query_id {query_id} успешно сохранен в историю.")
        except Exception as e:
            # get_cursor сам обработает rollback
            print(f"Ошибка при сохранении истории: {e}")
            raise

def get_history_list_for_user(db: PostgreSQLClient, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
    history = []
    query = """
        SELECT DISTINCT ON (c.id)
            c.id as conversation_id, c.user_id, c.title, q.created_at
        FROM conversations c
        JOIN search_queries q ON c.id = q.conversation_id
        WHERE c.user_id = %s
        ORDER BY c.id, q.created_at DESC
        LIMIT %s OFFSET %s;
    """
    # ИСПРАВЛЕНО: db_client -> db
    with db.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(query, (user_id, limit, offset))
        rows = cur.fetchall()
        for row in rows:
            history.append(dict(row))
    return history

def get_full_history_by_query_id(db: PostgreSQLClient, query_id: int) -> Optional[Dict]:
    query = """
        SELECT
            q.id as query_id, q.conversation_id, q.user_id, q.query,
            r.answer, r.success, r.citations, r.graph_context, r.graph_status,
            r.enrichment_used, r.used_chunks, r.used_tokens, r.latency_ms, r.created_at
        FROM search_queries q
        JOIN search_results r ON q.id = r.query_id
        WHERE q.id = %s;
    """
    # ИСПРАВЛЕНО: db_client -> db
    with db.get_cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(query, (query_id,))
        row = cur.fetchone()
        return dict(row) if row else None