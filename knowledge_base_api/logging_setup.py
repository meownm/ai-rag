"""
Централизованная настройка логирования.

Этот модуль содержит:
1.  ContextVar `trace_id_var` для хранения ID трассировки запроса.
2.  Фильтр `TraceIdFilter` для добавления trace_id в каждую запись лога.
3.  Словарь `LOGGING_CONFIG` с полной конфигурацией для `logging.dictConfig`.
4.  Функцию `setup_logging` для применения этой конфигурации.
"""
import logging
import uuid
from contextvars import ContextVar
from logging.config import dictConfig
from typing import Optional

# 1. ContextVar для хранения ID трассировки.
# ContextVar - это специальная переменная, которая безопасна для использования
# в асинхронном коде. Она хранит свое значение уникальным для каждой
# асинхронной задачи (например, для каждого HTTP-запроса), предотвращая
# путаницу trace_id между параллельно обрабатываемыми запросами.
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

class TraceIdFilter(logging.Filter):
    """Кастомный фильтр для добавления trace_id в каждую запись лога."""
    def filter(self, record):
        # При каждой записи в лог, этот фильтр извлекает значение из ContextVar
        # и добавляет его в объект записи лога (record).
        record.trace_id = trace_id_var.get()
        return True

# 2. Словарь конфигурации логирования.
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            # Используем python-json-logger для вывода логов в структурированном JSON формате.
            # Это стандарт для современных систем сбора логов (ELK, Datadog, Grafana Loki).
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s %(trace_id)s",
        },
    },
    "filters": {
        "trace_id_filter": {
            # Указываем Python создать экземпляр нашего кастомного фильтра.
            # Путь "logging_setup.TraceIdFilter" является стабильным и не зависит от того,
            # как запускается приложение.
            "()": "logging_setup.TraceIdFilter",
        }
    },
    "handlers": {
        "default": {
            # Выводим логи в стандартный поток вывода (консоль).
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["trace_id_filter"], # Применяем наш фильтр к этому обработчику.
        },
    },
    "root": {
        # Настройки для корневого логгера. Все логгеры в приложении
        # наследуют эти настройки.
        "handlers": ["default"],
        "level": "INFO",
    },
}

# 3. Функция-инициализатор.
def setup_logging():
    """Применяет конфигурацию логирования из словаря LOGGING_CONFIG."""
    dictConfig(LOGGING_CONFIG)