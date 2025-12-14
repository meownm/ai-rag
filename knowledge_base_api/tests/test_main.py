import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core import pwd_context
from models import Tenant, User, UserRole

TEST_USERNAME = "testadmin"
TEST_PASSWORD = "testpassword"


@pytest.mark.asyncio
async def test_health_check(api_client: AsyncClient):
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["api"]["status"] == "ok"


@pytest.mark.asyncio
async def test_get_self_user_profile(api_client: AsyncClient, db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    hashed_password = pwd_context.hash(TEST_PASSWORD)
    user = User(
        username=TEST_USERNAME,
        hashed_password=hashed_password,
        role=UserRole.ADMIN,
        tenant_id=tenant.id,
    )
    db_session.add(user)
    await db_session.commit()

    token_response = await api_client.post(
        "/token", data={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = await api_client.get("/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == TEST_USERNAME
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_add_link_and_get_items(api_client: AsyncClient, db_session: AsyncSession):
    tenant = Tenant(name="Links Tenant")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    hashed_password = pwd_context.hash(TEST_PASSWORD)
    user = User(
        username=TEST_USERNAME,
        hashed_password=hashed_password,
        role=UserRole.ADMIN,
        tenant_id=tenant.id,
    )
    db_session.add(user)
    await db_session.commit()

    token_response = await api_client.post(
        "/token", data={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    link_data = {"name": "Test FastAPI", "url": "https://fastapi.tiangolo.com/"}
    response_post = await api_client.post("/links", headers=headers, json=link_data)
    assert response_post.status_code == 201
    created_item = response_post.json()
    assert created_item["item_name"] == link_data["name"]

    response_get = await api_client.get("/items", headers=headers)
    assert response_get.status_code == 200
    items = response_get.json()
    assert len(items) == 1
    assert items[0]["item_uuid"] == created_item["item_uuid"]
