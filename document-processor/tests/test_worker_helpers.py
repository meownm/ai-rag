import sys
from pathlib import Path
import logging
import types

import pytest

# Stub heavy dependencies before importing the worker module
sys.modules.setdefault("sentence_transformers", types.SimpleNamespace(SentenceTransformer=type("SentenceTransformer", (), {})))

# Override shared module name used by sibling services to avoid cross-import
sys.modules["clients"] = types.SimpleNamespace(
    DatabaseClient=type("DatabaseClient", (), {}),
    MinioClient=type("MinioClient", (), {}),
    Neo4jClient=type("Neo4jClient", (), {}),
)

class _FakeCuda:
    class OutOfMemoryError(RuntimeError):
        pass

    @staticmethod
    def empty_cache():
        return None


fake_torch = types.SimpleNamespace(cuda=_FakeCuda())
sys.modules.setdefault("torch", fake_torch)

sys.modules.setdefault(
    "prometheus_client",
    types.SimpleNamespace(
        Counter=lambda *args, **kwargs: lambda *cargs, **ckwargs: None,
        Histogram=lambda *args, **kwargs: lambda *cargs, **ckwargs: None,
    ),
)

# Ensure local worker module is resolved before similarly named modules in sibling services
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker import (
    normalize_text_block,
    enrich_blocks_with_hierarchy,
    _generate_embeddings_api,
    generate_embeddings,
    get_logger_adapter,
)


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _StubLogger(logging.LoggerAdapter):
    def __init__(self):
        super().__init__(logging.getLogger("test"), {})

    def process(self, msg, kwargs):
        return msg, kwargs


@pytest.fixture
def stub_logger():
    return get_logger_adapter(logging.getLogger("test"))


def test_normalize_text_block_removes_hyphen_breaks():
    raw = "Hello-\nworld\n\nAnother\nline"
    assert normalize_text_block(raw) == "Helloworld\n\nAnother line"


def test_enrich_blocks_with_hierarchy_adds_context_paths():
    blocks = [
        {"type": "heading", "level": 1, "text": "Chapter"},
        {"type": "paragraph", "text": "Content"},
        {"type": "heading", "level": 2, "text": "Section"},
        {"type": "paragraph", "text": "More content"},
    ]

    result = enrich_blocks_with_hierarchy(blocks)
    assert result[1]["metadata"]["context_path"] == ["Chapter"]
    assert result[3]["metadata"]["context_path"] == ["Chapter", "Section"]


def test_generate_embeddings_api_with_service(monkeypatch, stub_logger):
    called_payloads = []

    def _fake_request(endpoint, payload):  # noqa: ARG001
        called_payloads.append(payload)
        return _StubResponse({"data": [{"index": 1, "embedding": [0.2, 0.3]}, {"index": 0, "embedding": [0.0, 0.1]}]})

    monkeypatch.setattr("worker._make_embedding_api_request", _fake_request)

    embeddings = _generate_embeddings_api(
        ["text a", "text b"],
        {"api_base": "http://api", "model_name": "model", "generator": "service"},
        stub_logger,
    )

    assert called_payloads == [{"model": "model", "input": ["text a", "text b"]}]
    assert embeddings == [[0.0, 0.1], [0.2, 0.3]]


def test_generate_embeddings_api_with_ollama(monkeypatch, stub_logger):
    requested_prompts = []

    def _fake_request(endpoint, payload):  # noqa: ARG001
        requested_prompts.append(payload["prompt"])
        return _StubResponse({"embedding": [1.0, 2.0, 3.0]})

    monkeypatch.setattr("worker._make_embedding_api_request", _fake_request)

    embeddings = _generate_embeddings_api(
        ["first", "second"],
        {"api_base": "http://ollama:11434", "model_name": "llama", "generator": "ollama"},
        stub_logger,
    )

    assert requested_prompts == ["first", "second"]
    assert embeddings == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]


def test_generate_embeddings_assigns_results_to_chunks(monkeypatch, stub_logger):
    outputs = [[0.1, 0.2], [0.3, 0.4]]

    def _fake_api(texts, api_config, logger):  # noqa: ARG002
        return outputs

    monkeypatch.setattr("worker._generate_embeddings_api", _fake_api)

    chunks = [
        {"text": "first"},
        {"text": "second"},
    ]

    generate_embeddings(chunks, {"mode": "api", "api_base": "http://api", "model_name": "m"}, stub_logger)

    assert chunks[0]["embedding"] == [0.1, 0.2]
    assert chunks[1]["embedding"] == [0.3, 0.4]
