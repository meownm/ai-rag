#!/bin/bash
# scripts/run-prod.sh
# Собирает и запускает Docker контейнер в фоновом режиме.

echo "Сборка и запуск production-контейнера..."
docker-compose up --build -d

echo "Сервис запущен. Проверьте логи командой: docker-compose logs -f"