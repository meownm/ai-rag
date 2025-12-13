"""
Определения структур данных проекта.

Этот модуль содержит:
1.  Enum'ы: Перечисления для стандартизации строковых значений в коде и БД.
2.  Модели SQLAlchemy: Классы, описывающие таблицы в базе данных.
3.  Схемы Pydantic: Классы для валидации данных в API запросах и форматирования ответов.
"""
import datetime
import enum
import uuid
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey,
                        Index, Integer, String, func, Text)
from sqlalchemy.dialects.postgresql import JSON, TSVECTOR, UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import UserDefinedType


# ===============================================================================
# 0. Вспомогательные типы
# ===============================================================================

class VECTOR(UserDefinedType):
    """
    Кастомный тип SQLAlchemy для поддержки типа 'vector' из расширения pgvector.
    Это позволяет использовать `Column(VECTOR)` в моделях.
    """
    def get_col_spec(self, **kw):
        return "vector"

# ===============================================================================
# 1. ОБЩИЕ ENUM'ы
# ===============================================================================

class UserRole(str, enum.Enum):
    """Роли пользователей в системе."""
    ADMIN = "admin"
    USER = "user"

class ItemType(str, enum.Enum):
    """Типы элементов в базе знаний (файл или ссылка)."""
    FILE = "file"
    LINK = "link"

class OperationType(str, enum.Enum):
    """
    Типы операций над элементом, записываемые в историю (event sourcing).
    """
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGED = "status_changed"

class StatusType(str, enum.Enum):
    """Статусы обработки элемента."""
    NEW = "new"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

# ===============================================================================
# 2. МОДЕЛИ БАЗЫ ДАННЫХ (SQLAlchemy)
# ===============================================================================
Base = declarative_base()

class Tenant(Base):
    """Таблица тенантов (арендаторов). Каждый тенант - это изолированная база знаний."""
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Уникальный идентификатор тенанта (PK)")
    name = Column(String, nullable=False, comment="Человекочитаемое название тенанта")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, comment="Дата и время создания")

class User(Base):
    """Таблица пользователей системы."""
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Уникальный идентификатор пользователя (PK)")
    username = Column(String, unique=True, index=True, nullable=False, comment="Уникальный логин для входа")
    hashed_password = Column(String, nullable=False, comment="Хеш пароля (argon2)")
    is_active = Column(Boolean, default=True, comment="Флаг активности пользователя")
    role = Column(String, nullable=False, default=UserRole.USER, comment="Роль пользователя (admin/user)")
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, comment="Ключ тенанта, к которому привязан пользователь (FK)")
    tenant = relationship("Tenant")

class KnowledgeEvent(Base):
    """Таблица событий, хранящая всю историю изменений элементов базы знаний."""
    __tablename__ = "knowledge_events"
    id = Column(Integer, primary_key=True, comment="Суррогатный первичный ключ события (PK)")
    item_uuid = Column(UUID(as_uuid=True), nullable=False, index=True, comment="Логический ID элемента, связывающий всю его историю")
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True, comment="ID тенанта для изоляции данных (FK)")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, comment="ID пользователя, совершившего действие (FK)")
    operation = Column(String, nullable=False, comment="Тип операции (created, updated, deleted, ...)")
    operation_time = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, comment="Точное время операции")
    item_name = Column(String, nullable=False, comment="Название файла или ссылки на момент события")
    item_type = Column(String, nullable=False, comment="Тип элемента (file/link)")
    content = Column(String, nullable=True, comment="Содержимое: S3 URI для файла или URL для ссылки")
    size = Column(BigInteger, nullable=True, comment="Размер файла в байтах (NULL для ссылок)")
    status = Column(String, nullable=False, comment="Статус элемента на момент события (new, processing, ...)")
    s3_path = Column(String, nullable=True, comment="Полный путь к объекту в S3-бакете (ключ объекта)")
    __table_args__ = (Index('ix_knowledge_events_status_op', "status", "operation"),)

# ===============================================================================
# 3. СХЕМЫ ДАННЫХ API (Pydantic)
# ===============================================================================

class UserPublic(BaseModel):
    """Схема для публичного представления данных о пользователе."""
    id: uuid.UUID = Field(description="Уникальный ID пользователя")
    username: str = Field(description="Логин пользователя")
    role: UserRole = Field(description="Роль пользователя в системе")
    is_active: bool = Field(description="Активен ли пользователь")
    class Config: from_attributes = True

class ItemResponse(BaseModel):
    """Основная схема для ответа API, представляющая состояние элемента."""
    item_uuid: uuid.UUID = Field(description="Логический ID элемента, связывающий его версии")
    item_name: str = Field(description="Название элемента")
    item_type: ItemType = Field(description="Тип элемента (файл/ссылка)")
    size: Optional[int] = Field(None, description="Размер файла в байтах")
    status: StatusType = Field(description="Текущий статус элемента")
    operation: OperationType = Field(description="Последняя выполненная операция")
    operation_time: datetime.datetime = Field(description="Время последней операции")
    action: Optional[str] = Field(None, description="Действие, выполненное в рамках запроса ('created' или 'updated')")
    class Config: from_attributes = True

class LinkCreate(BaseModel):
    """Схема для создания новой ссылки."""
    name: str = Field(description="Название ссылки")
    url: str = Field(description="URL-адрес")

class StatusUpdate(BaseModel):
    """Схема для обновления статуса элемента."""
    status: StatusType = Field(description="Новый статус элемента")

class FileDownloadResponse(BaseModel):
    """Схема ответа для получения ссылки на скачивание файла."""
    download_url: str = Field(description="Временная подписанная ссылка (presigned URL) для скачивания файла из S3")

class ComponentStatus(BaseModel):
    """Вспомогательная схема для Health Check."""
    status: str = Field(description="Состояние компонента ('ok' или 'down')")
    details: Optional[str] = Field(None, description="Дополнительная информация об ошибке")

class DeepHealthCheckResponse(BaseModel):
    """Схема для ответа 'глубокой' проверки состояния сервиса."""
    api: ComponentStatus = Field(description="Состояние API")
    database: ComponentStatus = Field(description="Состояние подключения к базе данных")
    storage: ComponentStatus = Field(description="Состояние подключения к S3-хранилищу")

class StatusResponse(BaseModel):
    """Схема для ответа эндпоинта /status со статистикой."""
    files_uploaded_by_user: int
    documents_in_tenant: int
    chunks_in_tenant: int
    chunks_with_embedding: int
    chunks_with_metadata: int