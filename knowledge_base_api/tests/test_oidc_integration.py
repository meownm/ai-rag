import asyncio
import uuid

import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy import select

from core import AsyncSessionLocal, settings
from models import Organization, Tenant, User, UserRole

REALM_NAME = "ai-rag"
TEST_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_USERNAME = "oidc-user"
TEST_PASSWORD = "Password123!"


async def _wait_for_keycloak(http_client_session, base_url: str) -> None:
    for attempt in range(60):
        try:
            response = await http_client_session.get(
                f"{base_url}/realms/master/.well-known/openid-configuration", timeout=5
            )
            if response.status_code < 500:
                return
        except Exception:  # noqa: BLE001
            if attempt == 59:
                raise
        await asyncio.sleep(1)


async def _get_admin_token(http_client_session, base_url: str) -> str:
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": "admin",
        "password": "admin",
    }
    response = await http_client_session.post(
        f"{base_url}/realms/master/protocol/openid-connect/token", data=data, timeout=30
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _ensure_realm(http_client_session, base_url: str, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    realm_payload = {"realm": REALM_NAME, "enabled": True}
    response = await http_client_session.post(
        f"{base_url}/admin/realms", json=realm_payload, headers=headers, timeout=30
    )
    if response.status_code not in (201, 409):
        response.raise_for_status()


async def _get_client_id(http_client_session, base_url: str, admin_token: str, client_id: str) -> str:
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await http_client_session.get(
        f"{base_url}/admin/realms/{REALM_NAME}/clients",
        params={"clientId": client_id},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    clients = response.json()
    return clients[0]["id"] if clients else ""


async def _ensure_client(http_client_session, base_url: str, admin_token: str, org_id: uuid.UUID) -> str:
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "clientId": settings.oidc_client_id,
        "publicClient": True,
        "directAccessGrantsEnabled": True,
        "standardFlowEnabled": False,
        "protocolMappers": [
            {
                "name": "org_id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "consentRequired": False,
                "config": {
                    "claim.value": str(org_id),
                    "claim.name": "org_id",
                    "jsonType.label": "String",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                },
            }
        ],
    }

    response = await http_client_session.post(
        f"{base_url}/admin/realms/{REALM_NAME}/clients", json=payload, headers=headers, timeout=30
    )
    if response.status_code not in (201, 409):
        response.raise_for_status()

    client_uid = await _get_client_id(http_client_session, base_url, admin_token, settings.oidc_client_id)
    if not client_uid:
        raise RuntimeError("OIDC client was not created")
    return client_uid


async def _ensure_user(http_client_session, base_url: str, admin_token: str) -> str:
    headers = {"Authorization": f"Bearer {admin_token}"}
    user_payload = {
        "username": TEST_USERNAME,
        "enabled": True,
        "emailVerified": True,
    }
    response = await http_client_session.post(
        f"{base_url}/admin/realms/{REALM_NAME}/users", json=user_payload, headers=headers, timeout=30
    )
    if response.status_code not in (201, 409):
        response.raise_for_status()

    users_response = await http_client_session.get(
        f"{base_url}/admin/realms/{REALM_NAME}/users",
        params={"username": TEST_USERNAME},
        headers=headers,
        timeout=30,
    )
    users_response.raise_for_status()
    user_id = users_response.json()[0]["id"]

    credential_payload = {
        "type": "password",
        "temporary": False,
        "value": TEST_PASSWORD,
    }
    await http_client_session.put(
        f"{base_url}/admin/realms/{REALM_NAME}/users/{user_id}/reset-password",
        json=credential_payload,
        headers=headers,
        timeout=30,
    )
    return user_id


async def _obtain_user_token(http_client_session, base_url: str) -> str:
    data = {
        "grant_type": "password",
        "client_id": settings.oidc_client_id,
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    }
    response = await http_client_session.post(
        f"{base_url}/realms/{REALM_NAME}/protocol/openid-connect/token", data=data, timeout=30
    )
    response.raise_for_status()
    return response.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def keycloak_token(http_client_session):
    base_url = settings.oidc_issuer.rsplit("/realms", 1)[0]
    await _wait_for_keycloak(http_client_session, base_url)
    admin_token = await _get_admin_token(http_client_session, base_url)
    await _ensure_realm(http_client_session, base_url, admin_token)
    await _ensure_client(http_client_session, base_url, admin_token, TEST_ORG_ID)
    await _ensure_user(http_client_session, base_url, admin_token)
    token = await _obtain_user_token(http_client_session, base_url)
    return token


@pytest.mark.asyncio
async def test_oidc_token_allows_access_and_maps_user(api_client, keycloak_token: str):
    claims = jwt.get_unverified_claims(keycloak_token)

    async with AsyncSessionLocal() as session:
        initial_tenant = Tenant(name="Initial Tenant")
        mapped_tenant = Tenant(name="Mapped Tenant")
        session.add_all([initial_tenant, mapped_tenant])
        await session.commit()
        await session.refresh(initial_tenant)
        await session.refresh(mapped_tenant)

        organization = Organization(id=TEST_ORG_ID, name="OIDC Org", tenant_id=mapped_tenant.id)
        user = User(
            username=TEST_USERNAME,
            hashed_password=None,
            is_active=True,
            role=UserRole.USER,
            tenant_id=initial_tenant.id,
            idp_subject=claims["sub"],
        )
        session.add_all([organization, user])
        await session.commit()

    headers = {"Authorization": f"Bearer {keycloak_token}"}
    profile_response = await api_client.get("/users/me", headers=headers)
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["username"] == TEST_USERNAME

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.idp_subject == claims["sub"]))
        refreshed_user = result.scalars().first()
        assert refreshed_user is not None
        assert refreshed_user.tenant_id == mapped_tenant.id


@pytest.mark.asyncio
async def test_anonymous_access_is_forbidden(api_client):
    response = await api_client.get("/status")
    assert response.status_code == 401
