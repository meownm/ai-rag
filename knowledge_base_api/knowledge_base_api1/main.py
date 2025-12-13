# ===============================================================================
# knowledge_base_api/main.py - Финальная версия
#
# Включает:
# - Multi-tenancy (полная изоляция данных по тенантам)
# - Аутентификацию по JWT через базу данных
# - Автоматическое создание таблиц и начальное заполнение при старте
# - Интеграцию с S3 (MinIO)
# - Структурированное логирование и трассировку
# - Глубокий Health Check
# ===============================================================================

import datetime
import logging
import uuid
import enum
from contextvars import ContextVar
from logging.config import dictConfig
from typing import List, Optional, Annotated

# --- Core FastAPI & Pydantic Imports ---
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, status, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# --- SQLAlchemy Imports ---
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func, select, Boolean, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- Security Imports ---
from jose import JWTError, jwt
from passlib.context import CryptContext

# --- S3 Imports ---
import aioboto3
from botocore.exceptions import ClientError

# ===============================================================================
# 1. КОНФИГУРАЦИЯ, ЛОГИРОВАНИЕ, ТРАССИРОВКА
# ===============================================================================

class Settings(BaseSettings):
    database_url: str; s3_endpoint_url: Optional[str] = None; s3_access_key_id: str
    s3_secret_access_key: str; s3_bucket_name: str; s3_region: str; secret_key: str
    algorithm: str; access_token_expire_minutes: int
    class Config:
        env_file = ".env"
        extra = "ignore" # Игнорируем лишние переменные из .env

# --- Logging & Tracing ---
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = trace_id_var.get()
        return True

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s %(trace_id)s",
        },
    },
    "filters": {
        "trace_id_filter": {
            "()": "main.TraceIdFilter", # <-- ИСПРАВЛЕНО: Указан явный путь к классу
        }
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["trace_id_filter"],
        },
    },
    "root": {
        "handlers": ["default"],
        "level": "INFO",
    },
}
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Инициализируем настройки ПОСЛЕ настройки логирования
settings = Settings()

# ===============================================================================
# 2. БАЗА ДАННЫХ
# ===============================================================================
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

# ===============================================================================
# 3. МОДЕЛИ БАЗЫ ДАННЫХ (SQLAlchemy) С КОММЕНТАРИЯМИ
# ===============================================================================

class UserRole(str, enum.Enum): ADMIN = "admin"; USER = "user"
class ItemType(str, enum.Enum): FILE = "file"; LINK = "link"
class OperationType(str, enum.Enum): CREATED = "created"; UPDATED = "updated"; DELETED = "deleted"; STATUS_CHANGED = "status_changed"
class StatusType(str, enum.Enum): NEW = "new"; PROCESSING = "processing"; DONE = "done"; FAILED = "failed"

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Публичный уникальный идентификатор тенанта (PK)")
    name = Column(String, nullable=False, comment="Человекочитаемое название тенанта (Базы Знаний)")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, comment="Дата и время создания тенанта")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Публичный уникальный идентификатор пользователя (PK)")
    username = Column(String, unique=True, index=True, nullable=False, comment="Уникальный логин пользователя для входа")
    hashed_password = Column(String, nullable=False, comment="Хеш пароля, сгенерированный с помощью argon2")
    is_active = Column(Boolean, default=True, comment="Флаг, позволяющий деактивировать пользователя без удаления")
    role = Column(String, nullable=False, default=UserRole.USER, comment="Роль пользователя в системе (admin или user)")
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, comment="Внешний ключ, связывающий пользователя с его тенантом (FK)")
    tenant = relationship("Tenant")

class KnowledgeEvent(Base):
    __tablename__ = "knowledge_events"
    id = Column(Integer, primary_key=True, comment="Суррогатный первичный ключ для самого события (PK)")
    item_uuid = Column(UUID(as_uuid=True), nullable=False, index=True, comment="Логический идентификатор элемента, связывающий всю его историю")
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True, comment="Идентификатор тенанта, которому принадлежит событие (FK)")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, comment="Идентификатор пользователя, совершившего действие (FK)")
    operation = Column(String, nullable=False, comment="Тип операции (created, updated, deleted, status_changed)")
    operation_time = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, comment="Точное время совершения операции")
    item_name = Column(String, nullable=False, comment="Название файла или ссылки на момент события")
    item_type = Column(String, nullable=False, comment="Тип элемента (file или link)")
    content = Column(String, nullable=True, comment="Содержимое: S3-ключ для файла или URL для ссылки")
    size = Column(BigInteger, nullable=True, comment="Размер файла в байтах (для ссылок - NULL)")
    status = Column(String, nullable=False, comment="Статус элемента на момент события (new, processing, done, failed)")
    __table_args__ = (Index('ix_knowledge_events_status_op', "status", "operation"),)

# ===============================================================================
# 4. СХЕМЫ ДАННЫХ API (Pydantic) С КОММЕНТАРИЯМИ
# ===============================================================================
class UserPublic(BaseModel):
    id: uuid.UUID = Field(description="Уникальный ID пользователя"); username: str = Field(description="Логин пользователя")
    role: UserRole = Field(description="Роль пользователя в системе"); is_active: bool = Field(description="Активен ли пользователь")
    class Config: from_attributes = True

class ItemResponse(BaseModel):
    item_uuid: uuid.UUID = Field(description="Логический ID элемента"); item_name: str = Field(description="Название элемента")
    item_type: ItemType = Field(description="Тип элемента (файл/ссылка)"); size: Optional[int] = Field(description="Размер файла в байтах")
    status: StatusType = Field(description="Текущий статус элемента"); operation: OperationType = Field(description="Последняя выполненная операция")
    operation_time: datetime.datetime = Field(description="Время последней операции")
    class Config: from_attributes = True

class LinkCreate(BaseModel): name: str; url: str
class LinkUpdate(BaseModel): name: Optional[str] = None; url: Optional[str] = None
class StatusUpdate(BaseModel): status: StatusType
class FileDownloadResponse(BaseModel): download_url: str
class ComponentStatus(BaseModel): status: str; details: Optional[str] = None
class DeepHealthCheckResponse(BaseModel): api: ComponentStatus; database: ComponentStatus; storage: ComponentStatus

# ===============================================================================
# 5. БЕЗОПАСНОСТЬ, S3 и ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ===============================================================================
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
s3_session = aioboto3.Session()

app = FastAPI(title="Knowledge Base API (Production)", version="3.1.0")

async def seed_initial_data(db: AsyncSession):
    logger.info("Checking for initial data seeding...")
    try:
        default_tenant_name = "Тест"; result = await db.execute(select(Tenant).where(Tenant.name == default_tenant_name)); tenant = result.scalars().first()
        if not tenant: logger.warning(f"Default tenant '{default_tenant_name}' not found, creating it."); tenant = Tenant(name=default_tenant_name); db.add(tenant); await db.commit(); await db.refresh(tenant); logger.info(f"Default tenant '{tenant.name}' created with id {tenant.id}")
        else: logger.info("Default tenant already exists.")
        result = await db.execute(select(User).where(User.username == DEFAULT_ADMIN_USERNAME)); admin_user = result.scalars().first()
        if not admin_user: logger.warning(f"Default admin user '{DEFAULT_ADMIN_USERNAME}' not found, creating it."); hashed_password = pwd_context.hash(DEFAULT_ADMIN_PASSWORD); admin_user = User(username=DEFAULT_ADMIN_USERNAME, hashed_password=hashed_password, role=UserRole.ADMIN, tenant_id=tenant.id); db.add(admin_user); await db.commit(); logger.info(f"Default admin user '{admin_user.username}' created.")
        else: logger.info("Default admin user already exists.")
    except Exception as e: logger.error(f"An error occurred during initial data seeding: {e}", exc_info=True); await db.rollback(); raise

@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...");
    async with engine.begin() as conn: logger.info("Checking and creating tables if they do not exist..."); await conn.run_sync(Base.metadata.create_all); logger.info("Tables are ready.")
    async with AsyncSessionLocal() as session: await seed_initial_data(session)

@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4())); token = trace_id_var.set(trace_id)
    logger.info("Request started", extra={"path": request.url.path, "method": request.method})
    response = await call_next(request); response.headers["X-Request-ID"] = trace_id; trace_id_var.reset(token)
    return response

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session: yield session

async def get_s3_client():
    async with s3_session.client("s3", endpoint_url=settings.s3_endpoint_url, aws_access_key_id=settings.s3_access_key_id, aws_secret_access_key=settings.s3_secret_access_key, region_name=settings.s3_region) as s3:
        yield s3

def verify_password(plain_password, hashed_password): return pwd_context.verify(plain_password, hashed_password)
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy(); expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=settings.access_token_expire_minutes)); to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm]); user_id: str = payload.get("user_id")
        if user_id is None: raise credentials_exception
    except JWTError: raise credentials_exception
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active: raise credentials_exception
    return user

async def get_latest_event_for_item(db: AsyncSession, item_uuid: uuid.UUID, tenant_id: uuid.UUID) -> Optional[KnowledgeEvent]:
    result = await db.execute(select(KnowledgeEvent).where(KnowledgeEvent.item_uuid == item_uuid, KnowledgeEvent.tenant_id == tenant_id).order_by(KnowledgeEvent.operation_time.desc()).limit(1))
    return result.scalars().first()

# ===============================================================================
# 6. API ЭНДПОИНТЫ
# ===============================================================================

@app.post("/token", tags=["Auth"])
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form_data.username)); user = result.scalars().first()
    if not user or not user.is_active or not verify_password(form_data.password, user.hashed_password): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    token_data = {"sub": user.username, "user_id": str(user.id), "tenant_id": str(user.tenant_id)}
    access_token = create_access_token(data=token_data); return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=UserPublic, tags=["Users"])
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user

@app.post("/files", response_model=ItemResponse, status_code=201, tags=["Items"])
async def add_file(file: UploadFile, name: Optional[str] = Form(None), db: AsyncSession = Depends(get_db), s3_client=Depends(get_s3_client), current_user: User = Depends(get_current_user)):
    file_name = name or file.filename; item_uuid = uuid.uuid4(); s3_object_key = f"{current_user.tenant_id}/{item_uuid}/{file_name}"
    try: await s3_client.upload_fileobj(file.file, settings.s3_bucket_name, s3_object_key)
    except ClientError as e: logger.error("Failed to upload to S3", exc_info=True); raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")
    new_event = KnowledgeEvent(item_uuid=item_uuid, tenant_id=current_user.tenant_id, user_id=current_user.id, operation=OperationType.CREATED, item_name=file_name, item_type=ItemType.FILE, content=s3_object_key, size=file.size, status=StatusType.NEW)
    db.add(new_event); await db.commit(); await db.refresh(new_event); return new_event

@app.post("/links", response_model=ItemResponse, status_code=201, tags=["Items"])
async def add_link(link: LinkCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_event = KnowledgeEvent(item_uuid=uuid.uuid4(), tenant_id=current_user.tenant_id, user_id=current_user.id, operation=OperationType.CREATED, item_name=link.name, item_type=ItemType.LINK, content=link.url, status=StatusType.NEW)
    db.add(new_event); await db.commit(); await db.refresh(new_event); return new_event

@app.get("/items", response_model=List[ItemResponse], tags=["Items"])
async def get_current_state_of_all_items(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    subquery = select(KnowledgeEvent, func.row_number().over(partition_by=KnowledgeEvent.item_uuid, order_by=KnowledgeEvent.operation_time.desc()).label("rn")).where(KnowledgeEvent.tenant_id == current_user.tenant_id).subquery()
    query = select(subquery).where(subquery.c.rn == 1, subquery.c.operation != OperationType.DELETED)
    result = await db.execute(query); return result.all()

@app.get("/items/search", response_model=List[ItemResponse], tags=["Items"])
async def search_items(q: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    subquery = select(KnowledgeEvent, func.row_number().over(partition_by=KnowledgeEvent.item_uuid, order_by=KnowledgeEvent.operation_time.desc()).label("rn")).where(KnowledgeEvent.tenant_id == current_user.tenant_id).subquery()
    query = select(subquery).where(subquery.c.rn == 1, subquery.c.operation != OperationType.DELETED, subquery.c.item_name.ilike(f"%{q}%"))
    result = await db.execute(query); return result.all()

@app.get("/files/{item_uuid}/download", response_model=FileDownloadResponse, tags=["Items"])
async def get_file_download_url(item_uuid: uuid.UUID, db: AsyncSession = Depends(get_db), s3_client=Depends(get_s3_client), current_user: User = Depends(get_current_user)):
    latest_event = await get_latest_event_for_item(db, item_uuid, current_user.tenant_id)
    if not latest_event or latest_event.operation == OperationType.DELETED or latest_event.item_type != ItemType.FILE: raise HTTPException(status_code=404, detail="File not found")
    try: url = await s3_client.generate_presigned_url('get_object', Params={'Bucket': settings.s3_bucket_name, 'Key': latest_event.content}, ExpiresIn=3600); return {"download_url": url}
    except ClientError as e: logger.error("Failed to generate presigned S3 URL", exc_info=True); raise HTTPException(status_code=500, detail="Could not generate download link.")

@app.delete("/items/{item_uuid}", status_code=status.HTTP_204_NO_CONTENT, tags=["Items"])
async def delete_item(item_uuid: uuid.UUID, db: AsyncSession = Depends(get_db), s3_client=Depends(get_s3_client), current_user: User = Depends(get_current_user)):
    latest_event = await get_latest_event_for_item(db, item_uuid, current_user.tenant_id)
    if not latest_event or latest_event.operation == OperationType.DELETED: raise HTTPException(status_code=404, detail="Item not found")
    if latest_event.item_type == ItemType.FILE:
        try: await s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=latest_event.content)
        except ClientError: logger.error("Failed to delete object from S3, but proceeding with DB event", exc_info=True)
    delete_event = KnowledgeEvent(item_uuid=item_uuid, tenant_id=current_user.tenant_id, user_id=current_user.id, operation=OperationType.DELETED, item_name=latest_event.item_name, item_type=latest_event.item_type, status=latest_event.status)
    db.add(delete_event); await db.commit(); return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.patch("/items/{item_uuid}/status", response_model=ItemResponse, tags=["Items"])
async def update_item_status(item_uuid: uuid.UUID, status_update: StatusUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    latest_event = await get_latest_event_for_item(db, item_uuid, current_user.tenant_id)
    if not latest_event or latest_event.operation == OperationType.DELETED: raise HTTPException(status_code=404, detail="Item not found")
    if latest_event.status == status_update.status: return latest_event
    status_change_event = KnowledgeEvent(item_uuid=item_uuid, tenant_id=current_user.tenant_id, user_id=current_user.id, operation=OperationType.STATUS_CHANGED, item_name=latest_event.item_name, item_type=latest_event.item_type, content=latest_event.content, size=latest_event.size, status=status_update.status)
    db.add(status_change_event); await db.commit(); await db.refresh(status_change_event); return status_change_event

@app.get("/health", response_model=DeepHealthCheckResponse, tags=["Monitoring"])
async def health_check(db: AsyncSession = Depends(get_db), s3_client=Depends(get_s3_client)):
    health = { "api": {"status": "ok"}, "database": {"status": "ok"}, "storage": {"status": "ok"} }; http_status = status.HTTP_200_OK
    try: await db.execute(text("SELECT 1"))
    except Exception as e: health["database"] = {"status": "down", "details": str(e)}; http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    try: await s3_client.head_bucket(Bucket=settings.s3_bucket_name)
    except Exception as e: health["storage"] = {"status": "down", "details": str(e)}; http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(content=DeepHealthCheckResponse(**health).model_dump_json(), status_code=http_status, media_type="application/json")