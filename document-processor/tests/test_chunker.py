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
