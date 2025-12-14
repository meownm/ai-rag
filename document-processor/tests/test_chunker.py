import sys
from pathlib import Path

import pytest

TEST_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(TEST_ROOT))

from chunker import SmartChunker


def test_respects_paragraph_boundaries_and_lists_without_markers(monkeypatch):
    class DummyEncoder:
        def encode(self, text: str, disallowed_special=()):
            return text.split()

    monkeypatch.setattr("chunker.tiktoken.get_encoding", lambda name: DummyEncoder())

    chunker = SmartChunker(chunk_tokens=12, overlap_tokens=0, encoding="gpt2")
    chunker.enc = DummyEncoder()
    text = (
        "Вступительный абзац короткий.\n\n"
        "Первый пункт списка без маркера\n"
        "Второй пункт списка без маркера\n"
        "Третий пункт списка без маркера\n\n"
        "Заключительный абзац с выводами."
    )

    chunks = chunker._split_large_text_block(text, {"source": "test"})
    chunk_texts = [chunk["text"] for chunk in chunks]

    assert len(chunks) == 3
    assert chunk_texts[0].startswith("Вступительный абзац короткий")
    assert "Первый пункт списка без маркера" in chunk_texts[1]
    assert "Второй пункт списка без маркера" in chunk_texts[1]
    assert "Третий пункт списка без маркера" in chunk_texts[1]
    assert chunk_texts[2].startswith("Заключительный абзац")
    assert all(chunk["meta"].get("source") == "test" for chunk in chunks)


def test_table_row_grouping_and_overlap(monkeypatch):
    class DummyEncoder:
        def encode(self, text: str, disallowed_special=()):
            return text.split()

    monkeypatch.setattr("chunker.tiktoken.get_encoding", lambda name: DummyEncoder())

    chunker = SmartChunker(
        chunk_tokens=20,
        overlap_tokens=0,
        table_row_group_tokens=12,
        table_row_overlap=1,
        encoding="gpt2",
    )
    chunker.enc = DummyEncoder()

    table_text = "\n".join([
        "| H1 | H2 |",
        "| --- | --- |",
        "| r1 | c1 |",
        "| r2 | c2 |",
        "| r3 | c3 |",
        "| r4 | c4 |",
    ])

    chunks = chunker._handle_table(table_text, {"type": "table", "section": "Table 1"})
    assert len(chunks) == 3

    first_block_rows = chunks[0]["text"].split("\n")
    second_block_rows = chunks[1]["text"].split("\n")

    assert "| r1 | c1 |" in first_block_rows
    assert "| r2 | c2 |" in first_block_rows
    # r2 должна появиться и в следующем блоке благодаря overlap по строкам
    assert "| r2 | c2 |" in second_block_rows
    assert all(chunk["meta"].get("section") == "Table 1" for chunk in chunks)


def test_text_overlap_between_chunks(monkeypatch):
    class DummyEncoder:
        def encode(self, text: str, disallowed_special=()):
            return text.split()

    monkeypatch.setattr("chunker.tiktoken.get_encoding", lambda name: DummyEncoder())

    chunker = SmartChunker(chunk_tokens=5, overlap_tokens=2, doc_limit=0, encoding="gpt2")
    chunker.enc = DummyEncoder()

    sections = [
        {"text": "Первый абзац текста", "meta": {}},
        {"text": "Второй абзац длиннее", "meta": {}},
    ]

    chunks = chunker.split_document(sections)

    assert len(chunks) == 2

    first_chunk_text = chunks[0]["text"]
    second_chunk_text = chunks[1]["text"]

    assert sections[0]["text"] == first_chunk_text
    assert sections[0]["text"] in second_chunk_text
    assert sections[1]["text"] in second_chunk_text


def test_split_document_limits_token_recounts(monkeypatch):
    class DummyEncoder:
        def encode(self, text: str, disallowed_special=()):
            return text.split()

    call_count = 0

    def fake_count_tokens(self, text: str):
        nonlocal call_count
        call_count += 1
        return len(text.split())

    monkeypatch.setattr("chunker.tiktoken.get_encoding", lambda name: DummyEncoder())
    monkeypatch.setattr(SmartChunker, "count_tokens", fake_count_tokens)

    chunker = SmartChunker(chunk_tokens=5, overlap_tokens=2, doc_limit=0, encoding="gpt2")
    sections = [
        {"text": f"раздел {i}", "meta": {"type": "paragraph"}}
        for i in range(50)
    ]

    chunks = chunker.split_document(sections)

    assert chunks  # убедимся, что разбиение выполнено
    # должно быть не больше нескольких вызовов на секцию + базовые проверки документа
    assert call_count <= len(sections) + 10
