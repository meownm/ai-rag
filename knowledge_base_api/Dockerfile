# Dockerfile

# Этап 1: Используем официальный образ Python как базовый
FROM python:3.9-slim-buster as base

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем Poetry
RUN pip install poetry

# Конфигурируем Poetry так, чтобы он не создавал виртуальное окружение внутри контейнера
RUN poetry config virtualenvs.create false

# Копируем только файлы зависимостей и устанавливаем их
COPY pyproject.toml ./
RUN poetry install --no-root --no-dev

# Этап 2: Собираем финальный образ
FROM python:3.9-slim-buster

WORKDIR /app

# Копируем установленные зависимости из первого этапа
COPY --from=base /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=base /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Копируем исходный код приложения
COPY . .

# Открываем порт, на котором будет работать приложение
EXPOSE 8001

# Команда для запуска приложения при старте контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]