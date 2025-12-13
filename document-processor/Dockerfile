# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости (для docx/pdf/tesseract)
RUN apt-get update && apt-get install -y \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Копируем весь проект
COPY . .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -U pip && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi || \
    if [ -f pyproject.toml ]; then pip install .; fi

# Среда выполнения
ENV PYTHONUNBUFFERED=1
ENV USE_GPU=false

# FastAPI порт
EXPOSE 8010

# Команда запуска
CMD ["python", "main.py"]
