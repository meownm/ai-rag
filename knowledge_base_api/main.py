import asyncio
import logging
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import core
from core import (
    AsyncSessionLocal,
    engine,
    get_current_user,
    get_db,
    get_s3_client,
    settings,
    validate_oidc_token,
)
from logging_setup import setup_logging, trace_id_var
from models import Base, DeepHealthCheckResponse, StatusResponse, Tenant, User, UserRole
from routers import auth, items, telegram
from routers import admin as admin_router
from services import S3UploadError

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Base API (Production)", version="4.1.0")


@app.get("/")
async def root():
    return {"message": "Hello, World!"}


@app.exception_handler(S3UploadError)
async def s3_upload_exception_handler(request: Request, exc: S3UploadError):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: Could not process file storage. Details: {str(exc)}"},
    )


class OIDCMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                claims = await validate_oidc_token(token)
                request.state.oidc_claims = claims
                request.state.org_id = claims.get("org_id")
            except Exception as exc:  # noqa: BLE001
                logger.warning("OIDC token validation failed: %s", exc)
        return await call_next(request)


app.add_middleware(OIDCMiddleware)
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(admin_router.router)
app.include_router(telegram.router)


async def seed_initial_data(db: AsyncSession):
    logger.info("Checking for initial data seeding...")
    try:
        tenant_name = settings.initial_tenant_name
        result = await db.execute(select(Tenant).where(Tenant.name == tenant_name))
        tenant = result.scalars().first()
        if not tenant:
            tenant = Tenant(name=tenant_name)
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)

        admin_username = settings.initial_admin_username
        result = await db.execute(select(User).where(User.username == admin_username))
        admin_user = result.scalars().first()
        if not admin_user:
            hashed_password = core.pwd_context.hash(settings.initial_admin_password)
            admin_user = User(
                username=admin_username,
                hashed_password=hashed_password,
                role=UserRole.ADMIN,
                tenant_id=tenant.id,
                idp_subject=admin_username,
            )
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)
    except Exception as e:  # noqa: BLE001
        logger.error("An error occurred during initial data seeding: %s", e, exc_info=True)
        await db.rollback()
        raise


@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)


@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = trace_id_var.set(trace_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = trace_id
    trace_id_var.reset(token)
    return response


@app.get("/health", response_model=DeepHealthCheckResponse, tags=["Monitoring"], summary="Проверка состояния сервиса")
async def health_check(db: AsyncSession = Depends(get_db), s3_client=Depends(get_s3_client)):
    health = {"api": {"status": "ok"}, "database": {"status": "ok"}, "storage": {"status": "ok"}}
    http_status = 200
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        health["database"] = {"status": "down", "details": str(e)}
        http_status = 503
    try:
        await s3_client.head_bucket(Bucket=settings.s3_bucket_name)
    except Exception as e:  # noqa: BLE001
        health["storage"] = {"status": "down", "details": str(e)}
        http_status = 503

    return Response(
        content=DeepHealthCheckResponse(**health).model_dump_json(),
        status_code=http_status,
        media_type="application/json",
    )


@app.get("/status", response_model=StatusResponse, tags=["Monitoring"], summary="Получение статистики по базе знаний")
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    params = {"user_id": current_user.id, "tenant_id": current_user.tenant_id}

    q1 = text("SELECT COUNT(*) FROM knowledge_events WHERE user_id = :user_id AND operation = 'created'")
    q2 = text("SELECT COUNT(*) FROM documents WHERE tenant_id = :tenant_id")
    q3 = text("SELECT COUNT(*) FROM chunks WHERE tenant_id = :tenant_id")
    q4 = text("SELECT COUNT(*) FROM chunks WHERE tenant_id = :tenant_id AND embedding IS NOT NULL")
    q5 = text("SELECT COUNT(*) FROM chunks WHERE tenant_id = :tenant_id AND metadata IS NOT NULL")

    results = await asyncio.gather(
        db.scalar(q1, params),
        db.scalar(q2, params),
        db.scalar(q3, params),
        db.scalar(q4, params),
        db.scalar(q5, params),
    )

    return StatusResponse(
        files_uploaded_by_user=results[0],
        documents_in_tenant=results[1],
        chunks_in_tenant=results[2],
        chunks_with_embedding=results[3],
        chunks_with_metadata=results[4],
    )
