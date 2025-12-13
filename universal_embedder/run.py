# run.py
import uvicorn
import os

def main():
    """Точка входа Poetry для запуска Uvicorn."""
    # Используем порт 8012, чтобы не конфликтовать с другими сервисами по умолчанию
    port = int(os.environ.get("UVICORN_PORT", 8012))
    uvicorn.run("worker:app", host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    main()