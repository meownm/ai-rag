"""
Ядро приложения.

Этот модуль содержит инфраструктурный код:
1.  Settings: Класс конфигурации, считывающий переменные из .env файла.
2.  Database & S3: Создание асинхронного движка SQLAlchemy и сессии aioboto3.
3.  Security: Утилиты для хеширования паролей (passlib) и работы с JWT (jose).
4.  Dependencies: Общие зависимости FastAPI (get_db, get_s3_client, get_current_user),
    которые внедряются в эндпоинты.
"""
import datetime
import uuid
from typing import Annotated, Optional

import aioboto3
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (AsyncSession, create_async_engine)
from sqlalchemy.orm import sessionmaker

from models import User

# ===============================================================================
# 1. КОНФИГУРАЦИЯ
# ===============================================================================
class Settings(BaseSettings):
    """
    Класс для управления конфигурацией приложения.
    Считывает переменные из .env файла с помощью pydantic-settings.
    """
    # --- Основные настройки ---
    database_url: str
    s3_endpoint_url: Optional[str] = None
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket_name: str
    s3_region: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    # --- Настройки для первоначального запуска ---
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin123"
    initial_tenant_name: str = "Default Tenant"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ===============================================================================
# 2. БАЗА ДАННЫХ И S3
# ===============================================================================
# Создаем асинхронный движок для SQLAlchemy. 'echo=False' отключает логирование SQL-запросов.
engine = create_async_engine(settings.database_url, echo=False)

# Фабрика для создания асинхронных сессий SQLAlchemy.
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

# Создаем сессию aioboto3 для асинхронной работы с S3.
s3_session = aioboto3.Session()

# ===============================================================================
# 3. БЕЗОПАСНОСТЬ
# ===============================================================================
# Контекст для хеширования и проверки паролей. Используется современный и надежный алгоритм argon2.
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Схема безопасности FastAPI для получения токена из заголовка Authorization: Bearer <token>.
# tokenUrl указывает эндпоинт, где можно получить токен.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, соответствует ли обычный пароль хешу."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Создает JWT-токен доступа."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

# ===============================================================================
# 4. ЗАВИСИМОСТИ (DEPENDENCIES)
# ===============================================================================

async def get_db() -> AsyncSession:
    """
    Зависимость FastAPI для получения асинхронной сессии БД.
    Обеспечивает, что сессия будет создана для каждого запроса и закрыта после него.
    """
    async with AsyncSessionLocal() as session:
        yield session

async def get_s3_client():
    """
    Зависимость FastAPI для получения асинхронного клиента S3.
    Обеспечивает корректное управление сессией клиента.
    """
    async with s3_session.client("s3", endpoint_url=settings.s3_endpoint_url,
                                 aws_access_key_id=settings.s3_access_key_id,
                                 aws_secret_access_key=settings.s3_secret_access_key,
                                 region_name=settings.s3_region) as s3:
        yield s3

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)) -> User:
    """
    Зависимость для проверки JWT-токена и получения текущего пользователя.
    Внедряется во все защищенные эндпоинты.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise credentials_exception
    return user