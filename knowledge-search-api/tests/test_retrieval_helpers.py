import sys
from pathlib import Path
import types

import pytest

# Light stubs to avoid heavy model imports during unit tests
if "sentence_transformers" not in sys.modules:
    SentenceTransformerStub = type("SentenceTransformer", (), {})
    CrossEncoderStub = type("CrossEncoder", (), {})
    sys.modules["sentence_transformers"] = types.SimpleNamespace(
        SentenceTransformer=SentenceTransformerStub,
        CrossEncoder=CrossEncoderStub,
    )

# Ensure imports resolve when running from repo root
sys.path.append(str(Path(__file__).resolve().parents[1]))

from retrieval import (
    _build_filter_clause,
    _build_indexing_guard,
    _build_ollama_embedding_endpoint,
    _post_process_chunks,
)
from schemas import Filters


class _DummyCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed_sql = None
        self.executed_params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params

    def fetchall(self):
        return self._rows


class _DummyDBClient:
    def __init__(self, rows):
        self._rows = rows

    def get_cursor(self, cursor_factory=None):  # noqa: ARG002
        return _DummyCursor(self._rows)


def test_build_filter_clause_with_doc_ids_and_filters():
    filters = Filters(author=["Ivan"], doc_type=["pdf", ".doc"])
    clause, params = _build_filter_clause(filters, doc_ids=["doc1", "doc2"])

    assert clause == (
        "WHERE c.doc_id = ANY(%s) AND d.author ILIKE ANY(%s) "
        "AND (d.filename ILIKE %s OR d.filename ILIKE %s)"
    )
    assert params == [["doc1", "doc2"], ("Ivan",), "%.pdf", "%.doc"]


    def test_build_indexing_guard_appends_readiness_checks():
        clause, params = _build_indexing_guard("WHERE c.doc_id = ANY(%s)", ["doc1"], embedding_version=2)
        assert "c.embedding IS NOT NULL" in clause
        assert "upper(coalesce(c.enrichment_status->'embedding_generation'->>'status','')) = 'COMPLETED'" in clause
        assert clause.endswith("c.embedding_version = %s")
        assert params == ["doc1", 2]

    empty_clause, empty_params = _build_indexing_guard("", [], embedding_version=None)
    assert empty_clause.startswith("WHERE ")
    assert empty_params == []


def test_build_ollama_embedding_endpoint_removes_generate_suffix():
    assert _build_ollama_embedding_endpoint("http://localhost:11434/api/generate") == "http://localhost:11434/api/embeddings"
    assert _build_ollama_embedding_endpoint("http://ollama:11434") == "http://ollama:11434/api/embeddings"


def test_post_process_chunks_reconstructs_table_once():
    rows = [
        {"text": "Name: John, Age: 30", "type": "table_row"},
        {"text": "Name: Jane, Age: 25", "type": "table_row"},
    ]
    db_client = _DummyDBClient(rows)

    class DummyChunk:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    table_chunk = DummyChunk(
        source_id=1,
        doc_id="doc123",
        chunk_id=10,
        filename="report.csv",
        text="stub",
        score=0.5,
        type="table_part",
        section="Section1",
    )

    text_chunk = DummyChunk(
        source_id=2,
        doc_id="doc123",
        chunk_id=11,
        filename="report.csv",
        text="Regular paragraph",
        score=0.4,
        type="paragraph",
    )

    processed = _post_process_chunks(db_client, [table_chunk, text_chunk])
    assert len(processed) == 2
    reconstructed = processed[0]
    assert "Из таблицы" in reconstructed.text
    assert "| Name | Age |" in reconstructed.text
    assert reconstructed.block_type == "reconstructed_table"
    assert processed[1].text == "Regular paragraph"
