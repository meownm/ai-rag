import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from main import app, Base, get_db, User, Tenant, UserRole, pwd_context, get_s3_client

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

TEST_USERNAME = "testadmin"
TEST_PASSWORD = "testpassword"

@pytest_asyncio.fixture()
async def client() -> tuple[AsyncClient, str]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        test_tenant = Tenant(name="Test Tenant")
        session.add(test_tenant)
        await session.commit()
        await session.refresh(test_tenant)
        hashed_password = pwd_context.hash(TEST_PASSWORD)
        test_user = User(
            username=TEST_USERNAME,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            tenant_id=test_tenant.id
        )
        session.add(test_user)
        await session.commit()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/token", data={"username": TEST_USERNAME, "password": TEST_PASSWORD})
        assert response.status_code == 200
        token = response.json()["access_token"]
        yield ac, token

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_health_check(client: tuple[AsyncClient, str]):
    test_client, _ = client
    # Мокаем S3 зависимость, так как в тестах у нас нет S3
    app.dependency_overrides[get_s3_client] = lambda: None 
    response = await test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["api"]["status"] == "ok"
    del app.dependency_overrides[get_s3_client]

@pytest.mark.asyncio
async def test_get_self_user_profile(client: tuple[AsyncClient, str]):
    test_client, token = client
    headers = {"Authorization": f"Bearer {token}"}
    response = await test_client.get("/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == TEST_USERNAME
    assert data["role"] == "admin"

@pytest.mark.asyncio
async def test_add_link_and_get_items(client: tuple[AsyncClient, str]):
    test_client, token = client
    headers = {"Authorization": f"Bearer {token}"}
    link_data = {"name": "Test FastAPI", "url": "https://fastapi.tiangolo.com/"}
    response_post = await test_client.post("/links", headers=headers, json=link_data)
    assert response_post.status_code == 201
    created_item = response_post.json()
    assert created_item["item_name"] == link_data["name"]
    response_get = await test_client.get("/items", headers=headers)
    assert response_get.status_code == 200
    items = response_get.json()
    assert len(items) == 1
    assert items[0]["item_uuid"] == created_item["item_uuid"]