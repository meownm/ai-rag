"""Backfill worker that scans for chunks without embeddings and fills them using the configured model."""
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv
import requests
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("embedding_backfill_worker")


@dataclass
class EmbeddingConfig:
    model_name: str
    version: int
    dimension: Optional[int] = None
    mode: str = "local"  # local | api
    api_base: Optional[str] = None


class EmbeddingBackfillWorker:
    def __init__(
        self,
        poll_interval: int = 5,
        batch_size: int = 64,
        conn_dsn: Optional[str] = None,
    ) -> None:
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.conn_dsn = conn_dsn or self._build_dsn_from_env()
        self.worker_id = f"backfill-{uuid.uuid4().hex[:6]}"

        self._model: Optional[Any] = None
        self._config: Optional[EmbeddingConfig] = None

    def _build_dsn_from_env(self) -> str:
        env_dsn = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_DSN")
        if env_dsn:
            return env_dsn

        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "postgres")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"

    def _connect(self):
        return psycopg2.connect(self.conn_dsn, cursor_factory=DictCursor)

    def _load_config(self, conn) -> EmbeddingConfig:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = 'embedding_config';")
            row = cur.fetchone()
            if not row or not row[0]:
                raise RuntimeError("Нет записи embedding_config в таблице settings")

            raw_value: Dict[str, Any] = row[0]

        model_name = raw_value.get("model_name")
        version = raw_value.get("version")
        if not model_name or not isinstance(version, int):
            raise RuntimeError("В embedding_config отсутствуют model_name или version")

        mode = raw_value.get("mode") or raw_value.get("model_type") or "local"
        api_base = raw_value.get("api_base")
        dimension = raw_value.get("dimension")
        return EmbeddingConfig(
            model_name=model_name,
            version=version,
            dimension=dimension if isinstance(dimension, int) else None,
            mode=str(mode).lower(),
            api_base=api_base,
        )

    def _ensure_model(self, config: EmbeddingConfig) -> Any:
        if self._model and self._config and self._config.model_name == config.model_name and self._config.mode == config.mode:
            return self._model

        if config.mode == "api":
            api_base = config.api_base or os.getenv("EMBEDDING_API_BASE")
            if not api_base:
                raise RuntimeError("Для режима api требуется api_base в settings или EMBEDDING_API_BASE")
            self._model = {"api_base": api_base, "model_name": config.model_name, "mode": "api"}
            logger.info("Загружена конфигурация API эмбеддингов: %s", api_base)
            return self._model

        device = "cpu"
        try:
            from torch import cuda  # type: ignore

            if cuda.is_available():
                device = "cuda"
        except Exception:  # noqa: BLE001
            device = "cpu"

        logger.info("Загрузка модели %s на устройство %s", config.model_name, device)
        self._model = SentenceTransformer(config.model_name, device=device)
        return self._model

    def _capture_batch(self, conn, config: EmbeddingConfig) -> List[Dict[str, Any]]:
        processing_status = json.dumps(
            {
                "status": "processing",
                "processor": self.worker_id,
                "model": config.model_name,
                "started_at": time.time(),
            }
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH target AS (
                    SELECT doc_id, chunk_id, text, tenant_id
                    FROM chunks
                    WHERE (embedding IS NULL OR embedding_version < %s)
                    ORDER BY doc_id, chunk_id
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE chunks c
                SET enrichment_status = jsonb_set(coalesce(c.enrichment_status, '{}'::jsonb), '{embedding_generation}', %s::jsonb, true)
                FROM target t
                WHERE c.doc_id = t.doc_id AND c.chunk_id = t.chunk_id
                RETURNING t.doc_id, t.chunk_id, t.text, t.tenant_id;
                """,
                (config.version, self.batch_size, processing_status),
            )
            rows = cur.fetchall()
            conn.commit()
        return [dict(row) for row in rows]

    def _embed_batch(self, texts: Sequence[str], model: Any, config: EmbeddingConfig) -> List[List[float]]:
        if not texts:
            return []

        if isinstance(model, dict) and model.get("mode") == "api":
            api_base = model["api_base"]
            payload = {"model": model["model_name"], "input": list(texts)}
            response = requests.post(f"{api_base}/embeddings", json=payload, timeout=60)
            response.raise_for_status()
            data = response.json().get("data", [])
            data_sorted = sorted(data, key=lambda d: d.get("index", 0))
            return [item["embedding"] for item in data_sorted]

        embeddings = model.encode(list(texts), batch_size=self.batch_size, show_progress_bar=False)
        return [vec.tolist() for vec in embeddings]

    def _mark_failed(self, conn, batch: List[Dict[str, Any]], config: EmbeddingConfig, error: str) -> None:
        failed_status = json.dumps(
            {
                "status": "failed",
                "processor": self.worker_id,
                "model": config.model_name,
                "error": error,
                "failed_at": time.time(),
            }
        )
        with conn.cursor() as cur:
            for item in batch:
                cur.execute(
                    """
                    UPDATE chunks
                    SET enrichment_status = jsonb_set(coalesce(enrichment_status, '{}'::jsonb), '{embedding_generation}', %s::jsonb, true)
                    WHERE doc_id = %s AND chunk_id = %s;
                    """,
                    (failed_status, item["doc_id"], item["chunk_id"]),
                )
            conn.commit()

    def _save_embeddings(self, conn, batch: List[Dict[str, Any]], embeddings: List[List[float]], config: EmbeddingConfig) -> None:
        completed_status = json.dumps(
            {
                "status": "completed",
                "processor": self.worker_id,
                "model": config.model_name,
                "completed_at": time.time(),
            }
        )
        with conn.cursor() as cur:
            for item, vector in zip(batch, embeddings):
                vector_literal = "[" + ",".join(str(v) for v in vector) + "]"
                cur.execute(
                    """
                    UPDATE chunks
                    SET embedding = %s::vector,
                        embedding_version = %s,
                        enrichment_status = jsonb_set(coalesce(enrichment_status, '{}'::jsonb), '{embedding_generation}', %s::jsonb, true)
                    WHERE doc_id = %s AND chunk_id = %s;
                    """,
                    (
                        vector_literal,
                        config.version,
                        completed_status,
                        item["doc_id"],
                        item["chunk_id"],
                    ),
                )
            conn.commit()

    def run_once(self) -> bool:
        with self._connect() as conn:
            conn.autocommit = False
            config = self._load_config(conn)
            if not self._config or self._config != config:
                self._config = config
                self._model = None
            model = self._ensure_model(config)
            batch = self._capture_batch(conn, config)
            if not batch:
                return False

            texts = [item["text"] for item in batch]
            try:
                embeddings = self._embed_batch(texts, model, config)
                if len(embeddings) != len(batch):
                    raise RuntimeError("Количество эмбеддингов не совпадает с количеством чанков")
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка при генерации эмбеддингов: %s", exc, exc_info=True)
                self._mark_failed(conn, batch, config, str(exc))
                return True

            self._save_embeddings(conn, batch, embeddings, config)
            logger.info("Записан батч из %s чанков", len(batch))
            return True

    def run_forever(self) -> None:
        logger.info(
            "Старт воркера %s с dsn=%s, poll=%ss, batch=%s",
            self.worker_id,
            self.conn_dsn,
            self.poll_interval,
            self.batch_size,
        )
        while True:
            try:
                processed = self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.critical("Критическая ошибка в цикле: %s", exc, exc_info=True)
                processed = False
            if not processed:
                time.sleep(self.poll_interval)


def main() -> None:
    poll_interval = int(os.getenv("BACKFILL_POLL_INTERVAL", "5"))
    batch_size = int(os.getenv("BACKFILL_BATCH_SIZE", "64"))
    worker = EmbeddingBackfillWorker(poll_interval=poll_interval, batch_size=batch_size)
    worker.run_forever()


if __name__ == "__main__":
    main()
