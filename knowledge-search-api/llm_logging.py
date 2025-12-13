from datetime import datetime
from typing import Optional

from clients import PostgreSQLClient


def log_llm_request(
    db_client: PostgreSQLClient,
    *,
    start_time: datetime,
    end_time: Optional[datetime],
    is_success: bool,
    request_type: str,
    model_name: Optional[str],
    prompt: str,
    raw_response: Optional[str] = None,
    error_message: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    tenant_id: Optional[str] = None,
    doc_id: Optional[str] = None,
    chunk_id: Optional[int] = None,
) -> None:
    """Persists LLM call metadata into llm_requests_log without breaking the request flow."""

    if not db_client:
        return

    end_time = end_time or datetime.utcnow()
    duration = (end_time - start_time).total_seconds()

    try:
        with db_client.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_requests_log (
                    request_timestamp_start,
                    request_timestamp_end,
                    duration_seconds,
                    is_success,
                    request_type,
                    model_name,
                    prompt,
                    raw_response,
                    error_message,
                    prompt_tokens,
                    completion_tokens,
                    tenant_id,
                    doc_id,
                    chunk_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    start_time,
                    end_time,
                    duration,
                    is_success,
                    request_type,
                    model_name,
                    prompt,
                    raw_response,
                    error_message,
                    prompt_tokens,
                    completion_tokens,
                    tenant_id,
                    doc_id,
                    chunk_id,
                ),
            )
    except Exception as logging_error:  # noqa: BLE001
        print(f"Failed to log LLM request of type {request_type}: {logging_error}")

