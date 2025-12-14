from datetime import date, datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# --- DDL для таблиц, которые создает и которыми владеет этот сервис ---

HISTORY_TABLES_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    org_id TEXT,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS search_queries (
    id BIGSERIAL PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id TEXT,
    org_id TEXT,
    query TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS search_results (
    query_id BIGINT PRIMARY KEY REFERENCES search_queries(id) ON DELETE CASCADE,
    user_id TEXT,
    org_id TEXT,
    answer TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    citations JSONB,
    graph_context JSONB,
    graph_status TEXT,
    enrichment_used BOOLEAN,
    used_chunks INT,
    used_tokens INT,
    latency_ms INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS org_id TEXT;
ALTER TABLE search_queries ADD COLUMN IF NOT EXISTS org_id TEXT;
ALTER TABLE search_results ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE search_results ADD COLUMN IF NOT EXISTS org_id TEXT;
"""

# --- Модели для внутреннего использования ---


class RetrievedChunk(BaseModel):
    """
    Базовая модель для одного найденного фрагмента (чанка).
    """

    source_id: int
    doc_id: str
    chunk_id: int
    filename: str
    text: str
    score: float


class InternalChunk(RetrievedChunk):
    """
    Расширяет RetrievedChunk, добавляя поле metadata для внутреннего использования.
    """

    type: Optional[str] = None
    metadata: Optional[Dict] = None


# --- Модели для API ---


class HighlightedCitation(BaseModel):
    """
    Финальная модель цитаты для ответа API.
    """

    source_id: int
    doc_id: str
    chunk_id: int
    filename: str
    highlighted_text: str
    score: float


class Filters(BaseModel):
    """Модель для фильтров поиска."""

    space: Optional[List[str]] = None
    author: Optional[List[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    doc_type: Optional[List[str]] = None


class AnswerRequest(BaseModel):
    """Модель запроса для эндпоинта /v1/answer."""

    query: str
    conversation_id: Optional[str] = None
    stream: bool = Field(
        default=False,
        description="Если true, ответ будет передаваться потоком через SSE.",
    )
    mode: Literal["dense", "bm25", "hybrid", "graph", "hybrid+graph"] = Field(
        default="hybrid", description="Режим поиска."
    )
    context_mode: Literal["short", "long"] = Field(
        default="long", description="Режим контекста (пока не используется)."
    )
    graph_depth: int = Field(default=2, description="Глубина обхода графа знаний.")
    top_k: int = Field(
        default=10,
        description="Количество наиболее релевантных чанков для извлечения.",
    )
    filters: Optional[Filters] = None
    max_tokens: int = Field(
        default=2048,
        description="Максимальное количество токенов для сгенерированного ответа.",
    )


class AnswerResponse(BaseModel):
    """Модель ответа для не-стримингового режима эндпоинта /v1/answer."""

    answer: str
    conversation_id: str
    citations: List[HighlightedCitation]
    graph_context: Optional[List[Dict]] = None
    graph_status: str
    enrichment_used: bool
    used_chunks: int
    used_tokens: int
    latency_ms: int


# --- Модели для стриминга (SSE) ---


class StreamTextChunk(BaseModel):
    """Часть текстового ответа от LLM."""

    type: Literal["text"] = "text"
    content: str


class StreamMetadataChunk(BaseModel):
    """Финальный блок метаданных, отправляемый в конце потока."""

    type: Literal["metadata"] = "metadata"
    conversation_id: str
    citations: List[HighlightedCitation]
    graph_context: Optional[List[Dict]] = None
    graph_status: str
    enrichment_used: bool
    used_chunks: int
    used_tokens: int
    latency_ms: int


# --- Модели для API Истории ---


class ConversationInfo(BaseModel):
    """Краткая информация о диалоге для списка истории."""

    conversation_id: str
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime


class FullHistoryResponse(BaseModel):
    """Полный ответ для эндпоинта GET /v1/history/{query_id}."""

    query_id: int
    conversation_id: str
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    query: str
    answer: str
    success: bool
    citations: List[HighlightedCitation]
    graph_context: Optional[List[Dict]] = None
    graph_status: str
    enrichment_used: bool
    used_chunks: int
    used_tokens: int
    latency_ms: int
    created_at: datetime


class TokenIdentity(BaseModel):
    """Распакованные данные токена OIDC."""

    user_id: str
    org_id: Optional[str] = None
