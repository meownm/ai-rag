"""
Скрипт для ручной инициализации базы данных.

Он выполняет следующие действия:
1.  Подключается к БД, указанной в .env файле.
2.  Делает несколько попыток подключения, ожидая, пока БД станет доступна.
3.  Проверяет наличие необходимых таблиц (tenants, users, knowledge_events).
4.  Если какие-либо таблицы отсутствуют, создает их на основе моделей SQLAlchemy.
"""
import asyncio

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from core import settings
from models import Base

async def check_and_init_db():
    """Основная функция для проверки и создания таблиц."""
    print("--- Database Initializer (Manual Mode) ---")

    db_url = settings.database_url
    if not db_url:
        print("[!] DATABASE_URL not found in settings. Aborting.")
        exit(1)

    engine = create_async_engine(db_url)

    # Пытаемся подключиться к базе данных с несколькими попытками.
    # Это полезно в контейнерных средах, где приложение может запуститься
    # раньше, чем база данных.
    retries = 5
    while retries > 0:
        try:
            async with engine.connect():
                print("[*] Database connection successful.")
                break
        except Exception:
            retries -= 1
            print(f"[!] Database not ready, retrying in 5 seconds... ({retries} retries left)")
            await asyncio.sleep(5)
    else:
        print("[!] Could not connect to the database after several retries. Aborting.")
        exit(1)

    # Список таблиц, которые должны существовать в нашей БД.
    tables_to_check = ["tenants", "users", "knowledge_events"]
    
    # Проверяем, какие из таблиц отсутствуют.
    # Используем inspector для интроспекции схемы БД.
    async with engine.begin() as conn:
        def check_tables_sync(sync_conn):
            inspector = inspect(sync_conn)
            return [
                table_name
                for table_name in tables_to_check
                if not inspector.has_table(table_name)
            ]
        
        missing_tables = await conn.run_sync(check_tables_sync)

    # Если все таблицы на месте, ничего не делаем.
    if not missing_tables:
        print("[V] All required tables already exist. No action needed.")
    else:
        # Если каких-то таблиц не хватает, создаем их.
        print(f"[!] The following tables are missing: {', '.join(missing_tables)}")
        print("[*] Creating all tables from metadata...")
        try:
            async with engine.begin() as conn:
                # Base.metadata.create_all создаст ВСЕ таблицы,
                # которые определены через Base, пропуская уже существующие.
                # Это идемпотентная операция.
                await conn.run_sync(Base.metadata.create_all)
            print("[V] All tables created or verified successfully.")
        except Exception as e:
            print(f"[!] An error occurred while creating tables: {e}")
            exit(1)
    
    # Корректно закрываем пул соединений.
    await engine.dispose()

if __name__ == "__main__":
    # Позволяет запускать этот скрипт напрямую командой `python init_db.py`
    asyncio.run(check_and_init_db())