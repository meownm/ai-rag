# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости системы (если нужно для docx/pdf/tesseract)
RUN apt-get update && apt-get install -y \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Копируем проект
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -U pip && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi || \
    if [ -f pyproject.toml ]; then pip install .; fi

# Переменные среды
ENV PYTHONUNBUFFERED=1
ENV USE_GPU=false

EXPOSE 8000

CMD ["python", "main.py"]
