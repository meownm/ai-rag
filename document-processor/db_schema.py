# db_schema.py
#
# Версия 3.8: Добавлено полное документирование схемы БД через COMMENT ON.
# --------------------------------------------------------------------------

import logging
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

def initialize_database_schema(conn):
    logging.info("DB_SCHEMA: Проверка, настройка и документирование схемы базы данных (v3.8)...")
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        logging.info(" -> Расширение 'vector' включено.")

        # --- Таблица settings ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(100) PRIMARY KEY,
                value JSONB NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );""")
        logging.info(" -> Таблица 'settings' готова.")

        cur.execute("COMMENT ON TABLE settings IS 'Хранит глобальные настройки и конфигурацию системы, управляемые приложением.';")
        cur.execute("COMMENT ON COLUMN settings.key IS 'Уникальный ключ настройки (например, ''embedding_config'').';")
        cur.execute("COMMENT ON COLUMN settings.value IS 'JSONB-объект со значением настройки.';")

        cur.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
               NEW.updated_at = NOW();
               RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        cur.execute("DROP TRIGGER IF EXISTS set_timestamp ON settings;")
        cur.execute("""
            CREATE TRIGGER set_timestamp
            BEFORE UPDATE ON settings
            FOR EACH ROW
            EXECUTE PROCEDURE update_updated_at_column();
        """)
        logging.info(" -> Триггер для 'settings.updated_at' готов.")

        # --- Таблица documents ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                owner_user_id UUID NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                title TEXT,
                author TEXT,
                metadata JSONB DEFAULT '{}'::jsonb
            );""")
        logging.info(" -> Таблица 'documents' готова.")

        cur.execute("COMMENT ON TABLE documents IS 'Хранит метаданные для каждого уникального, обработанного документа.';")
        cur.execute("COMMENT ON COLUMN documents.doc_id IS 'Уникальный идентификатор документа, соответствующий item_uuid из события.';")
        cur.execute("COMMENT ON COLUMN documents.tenant_id IS 'ID арендатора (клиента), которому принадлежит документ.';")
        cur.execute("COMMENT ON COLUMN documents.owner_user_id IS 'ID пользователя, загрузившего документ.';")
        cur.execute("COMMENT ON COLUMN documents.filename IS 'Оригинальное имя файла.';")
        cur.execute("COMMENT ON COLUMN documents.uploaded_at IS 'Время создания записи о документе.';")
        cur.execute("COMMENT ON COLUMN documents.title IS 'Заголовок документа, извлеченный парсером.';")
        cur.execute("COMMENT ON COLUMN documents.author IS 'Автор документа, извлеченный парсером.';")
        cur.execute("COMMENT ON COLUMN documents.metadata IS 'Прочие метаданные, извлеченные парсерами (размер, даты и т.д.).';")

        cur.execute("CREATE INDEX IF NOT EXISTS ix_documents_tenant_id ON documents (tenant_id);")
        logging.info(" -> Индексы для 'documents' готовы.")

        # --- Таблица chunks ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                doc_id UUID NOT NULL,
                chunk_id INT NOT NULL,
                tenant_id UUID NOT NULL,
                text TEXT NOT NULL,
                section TEXT,
                type TEXT,
                block_type TEXT,
                embedding vector(2048),
                text_tsv TSVECTOR,
                metadata JSONB DEFAULT '{}'::jsonb,
                enrichment_status JSONB DEFAULT '{}'::jsonb,
                embedding_version INT DEFAULT 1 NOT NULL,
                PRIMARY KEY (doc_id, chunk_id),
                FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
            );""")
        logging.info(" -> Таблица 'chunks' готова.")

        cur.execute("COMMENT ON TABLE chunks IS 'Хранит обработанные текстовые фрагменты (чанки) каждого документа.';")
        cur.execute("COMMENT ON COLUMN chunks.doc_id IS 'Внешний ключ, связывающий чанк с документом.';")
        cur.execute("COMMENT ON COLUMN chunks.chunk_id IS 'Порядковый номер чанка внутри документа.';")
        cur.execute("COMMENT ON COLUMN chunks.text IS 'Текстовое содержимое чанка.';")
        cur.execute("COMMENT ON COLUMN chunks.section IS 'Раздел/идентификатор исходного блока (например, таблицы).';")
        cur.execute("COMMENT ON COLUMN chunks.type IS 'Исходный тип блока после парсинга (paragraph, table, slide и т.д.).';")
        cur.execute("COMMENT ON COLUMN chunks.block_type IS 'Тип сгенерированного чанка после нарезки (table_part, composite_section и т.д.).';")
        cur.execute("COMMENT ON COLUMN chunks.embedding IS 'Векторное представление (эмбеддинг) текста чанка.';")
        cur.execute("COMMENT ON COLUMN chunks.text_tsv IS 'Предварительно рассчитанный tsvector для полнотекстового поиска.';")
        cur.execute("COMMENT ON COLUMN chunks.metadata IS 'Дополнительные метаданные чанка (контекст, результаты LLM-обогащения).';")
        cur.execute("COMMENT ON COLUMN chunks.enrichment_status IS 'JSONB-поле, отслеживающее статус асинхронных этапов обогащения.';")
        cur.execute("COMMENT ON COLUMN chunks.embedding_version IS 'Версия конфигурации эмбеддингов из таблицы settings.';")

        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='chunks' AND column_name='embedding_version') THEN
                    ALTER TABLE chunks ADD COLUMN embedding_version INT DEFAULT 1 NOT NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='chunks' AND column_name='section') THEN
                    ALTER TABLE chunks ADD COLUMN section TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='chunks' AND column_name='type') THEN
                    ALTER TABLE chunks ADD COLUMN type TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='chunks' AND column_name='block_type') THEN
                    ALTER TABLE chunks ADD COLUMN block_type TEXT;
                END IF;
            END $$;
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS ix_chunks_tenant_id ON chunks (tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_chunks_section ON chunks (section);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_chunks_block_type ON chunks (block_type);")
        cur.execute("CREATE INDEX IF NOT EXISTS chunks_text_tsv_idx ON chunks USING GIN(text_tsv);")
        logging.info(" -> Индексы для 'chunks' готовы.")

        cur.execute("""CREATE OR REPLACE FUNCTION update_chunks_tsv() RETURNS TRIGGER AS $$ BEGIN NEW.text_tsv := to_tsvector('russian', NEW.text) || to_tsvector('english', NEW.text); RETURN NEW; END; $$ LANGUAGE plpgsql;""")
        cur.execute("DROP TRIGGER IF EXISTS tsvector_update ON chunks;")
        cur.execute("""CREATE TRIGGER tsvector_update BEFORE INSERT OR UPDATE ON chunks FOR EACH ROW EXECUTE FUNCTION update_chunks_tsv();""")
        logging.info(" -> Триггер для 'text_tsv' готов.")

        # --- Таблица knowledge_events ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.knowledge_events (
                id serial4 NOT NULL, item_uuid uuid NOT NULL, tenant_id uuid NOT NULL, user_id uuid,
                operation varchar NOT NULL, operation_time timestamp NOT NULL, item_name varchar NOT NULL,
                item_type varchar NOT NULL, "content" varchar NULL, "size" int8 NULL, status varchar NOT NULL,
                s3_path TEXT,
                CONSTRAINT knowledge_events_pkey PRIMARY KEY (id)
            );""")
        logging.info(" -> Таблица 'knowledge_events' готова.")

        cur.execute("COMMENT ON TABLE knowledge_events IS 'Журнал событий и очередь задач для обработки воркерами.';")
        cur.execute("COMMENT ON COLUMN knowledge_events.item_uuid IS 'UUID элемента, над которым производится операция (например, doc_id).';")
        cur.execute("COMMENT ON COLUMN knowledge_events.operation IS 'Тип операции (например, ''created'', ''deleted'').';")
        cur.execute("COMMENT ON COLUMN knowledge_events.status IS 'Статус обработки задачи (''new'', ''processing'', ''done'', ''failed'').';")
        cur.execute("COMMENT ON COLUMN knowledge_events.s3_path IS 'Полный путь к объекту в S3/MinIO, без имени бакета.';")

        cur.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_events_status_op ON public.knowledge_events (status, operation);")
        logging.info(" -> Индексы для 'knowledge_events' готовы.")

        # --- Таблица llm_requests_log ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.llm_requests_log (
                log_id BIGSERIAL PRIMARY KEY, request_timestamp_start TIMESTAMPTZ NOT NULL, request_timestamp_end TIMESTAMPTZ,
                duration_seconds FLOAT, is_success BOOLEAN NOT NULL, request_type VARCHAR(50), model_name VARCHAR(100),
                prompt TEXT, raw_response TEXT, error_message TEXT, prompt_tokens INT, completion_tokens INT,
                tenant_id UUID, doc_id UUID, chunk_id INT
            );""")
        logging.info(" -> Таблица 'llm_requests_log' готова.")

        cur.execute("COMMENT ON TABLE llm_requests_log IS 'Хранит детальные логи каждого запроса к LLM для аудита, отладки и анализа производительности.';")
        cur.execute("COMMENT ON COLUMN llm_requests_log.request_type IS 'Тип запроса (например, ''metadata_extraction'').';")
        cur.execute("COMMENT ON COLUMN llm_requests_log.is_success IS 'Флаг успешности выполнения запроса.';")
        cur.execute("COMMENT ON COLUMN llm_requests_log.prompt_tokens IS 'Количество токенов в промпте (если возвращается моделью).';")

        cur.execute("CREATE INDEX IF NOT EXISTS ix_llm_log_timestamp ON llm_requests_log (request_timestamp_start DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_llm_log_context ON llm_requests_log (tenant_id, doc_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_llm_log_performance ON llm_requests_log (is_success, request_type);")
        logging.info(" -> Индексы для 'llm_requests_log' готовы.")

        conn.commit()
        logging.info("DB_SCHEMA: Схема базы данных успешно настроена и задокументирована.")

def get_vector_dimension(conn) -> int:
    """Получает текущую размерность колонки embedding из БД."""
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT atttypmod
                FROM pg_attribute
                WHERE attrelid = 'chunks'::regclass AND attname = 'embedding';
            """)
            result = cur.fetchone()
            if result and result['atttypmod'] > 0:
                return result['atttypmod']
    except Exception:
        pass
    
    try:
        with open(__file__, 'r') as f:
            content = f.read()
            match = re.search(r'embedding\s+vector\((\d+)\)', content)
            if match:
                return int(match.group(1))
    except Exception:
        pass

    return 1024

if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"), dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"))
        initialize_database_schema(conn)
    except Exception as e:
        logging.critical(f"Произошла ошибка во время инициализации схемы: {e}")
    finally:
        if conn: conn.close()