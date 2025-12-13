#!/bin/bash
# scripts/stop-prod.sh
# Останавливает и удаляет Docker контейнер.

echo "Остановка и удаление production-контейнера..."
docker-compose down

echo "Сервис остановлен."