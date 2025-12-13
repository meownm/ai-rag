"""
Роутеры для управления элементами базы знаний (файлами, ссылками).
"""
import logging
import uuid
from typing import List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Response,
                     UploadFile, status)
from sqlalchemy import func, select

import services
from core import get_current_user, get_db, get_s3_client
from models import (FileDownloadResponse, ItemResponse, LinkCreate,
                    OperationType, StatusUpdate, User)

logger = logging.getLogger(__name__)

# --- ЕДИНЫЙ РОУТЕР ДЛЯ ВСЕХ ОПЕРАЦИЙ С ЭЛЕМЕНТАМИ ---
# Мы используем один роутер без префикса, чтобы иметь полный контроль
# над путями (/files, /links, /items, и т.д.).
router = APIRouter(
    tags=["Items"],
    dependencies=[Depends(get_current_user)]
)


@router.post(
    "/files",
    response_model=ItemResponse,
    summary="Загрузить или обновить файл",
    description="Принимает файл через multipart/form-data. Поле формы — `file`."
)
async def add_file(
    file: UploadFile = File(..., description="Бинарное содержимое файла (multipart/form-data)"),
    name: Optional[str] = Form(None),
    db=Depends(get_db),
    s3_client=Depends(get_s3_client),
    current_user: User = Depends(get_current_user)
):
    """
    Загружает новый файл или обновляет существующий с тем же именем.

    - **Если файл новый**: возвращает статус `201 Created` и `action: "created"`.
    - **Если файл с таким именем уже существует**: перезаписывает его в S3,
      архивирует старую запись в БД и создает новую. Возвращает статус
      `200 OK` и `action: "updated"`.

    :param file: Загружаемый файл (`UploadFile`).
    :param name: Необязательное имя файла. Если не указано, используется имя из `file.filename`.
    :return: Объект `ItemResponse` с информацией о созданном/обновленном файле.
    """
    file_name = name or file.filename
    
    # 1. Вызываем сервисный слой, который содержит всю сложную логику
    new_event, action = await services.create_file_event(
        db=db, s3_client=s3_client, user=current_user,
        file_stream=file.file, filename=file_name, file_size=file.size
    )

    # 2. Формируем тело ответа, добавляя кастомное поле 'action'
    response_data = ItemResponse.from_orm(new_event).dict()
    response_data["action"] = action
    
    # 3. Устанавливаем корректный HTTP статус в зависимости от выполненного действия
    http_status = status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK

    return Response(
        content=ItemResponse(**response_data).model_dump_json(),
        status_code=http_status,
        media_type="application/json"
    )

@router.post("/links", response_model=ItemResponse, status_code=201, summary="Добавить новую ссылку")
async def add_link(link: LinkCreate, db=Depends(get_db), current_user: User = Depends(get_current_user)):
    """Создает новый элемент типа 'ссылка' в базе знаний."""
    return await services.create_link_event(db=db, user=current_user, link_data=link)

@router.get("/items", response_model=List[ItemResponse], summary="Получить список всех активных элементов")
async def get_current_state_of_all_items(db=Depends(get_db), current_user: User = Depends(get_current_user)):
    """Возвращает текущее состояние всех активных (не удаленных) элементов для тенанта пользователя."""
    return await services.get_all_active_items(db, current_user)

@router.get("/items/search", response_model=List[ItemResponse], summary="Поиск элементов по имени")
async def search_items(q: str, db=Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Выполняет поиск активных элементов по частичному совпадению имени (без учета регистра).
    """
    subquery = select(services.KnowledgeEvent, func.row_number().over(partition_by=services.KnowledgeEvent.item_uuid, order_by=services.KnowledgeEvent.operation_time.desc()).label("rn")).where(services.KnowledgeEvent.tenant_id == current_user.tenant_id).subquery()
    query = select(subquery).where(subquery.c.rn == 1, subquery.c.operation != OperationType.DELETED, subquery.c.item_name.ilike(f"%{q}%"))
    result = await db.execute(query)
    return result.all()

@router.get("/items/{item_uuid}/download", response_model=FileDownloadResponse, summary="Получить ссылку для скачивания файла")
async def get_file_download_url(item_uuid: uuid.UUID, db=Depends(get_db), s3_client=Depends(get_s3_client), current_user: User = Depends(get_current_user)):
    """
    Генерирует временную (presigned) ссылку для скачивания файла из S3.
    Это безопасный способ предоставления доступа к приватным файлам.
    """
    latest_event = await services.get_latest_event_for_item(db, item_uuid, current_user.tenant_id)
    if not latest_event or latest_event.operation == "deleted" or latest_event.item_type != "file":
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        url = await s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': services.settings.s3_bucket_name, 'Key': latest_event.s3_path},
            ExpiresIn=3600  # Ссылка действительна 1 час
        )
        return {"download_url": url}
    except Exception:
        logger.error("Failed to generate presigned S3 URL", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not generate download link.")

@router.delete("/items/{item_uuid}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить элемент")
async def delete_item(item_uuid: uuid.UUID, db=Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Помечает элемент как удаленный.
    Это "мягкое" удаление: создается событие DELETED, но сам файл в S3 и
    история в БД остаются для возможности восстановления и аудита.
    """
    await services.mark_item_as_deleted(db=db, user=current_user, item_uuid=item_uuid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/items/{item_uuid}/status", response_model=ItemResponse, summary="Обновить статус элемента")
async def update_item_status(item_uuid: uuid.UUID, status_update: StatusUpdate, db=Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Обновляет статус элемента, создавая новое событие STATUS_CHANGED в истории.
    """
    latest_event = await services.get_latest_event_for_item(db, item_uuid, current_user.tenant_id)
    if not latest_event or latest_event.operation == "deleted":
        raise HTTPException(status_code=404, detail="Item not found")
    
    if latest_event.status == status_update.status:
        return latest_event
    
    status_change_event = services.KnowledgeEvent(
        item_uuid=item_uuid,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        operation=services.OperationType.STATUS_CHANGED,
        item_name=latest_event.item_name,
        item_type=latest_event.item_type,
        content=latest_event.content,
        size=latest_event.size,
        status=status_update.status,
        s3_path=latest_event.s3_path
    )
    db.add(status_change_event)
    await db.commit()
    await db.refresh(status_change_event)
    return status_change_event