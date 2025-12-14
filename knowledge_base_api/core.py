import datetime
import uuid
from typing import Annotated, Optional

import aioboto3
import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode
from passlib.context import CryptContext
from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Organization, Tenant, User, UserRole


class Settings(BaseSettings):
    database_url: str
    s3_endpoint_url: Optional[str] = None
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket_name: str
    s3_region: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_minutes: int = 60 * 24 * 30

    oidc_client_id: Optional[str] = None
    oidc_issuer: Optional[str] = None
    oidc_jwks_url: Optional[str] = None

    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin123"
    initial_tenant_name: str = "Default Tenant"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
s3_session = aioboto3.Session()

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

_jwks_cache: Optional[dict] = None
_jwks_cached_at: Optional[datetime.datetime] = None
_JWKS_TTL_SECONDS = 300


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password is None:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta or datetime.timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta or datetime.timedelta(minutes=settings.refresh_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str, expected_type: Optional[str] = None) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    return payload


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def get_s3_client():
    async with s3_session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    ) as s3:
        yield s3


async def _fetch_jwks():
    if not settings.oidc_jwks_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OIDC JWKS url is not configured")
    async with httpx.AsyncClient() as client:
        response = await client.get(settings.oidc_jwks_url, timeout=10)
        response.raise_for_status()
        return response.json().get("keys", [])


async def _get_jwks():
    global _jwks_cache, _jwks_cached_at
    now = datetime.datetime.utcnow()
    if _jwks_cache and _jwks_cached_at and (now - _jwks_cached_at).total_seconds() < _JWKS_TTL_SECONDS:
        return _jwks_cache
    _jwks_cache = await _fetch_jwks()
    _jwks_cached_at = now
    return _jwks_cache


async def _get_signing_key(token: str):
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    jwks = await _get_jwks()
    for key in jwks:
        if key.get("kid") == kid:
            return key
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signing key not found for token")


async def validate_oidc_token(token: str) -> dict:
    if not (settings.oidc_client_id and settings.oidc_issuer and settings.oidc_jwks_url):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OIDC is not configured")
    try:
        signing_key = await _get_signing_key(token)
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[signing_key.get("alg", "RS256")],
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer,
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def resolve_tenant_id(db: AsyncSession, org_id: Optional[str]) -> Optional[uuid.UUID]:
    if not org_id:
        return None
    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    organization = result.scalars().first()
    return organization.tenant_id if organization else None


async def get_or_create_tenant(db: AsyncSession, name: str) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.name == name))
    tenant = result.scalars().first()
    if tenant:
        return tenant
    tenant = Tenant(name=name)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    claims = getattr(request.state, "oidc_claims", None)
    if not claims:
        try:
            claims = decode_token(token, expected_type="access")
        except HTTPException:
            claims = await validate_oidc_token(token)

    subject = claims.get("sub")
    if not subject:
        raise credentials_exception

    org_id = claims.get("org_id")
    tenant_id = await resolve_tenant_id(db, org_id) if org_id else None

    query = select(User).where(User.idp_subject == subject)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user:
        raise credentials_exception
    if tenant_id and user.tenant_id != tenant_id:
        user.tenant_id = tenant_id
        db.add(user)
        await db.commit()
        await db.refresh(user)
    if not user.is_active:
        raise credentials_exception
    return user
