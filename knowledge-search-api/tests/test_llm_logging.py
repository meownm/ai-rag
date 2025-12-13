import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# Ensure imports resolve when running from repo root
sys.path.append(str(Path(__file__).resolve().parents[1]))

from llm_logging import log_llm_request


class _DummyCursor:
    def __init__(self):
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, sql, params=None):
        self.executed = (sql.strip(), params)


class _DummyDB:
    def __init__(self):
        self.cursor = _DummyCursor()

    def get_cursor(self, cursor_factory=None):  # noqa: ARG002
        return self.cursor


def test_log_llm_request_persists_metadata():
    db = _DummyDB()
    start = datetime(2024, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=2)

    log_llm_request(
        db,
        start_time=start,
        end_time=end,
        is_success=True,
        request_type="answer",
        model_name="test-model",
        prompt="Hello",
        raw_response="Hi",
        prompt_tokens=5,
        completion_tokens=7,
        tenant_id="t1",
        doc_id="d1",
        chunk_id=3,
    )

    assert db.cursor.executed is not None
    sql, params = db.cursor.executed
    assert "INSERT INTO llm_requests_log" in sql
    # duration_seconds column should match provided timestamps
    assert params[2] == pytest.approx(2.0)
    assert params[4] == "answer"
    assert params[5] == "test-model"
    assert params[6] == "Hello"
    assert params[7] == "Hi"
    assert params[8] is None  # no error message
    assert params[9] == 5
    assert params[10] == 7
    assert params[11] == "t1"
    assert params[12] == "d1"
    assert params[13] == 3
