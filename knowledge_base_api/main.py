"""
Главный файл приложения FastAPI.

Этот модуль выполняет следующие задачи:
1.  Инициализирует логирование.
2.  Создает основной экземпляр приложения FastAPI.
3.  Регистрирует глобальные обработчики ошибок.
4.  Подключает все роутеры из папки `routers`.
5.  Настраивает middleware (например, для трассировки).
6.  Определяет логику для событий жизненного цикла приложения (startup).
7.  Содержит общие эндпоинты, такие как Health Check и Status.
"""
import asyncio
import logging
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from routers import auth, items

import core
from core import (AsyncSessionLocal, engine, get_db, get_s3_client,
                  settings)
from logging_setup import setup_logging, trace_id_var
from models import (Base, DeepHealthCheckResponse,
                    KnowledgeEvent, OperationType, StatusResponse, Tenant,
                    User, UserRole)

from services import S3UploadError

# ===============================================================================
# 1. КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ И ПРИЛОЖЕНИЯ
# ===============================================================================
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Base API (Production)", version="4.1.0")

@app.get("/")
async def root():
    return {"message": "Hello, World!"}
    
# ===============================================================================
# 2. ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ ОШИБОК
# ===============================================================================
@app.exception_handler(S3UploadError)
async def s3_upload_exception_handler(request: Request, exc: S3UploadError):
    """
    Перехватывает кастомное исключение S3UploadError из сервисного слоя
    и возвращает клиенту стандартизированную ошибку 500.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: Could not process file storage. Details: {str(exc)}"},
    )

# ===============================================================================
# 3. ПОДКЛЮЧЕНИЕ РОУТЕРОВ
# ===============================================================================

app.include_router(auth.router)
app.include_router(items.router)


# ===============================================================================
# 4. MIDDLEWARE, STARTUP/SHUTDOWN EVENTS
# ===============================================================================
async def seed_initial_data(db: AsyncSession):
    """
    Заполняет базу данных начальными данными (первый тенант, первый администратор),
    если они еще не существуют. Использует значения из .env файла.
    """
    logger.info("Checking for initial data seeding...")
    try:
        # --- Создание тенанта по умолчанию ---
        tenant_name = settings.initial_tenant_name
        result = await db.execute(select(Tenant).where(Tenant.name == tenant_name))
        tenant = result.scalars().first()
        if not tenant:
            logger.warning(f"Default tenant '{tenant_name}' not found, creating it.")
            tenant = Tenant(name=tenant_name)
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)
            logger.info(f"Default tenant '{tenant.name}' created with id {tenant.id}")
        else:
            logger.info("Default tenant already exists.")

        # --- Создание пользователя-администратора по умолчанию ---
        admin_username = settings.initial_admin_username
        result = await db.execute(select(User).where(User.username == admin_username))
        admin_user = result.scalars().first()
        if not admin_user:
            logger.warning(f"Default admin user '{admin_username}' not found, creating it.")
            hashed_password = core.pwd_context.hash(settings.initial_admin_password)
            admin_user = User(username=admin_username, hashed_password=hashed_password, role=UserRole.ADMIN, tenant_id=tenant.id)
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)
            logger.info(f"Default admin user '{admin_username}' created.")
        else:
            logger.info("Default admin user already exists.")
    except Exception as e:
        logger.error(f"An error occurred during initial data seeding: {e}", exc_info=True)
        await db.rollback()
        raise

@app.on_event("startup")
async def startup_event():
    """
    Выполняется один раз при запуске приложения.
    """
    logger.info("Application startup...")
    # 1. Создаем таблицы в БД, если они не существуют.
    async with engine.begin() as conn:
        logger.info("Checking and creating tables if they do not exist...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables are ready.")
    
    # 2. Заполняем БД начальными данными.
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)

@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    """
    Промежуточный слой (middleware), который выполняется для каждого HTTP-запроса.
    Добавляет уникальный ID для трассировки запроса в логи и в ответ.
    """
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = trace_id_var.set(trace_id)
    
    logger.info("Request started", extra={"path": request.url.path, "method": request.method})
    
    response = await call_next(request)
    
    response.headers["X-Request-ID"] = trace_id
    trace_id_var.reset(token)
    return response

# ===============================================================================
# 5. ОБЩИЕ ЭНДПОИНТЫ (Health Check, Status)
# ===============================================================================
@app.get("/health", response_model=DeepHealthCheckResponse, tags=["Monitoring"], summary="Проверка состояния сервиса")
async def health_check(db: AsyncSession = Depends(get_db), s3_client = Depends(get_s3_client)):
    """
    Выполняет "глубокую" проверку состояния, опрашивая не только само приложение,
    но и его зависимости (базу данных и S3-хранилище).
    Возвращает статус 503, если какая-либо из зависимостей недоступна.
    """
    health = {"api": {"status": "ok"}, "database": {"status": "ok"}, "storage": {"status": "ok"}}
    http_status = 200
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        health["database"] = {"status": "down", "details": str(e)}
        http_status = 503
    try:
        await s3_client.head_bucket(Bucket=settings.s3_bucket_name)
    except Exception as e:
        health["storage"] = {"status": "down", "details": str(e)}
        http_status = 503
    
    return Response(
        content=DeepHealthCheckResponse(**health).model_dump_json(),
        status_code=http_status,
        media_type="application/json"
    )

@app.get("/status", response_model=StatusResponse, tags=["Monitoring"], summary="Получение статистики по базе знаний")
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    """
    Собирает и возвращает статистику, используя прямые SQL-запросы на подсчет.
    """
    logger.info("Gathering statistics for tenant %s via raw SQL", current_user.tenant_id)
    
    # Готовим параметры для безопасной вставки в запросы
    params = {
        "user_id": current_user.id,
        "tenant_id": current_user.tenant_id
    }
    
    # --- "Рабоче-крестьянские" SQL-запросы ---
    # text() - функция SQLAlchemy для безопасного выполнения сырых SQL
    # :user_id и :tenant_id - это именованные параметры, защищающие от SQL-инъекций.
    
    q1 = text("SELECT COUNT(*) FROM knowledge_events WHERE user_id = :user_id AND operation = 'created'")
    q2 = text("SELECT COUNT(*) FROM documents WHERE tenant_id = :tenant_id")
    q3 = text("SELECT COUNT(*) FROM chunks WHERE tenant_id = :tenant_id")
    q4 = text("SELECT COUNT(*) FROM chunks WHERE tenant_id = :tenant_id AND embedding IS NOT NULL")
    q5 = text("SELECT COUNT(*) FROM chunks WHERE tenant_id = :tenant_id AND metadata IS NOT NULL")
    
    # Запускаем все запросы параллельно для эффективности
    results = await asyncio.gather(
        db.scalar(q1, params),
        db.scalar(q2, params),
        db.scalar(q3, params),
        db.scalar(q4, params),
        db.scalar(q5, params)
    )
    
    return StatusResponse(
        files_uploaded_by_user=results[0],
        documents_in_tenant=results[1],
        chunks_in_tenant=results[2],
        chunks_with_embedding=results[3],
        chunks_with_metadata=results[4],
    )