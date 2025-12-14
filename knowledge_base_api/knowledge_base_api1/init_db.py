import time
import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

# Импортируем необходимые компоненты из нашего основного приложения
# Base содержит метаданные обо ВСЕХ наших таблицах (KnowledgeEvent и ApiLog)
from main import Base, settings

async def check_and_init_db():
    print("--- Database Initializer (Manual Mode) ---")

    db_url = settings.database_url
    if not db_url:
        print("[!] DATABASE_URL not found in settings. Aborting.")
        exit(1)

    # Создаем асинхронный движок
    engine = create_async_engine(db_url)

    # Пытаемся подключиться к базе данных с несколькими попытками
    retries = 5
    while retries > 0:
        try:
            async with engine.connect() as connection:
                print("[*] Database connection successful.")
                break
        except Exception as e:
            retries -= 1
            print(f"[!] Database not ready, retrying in 5 seconds... ({retries} retries left)")
            await asyncio.sleep(5)
    else:
        print("[!] Could not connect to the database after several retries. Aborting.")
        exit(1)

    # Проверяем наличие наших таблиц
    tables_to_check = ["knowledge_events", "api_logs"]
    missing_tables = []

    async with engine.begin() as conn:
        def check_tables_sync(sync_conn):
            inspector = inspect(sync_conn)
            non_existent = []
            for table_name in tables_to_check:
                if not inspector.has_table(table_name):
                    non_existent.append(table_name)
            return non_existent
        
        missing_tables = await conn.run_sync(check_tables_sync)

    if not missing_tables:
        print("[V] All required tables already exist. No action needed.")
    else:
        print(f"[!] The following tables are missing: {', '.join(missing_tables)}")
        print("[*] Creating all tables from metadata...")
        try:
            async with engine.begin() as conn:
                # Base.metadata.create_all создаст ВСЕ таблицы,
                # которые определены через Base, пропуская уже существующие.
                await conn.run_sync(Base.metadata.create_all)
            print("[V] All tables created or verified successfully.")
        except Exception as e:
            print(f"[!] An error occurred while creating tables: {e}")
            exit(1)
    
    # Закрываем соединение с движком
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_and_init_db())