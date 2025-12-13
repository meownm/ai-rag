#!/bin/sh

# Выходим сразу, если какая-либо команда завершится с ошибкой
set -e

# Запускаем скрипт инициализации базы данных
echo "--- Running Database Initializer (Manual Mode) ---"
python init_db.py
echo "--- Database Initializer finished ---"

# Теперь передаем управление основной команде контейнера (uvicorn)
exec "$@"