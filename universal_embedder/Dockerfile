# Dockerfile
# Контейнер для стабильного CPU-based воркера (Linux)

FROM python:3.11-slim-buster

# Устанавливаем зависимости на уровне OS
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install poetry

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY pyproject.toml poetry.lock ./
COPY worker.py ./
COPY run.py ./
COPY .env.example ./

# 1. Установка основных зависимостей (poetry.dependencies)
RUN poetry install --no-root

# 2. Установка группы local-ml (форсируем CPU-версию torch)
# Это гарантирует, что torch, torchvision, torchaudio установятся с правильными CPU-версиями,
# а остальные ML-пакеты (transformers, sentence-transformers, scipy) будут установлены через local-ml.
RUN poetry run pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN poetry install --no-root --only local-ml

# Переменные окружения по умолчанию (для контейнера)
ENV POSTGRES_DSN="postgresql://user:pass@host.docker.internal:5432/dbname"
ENV WORKER_TYPE="cpu"
ENV WORKER_MODEL_TYPE="local_torch"
ENV WORKER_BATCH_SIZE=128

# Открываем порт для Health Check
EXPOSE 8012

# Команда запуска Uvicorn (через poetry entry point)
ENTRYPOINT ["poetry", "run", "start-worker"]