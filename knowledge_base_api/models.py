import datetime
import enum
import uuid
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSON, TSVECTOR, UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import UserDefinedType


class VECTOR(UserDefinedType):
    def get_col_spec(self, **kw):
        return "vector"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class ItemType(str, enum.Enum):
    FILE = "file"
    LINK = "link"


class OperationType(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGED = "status_changed"


class StatusType(str, enum.Enum):
    NEW = "new"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    tenant = relationship("Tenant")
    user_roles = relationship("UserOrganizationRole", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(String, nullable=False, default=UserRole.USER)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    idp_subject = Column(String, unique=True, index=True, nullable=True)

    tenant = relationship("Tenant")
    organizations = relationship("UserOrganizationRole", back_populates="user", cascade="all, delete-orphan")


class UserOrganizationRole(Base):
    __tablename__ = "user_organization_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_org"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    role = Column(String, nullable=False, default=UserRole.USER)

    user = relationship("User", back_populates="organizations")
    organization = relationship("Organization", back_populates="user_roles")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    embedding = Column(VECTOR, nullable=True)
    search_vector = Column(TSVECTOR, nullable=True)


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    text = Column(Text, nullable=False)
    metadata = Column(JSON, nullable=True)
    embedding = Column(VECTOR, nullable=True)

    document = relationship("Document", backref="chunks")


class KnowledgeEvent(Base):
    __tablename__ = "knowledge_events"
    __table_args__ = (Index("ix_knowledge_events_status_op", "status", "operation"),)

    id = Column(Integer, primary_key=True)
    item_uuid = Column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    operation = Column(String, nullable=False)
    operation_time = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    item_name = Column(String, nullable=False)
    item_type = Column(String, nullable=False)
    content = Column(String, nullable=True)
    size = Column(BigInteger, nullable=True)
    status = Column(String, nullable=False)
    s3_path = Column(String, nullable=True)


class UserTelegramLink(Base):
    __tablename__ = "user_telegram_links"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    state_token = Column(String, unique=True, nullable=False)
    verified_at = Column(DateTime, nullable=True)

    user = relationship("User")


class UserPublic(BaseModel):
    id: uuid.UUID = Field(description="Уникальный ID пользователя")
    username: str = Field(description="Логин пользователя")
    role: UserRole = Field(description="Роль пользователя в системе")
    is_active: bool = Field(description="Активен ли пользователь")

    class Config:
        from_attributes = True


class ItemResponse(BaseModel):
    item_uuid: uuid.UUID = Field(description="Логический ID элемента, связывающий его версии")
    item_name: str = Field(description="Название элемента")
    item_type: ItemType = Field(description="Тип элемента (файл/ссылка)")
    size: Optional[int] = Field(None, description="Размер файла в байтах")
    status: StatusType = Field(description="Текущий статус элемента")
    operation: OperationType = Field(description="Последняя выполненная операция")
    operation_time: datetime.datetime = Field(description="Время последней операции")
    action: Optional[str] = Field(None, description="Действие, выполненное в рамках запроса ('created' или 'updated')")

    class Config:
        from_attributes = True


class LinkCreate(BaseModel):
    name: str = Field(description="Название ссылки")
    url: str = Field(description="URL-адрес")


class StatusUpdate(BaseModel):
    status: StatusType = Field(description="Новый статус элемента")


class FileDownloadResponse(BaseModel):
    download_url: str = Field(description="Временная подписанная ссылка (presigned URL) для скачивания файла из S3")


class ComponentStatus(BaseModel):
    status: str = Field(description="Состояние компонента ('ok' или 'down')")
    details: Optional[str] = Field(None, description="Дополнительная информация об ошибке")


class DeepHealthCheckResponse(BaseModel):
    api: ComponentStatus = Field(description="Состояние API")
    database: ComponentStatus = Field(description="Состояние подключения к базе данных")
    storage: ComponentStatus = Field(description="Состояние подключения к S3-хранилищу")


class StatusResponse(BaseModel):
    files_uploaded_by_user: int
    documents_in_tenant: int
    chunks_in_tenant: int
    chunks_with_embedding: int
    chunks_with_metadata: int


class OrganizationCreate(BaseModel):
    name: str = Field(description="Название организации")
    tenant_name: Optional[str] = Field(None, description="Название тенанта, если нужно создать новый")


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    tenant_id: uuid.UUID

    class Config:
        from_attributes = True


class UserInviteRequest(BaseModel):
    username: str = Field(description="Отображаемое имя пользователя")
    idp_subject: str = Field(description="Внешний идентификатор пользователя в IdP")
    role: UserRole = Field(default=UserRole.USER)


class UserOrganizationLink(BaseModel):
    user_id: uuid.UUID
    username: str
    organization_id: uuid.UUID
    role: UserRole

    class Config:
        from_attributes = True


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TelegramLinkStart(BaseModel):
    telegram_id: int
    username: Optional[str] = None


class TelegramLinkStatus(BaseModel):
    state_token: str
    verified: bool
