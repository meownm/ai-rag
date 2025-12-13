#!/bin/bash
# scripts/run-dev.sh
# Запускает dev-сервер с автоматической перезагрузкой.

echo "Запуск сервиса в режиме разработки..."
echo "API будет доступен по адресу http://127.0.0.1:8100"
echo "Документация Swagger UI: http://127.0.0.1:8100/docs"

# Запускаем uvicorn через poetry, чтобы использовать правильное окружение
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8100