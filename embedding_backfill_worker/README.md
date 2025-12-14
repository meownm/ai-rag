# Embedding Backfill Worker

Этот воркер периодически просматривает таблицу `chunks` и достраивает эмбеддинги для всех записей, у которых `embedding` отсутствует или версия эмбеддинга меньше значения из `settings.embedding_config`. Статус в поле `enrichment_status.embedding_generation.status` сохраняется в верхнем регистре (`COMPLETED`/`FAILED`), чтобы быть совместимым с пайплайнами индексации и поисковыми фильтрами.

## Настройки
- **DB подключения**: через `POSTGRES_DSN`/`DATABASE_DSN` или набор переменных `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- **Периодичность и батч**: `BACKFILL_POLL_INTERVAL` (по умолчанию `5` секунд) и `BACKFILL_BATCH_SIZE` (по умолчанию `64`).
- **Модель и генератор**: берётся из `settings` (`embedding_config`). Поддерживаются режимы `local` (SentenceTransformer) и `api` (совместимый с OpenAI `/embeddings` или Ollama `/api/embeddings`). В конфиге сохраняется ключ `generator` (`service` или `ollama`); для API-режима можно задать `api_base` в конфиге или переменной `EMBEDDING_API_BASE`.

## Запуск
```bash
poetry install
poetry run python worker.py
```
