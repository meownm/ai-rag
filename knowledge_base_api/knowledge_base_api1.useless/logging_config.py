# logging_config.py
import logging
from typing import Dict

# --- ВАШ КАСТОМНЫЙ ФИЛЬТР ---
# Предполагается, что ваш TraceIdFilter выглядит примерно так.
# Если он другой, замените этот класс на свой.
class TraceIdFilter(logging.Filter):
    def filter(self, record):
        # Здесь должна быть ваша логика добавления trace_id
        # Например, из request.state или другой системы
        record.trace_id = "some-trace-id" 
        return True

# --- ВАШ СЛОВАРЬ КОНФИГУРАЦИИ ---
# Я предполагаю, что он выглядит примерно так.
LOGGING_CONFIG: Dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "trace_id_filter": {
            "()": "logging_config.TraceIdFilter",
        }
    },
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - [%(trace_id)s] - %(message)s",
        }
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["trace_id_filter"],
            "level": "INFO",
        }
    },
    "root": {
        "handlers": ["default"],
        "level": "INFO",
    },
    "loggers": {
        "uvicorn.error": {
            "propagate": True,
        },
        "uvicorn.access": {
            "propagate": True,
        },
    },
}
