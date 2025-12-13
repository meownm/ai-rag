# Карта портов по сервисам

Ниже — сводная таблица открытых портов для основных сервисов проекта. Все значения указаны как порты хоста по умолчанию (при локальном запуске или в Docker) и не пересекаются между собой.

| Сервис | Порт(ы) хоста | Источник/примечание |
| --- | --- | --- |
| knowledge-search-api | 8000 (Docker Desktop), 8020 (локальный `poetry run uvicorn`) | `setup-docker-desktop.bat`, `knowledge-search-api/run.bat`, `knowledge-search-api/Dockerfile` |
| knowledge_base_api | 8001 | `knowledge_base_api/docker-compose.yml`, `knowledge_base_api/Dockerfile` |
| document-processor | 8010 | `document-processor/docker-compose.yml`, `document-processor/run.bat` |
| embedding_service (CPU/GPU) | 8101 / 8102 | `embedding_service/docker-compose.yml`, `embedding_service/run_server.bat` |
| universal_embedder | 8012 | `setup-docker-desktop.bat`, `universal_embedder/Dockerfile`, `universal_embedder/run.py` |
| rag-search-ui | 3010 | `rag-search-ui/vite.config.ts` |
| landing (vite demo) | 3020 | `landing/vite.config.ts` (обычно запускается отдельно от `rag-search-ui`) |
| rag_observability_stack | 6006 / 8787 / 7000 / 9090 / 3000 / 8080 | `rag_observability_stack/docker-compose.yml` (значения задаются через `.env`) |

> Если вы меняете конфигурацию портов вручную, убедитесь, что новые значения не пересекаются с указанными, чтобы избежать конфликтов при одновременном запуске сервисов.
