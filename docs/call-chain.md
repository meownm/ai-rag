# Цепочка вызовов: Telegram-бот → База знаний → Document Processor → Эмбеддер

Ниже описан фактический путь данных и управляющих запросов, начиная с взаимодействия пользователя в Telegram-боте и заканчивая генерацией эмбеддингов.

## 1. Telegram-бот
* Бот хранит асинхронный клиент `KnowledgeBaseAPI`, который автоматически обновляет JWT и подставляет его в каждый запрос к API базы знаний (`/token`, затем использование Bearer). 
* Хэндлер загрузки файла (`document_handler`) скачивает бинарный файл из Telegram и отправляет его в базу знаний через `POST /files`, остальные хэндлеры вызывают поиск/статистику через `GET /items`, `GET /items/search`, `GET /status`.

## 2. API базы знаний
* `POST /files` вызывает `create_file_event`, который загружает файл в S3/MinIO и записывает событие в таблицу `knowledge_events` со статусом `new` и операцией `created` (очередь для Document Processor).
* Для каждой загрузки создаётся новый `item_uuid`; существующий файл помечается `DELETED`, чтобы отделить старую версию.

## 3. Document Processor
* `upload_worker_loop` циклически выбирает задачи `knowledge_events` со статусом `new` и операцией `created`, помечает их `processing` и вызывает `process_and_save_file`. Этот шаг скачивает файл из MinIO, парсит его, чанкует и записывает в `documents`/`chunks`, выставляя `enrichment_status.embedding_generation=pending`.
* `enrichment_worker_loop` подхватывает чанки со статусом `embedding_generation=pending`, генерирует эмбеддинги (локальная `SentenceTransformer` или внешний API) и массово обновляет `chunks.embedding`, а также статус задачи в `enrichment_status`.

## 4. Универсальный эмбеддер (опциональный)
* Сервис `universal_embedder` может выступать альтернативным генератором эмбеддингов: `WorkerApp` периодически лочит порции записей из таблицы `chunks`, где `embedding` отсутствует или версия отстаёт, создаёт батч эмбеддингов на локальной модели или через OpenAI-совместимый API и обновляет `chunks.embedding`, `embedding_version` и `enrichment_status.embedding_generation`.

## Итоговое движение данных
1. Пользователь отправляет файл боту → бот вызывает `POST /files` в базе знаний.
2. API базы знаний загружает файл в MinIO и создаёт событие `created` в `knowledge_events`.
3. Document Processor вытягивает событие, парсит файл и кладёт чанки в БД с задачей на эмбеддинги.
4. Встроенный воркер Document Processor **или** сервис universal_embedder снимает задачу на эмбеддинги, пишет вектор в `chunks.embedding` и обновляет статус. Всё готово для поиска/ответов.
