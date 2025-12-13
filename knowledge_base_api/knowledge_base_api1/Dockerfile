FROM python:3.11-slim as base
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app
RUN pip install --no-cache-dir poetry

FROM base as builder
COPY pyproject.toml poetry.lock ./
# Устанавливаем только production зависимости
RUN poetry install --no-interaction --no-ansi --no-dev --no-root

FROM base
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY main.py .
COPY .env .

# Слушаем на 0.0.0.0, чтобы быть доступным извне контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]