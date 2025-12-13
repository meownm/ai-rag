"""
Сервисный слой приложения.

Этот модуль инкапсулирует всю бизнес-логику, отделяя ее от HTTP-уровня (роутеров).
Функции здесь работают с объектами базы данных и выполняют операции,
такие как создание/обновление файлов, поиск и т.д.
"""
import datetime
import logging
import uuid
from typing import List, Optional, Tuple

from botocore.exceptions import ClientError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core import settings
from models import (ItemType, KnowledgeEvent, LinkCreate, OperationType, User)

logger = logging.getLogger(__name__)

# --- Кастомные исключения для сервисного слоя ---
class ServiceError(Exception):
    """Базовый класс для ошибок сервисного слоя."""
    pass

class S3UploadError(ServiceError):
    """Исключение, возникающее при ошибке загрузки в S3."""
    pass


async def get_latest_event_for_item(db: AsyncSession, item_uuid: uuid.UUID, tenant_id: uuid.UUID) -> Optional[KnowledgeEvent]:
    """Находит самое последнее событие для указанного элемента в рамках тенанта."""
    result = await db.execute(
        select(KnowledgeEvent)
        .where(KnowledgeEvent.item_uuid == item_uuid, KnowledgeEvent.tenant_id == tenant_id)
        .order_by(KnowledgeEvent.operation_time.desc())
        .limit(1)
    )
    return result.scalars().first()

async def get_active_item_by_name(db: AsyncSession, user: User, item_name: str) -> Optional[KnowledgeEvent]:
    """
    Находит последнее активное событие для элемента по его имени.
    """
    subquery = select(
        KnowledgeEvent,
        func.row_number().over(
            partition_by=KnowledgeEvent.item_uuid,
            order_by=KnowledgeEvent.operation_time.desc()
        ).label("rn")
    ).where(KnowledgeEvent.tenant_id == user.tenant_id).subquery()

    query = select(subquery).where(
        subquery.c.rn == 1,
        subquery.c.operation != OperationType.DELETED,
        subquery.c.item_name == item_name,
        subquery.c.item_type == ItemType.FILE
    )
    result = await db.execute(query)
    return result.first()


async def create_file_event(
    db: AsyncSession, s3_client, user: User, file_stream, filename: str, file_size: int
) -> Tuple[KnowledgeEvent, str]:
    """
    Создает или обновляет (заменяет) файл.

    АЛГОРИТМ (ОБНОВЛЕННЫЙ):
    1.  **Проверка существования**: Ищется активный файл с таким же именем.
    2.  **Ветка "Обновление" (файл найден)**:
        a.  Действие помечается как `'updated'`.
        b.  Создается событие `DELETED` со **старым item_uuid**, чтобы "закрыть" историю старого файла.
    3.  **Ветка "Создание" (файл не найден)**:
        a.  Действие помечается как `'created'`.
    4.  **Создание нового элемента**: Вне зависимости от ветки, генерируется
        **новый item_uuid** для нового файла.
    5.  **Загрузка в S3**: Файл загружается/перезаписывается в S3.
    6.  **Создание новой записи**: Создается новое событие `CREATED` с **новым item_uuid**.
    7.  **Транзакция**: Все изменения (`DELETED` для старого, `CREATED` для нового)
        сохраняются в БД атомарно.
    """
    existing_event = await get_active_item_by_name(db, user, filename)
    now = datetime.datetime.utcnow()

    s3_object_key = (
        f"{user.tenant_id}/"
        f"{user.id}/"
        f"{ItemType.FILE.value}/"
        f"{now.year}/{now.month:02d}/{now.day:02d}/"
        f"{filename}"
    )

    if existing_event:
        logger.info(f"File '{filename}' already exists. Replacing it.")
        action = "updated"
        
        # Создаем событие DELETED для СТАРОГО item_uuid, чтобы закрыть его историю.
        delete_event = KnowledgeEvent(
            item_uuid=existing_event.item_uuid, # Используем старый UUID
            tenant_id=user.tenant_id, user_id=user.id,
            operation=OperationType.DELETED,
            operation_time=existing_event.operation_time, item_name=filename,
            item_type=ItemType.FILE, content=existing_event.content,
            size=existing_event.size, status=existing_event.status,
            s3_path=existing_event.s3_path
        )
        db.add(delete_event)
        
    else:
        logger.info(f"Creating new file '{filename}'.")
        action = "created"

    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
    # Мы ВСЕГДА создаем новый item_uuid для записи CREATED.
    # Это разрывает прямую связь по ID между старой и новой версией.
    new_item_uuid = uuid.uuid4()

    try:
        file_stream.seek(0)
        await s3_client.upload_fileobj(file_stream, settings.s3_bucket_name, s3_object_key)
    except ClientError as e:
        logger.error("Failed to upload to S3", exc_info=True)
        raise S3UploadError(f"S3 upload failed: {e}")

    # Создаем новую запись CREATED с НОВЫМ item_uuid.
    create_event = KnowledgeEvent(
        item_uuid=new_item_uuid, # Используем новый UUID
        tenant_id=user.tenant_id, user_id=user.id,
        operation=OperationType.CREATED,
        item_name=filename, item_type=ItemType.FILE,
        content=f"s3://{settings.s3_bucket_name}/{s3_object_key}",
        size=file_size, status="new", s3_path=s3_object_key
    )
    db.add(create_event)

    await db.commit()
    await db.refresh(create_event)
    
    return create_event, action

async def create_link_event(db: AsyncSession, user: User, link_data: LinkCreate) -> KnowledgeEvent:
    """Создает событие для новой ссылки."""
    new_event = KnowledgeEvent(
        item_uuid=uuid.uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        operation=OperationType.CREATED,
        item_name=link_data.name,
        item_type=ItemType.LINK,
        content=link_data.url,
        status="new"
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    return new_event

async def get_all_active_items(db: AsyncSession, user: User) -> List[KnowledgeEvent]:
    """
    Возвращает список последних состояний всех активных элементов для пользователя.
    """
    subquery = select(
        KnowledgeEvent,
        func.row_number().over(
            partition_by=KnowledgeEvent.item_uuid,
            order_by=KnowledgeEvent.operation_time.desc()
        ).label("rn")
    ).where(KnowledgeEvent.tenant_id == user.tenant_id).subquery()

    query = select(subquery).where(
        subquery.c.rn == 1,
        subquery.c.operation != OperationType.DELETED
    )
    result = await db.execute(query)
    return result.all()

async def mark_item_as_deleted(db: AsyncSession, user: User, item_uuid: uuid.UUID) -> bool:
    """
    Помечает элемент как удаленный.
    """
    latest_event = await get_latest_event_for_item(db, item_uuid, user.tenant_id)

    if not latest_event or latest_event.operation == OperationType.DELETED:
        return False

    delete_event = KnowledgeEvent(
        item_uuid=item_uuid,
        tenant_id=user.tenant_id,
        user_id=user.id,
        operation=OperationType.DELETED,
        item_name=latest_event.item_name,
        item_type=latest_event.item_type,
        status=latest_event.status,
        content=latest_event.content,
        size=latest_event.size,
        s3_path=latest_event.s3_path
    )
    db.add(delete_event)
    await db.commit()
    return True