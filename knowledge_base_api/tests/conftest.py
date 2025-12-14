import asyncio
import os
from importlib import reload

import httpx
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

DEFAULT_ENV = {
    "DATABASE_URL": os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kb_test:kb_test@localhost:5432/knowledge_base_test",
    ),
    "S3_ENDPOINT_URL": os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000"),
    "S3_ACCESS_KEY_ID": os.environ.get("TEST_S3_ACCESS_KEY_ID", "test-key"),
    "S3_SECRET_ACCESS_KEY": os.environ.get("TEST_S3_SECRET_ACCESS_KEY", "test-secret"),
    "S3_BUCKET_NAME": os.environ.get("TEST_S3_BUCKET_NAME", "test-bucket"),
    "S3_REGION": os.environ.get("TEST_S3_REGION", "us-east-1"),
    "SECRET_KEY": os.environ.get("TEST_SECRET_KEY", "integration-secret"),
    "ALGORITHM": os.environ.get("TEST_JWT_ALGORITHM", "HS256"),
    "ACCESS_TOKEN_EXPIRE_MINUTES": os.environ.get("TEST_ACCESS_TOKEN_EXPIRE_MINUTES", "60"),
    "OIDC_CLIENT_ID": os.environ.get("TEST_OIDC_CLIENT_ID", "knowledge-base-api"),
    "OIDC_ISSUER": os.environ.get("TEST_OIDC_ISSUER", "http://localhost:8080/realms/ai-rag"),
    "OIDC_JWKS_URL": os.environ.get(
        "TEST_OIDC_JWKS_URL",
        "http://localhost:8080/realms/ai-rag/protocol/openid-connect/certs",
    ),
}

for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)

import core as core_module  # noqa: E402
import main as main_module  # noqa: E402
from models import Base  # noqa: E402

# Reload settings-aware modules after environment variables are in place
# and expose the refreshed references for fixtures.
core_module = reload(core_module)
main_module = reload(main_module)
AsyncSessionLocal = core_module.AsyncSessionLocal
engine = core_module.engine
get_s3_client = core_module.get_s3_client


async def _wait_for_db_ready(retries: int = 30, delay: float = 1.0) -> None:
    for attempt in range(retries):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return
        except Exception:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            await asyncio.sleep(delay)


class _FakeS3Client:
    async def head_bucket(self, Bucket: str):  # noqa: N803
        return {"Bucket": Bucket}

    async def generate_presigned_url(self, *_args, **_kwargs):
        return "https://example.com/download"


async def _provide_fake_s3():
    yield _FakeS3Client()


@pytest_asyncio.fixture(scope="session")
async def prepare_database():
    await _wait_for_db_ready()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def reset_database(prepare_database):  # noqa: PT004
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture()
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def api_client():
    main_module.app.dependency_overrides[get_s3_client] = _provide_fake_s3
    async with AsyncClient(app=main_module.app, base_url="http://test") as client:
        yield client
    main_module.app.dependency_overrides.pop(get_s3_client, None)


@pytest_asyncio.fixture(scope="session")
async def http_client_session():
    async with httpx.AsyncClient() as client:
        yield client
