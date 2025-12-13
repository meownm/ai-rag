"""
Роутер для аутентификации и управления пользователями.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from core import (create_access_token, get_current_user, get_db,
                  verify_password)
from models import User, UserPublic

# Создаем экземпляр APIRouter. Все эндпоинты, определенные с помощью этого
# объекта, будут позже включены в основное приложение FastAPI.
router = APIRouter(
    # Группируем эндпоинты в документации Swagger UI под этим тегом.
    tags=["Auth & Users"],
)

@router.post("/token", summary="Получить JWT токен доступа")
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db=Depends(get_db)):
    """
    Аутентифицирует пользователя по логину и паролю и возвращает JWT токен.

    Принимает данные в формате `application/x-www-form-urlencoded`
    (стандарт для OAuth2).
    """
    # 1. Находим пользователя в БД по имени пользователя.
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()

    # 2. Проверяем, что пользователь существует, активен, и пароль совпадает.
    # Используется безопасная функция verify_password, которая сравнивает хеши.
    if not user or not user.is_active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Создаем JWT токен, в который зашиваем ID пользователя и его тенанта.
    # Это ключевой момент для реализации multi-tenancy.
    token_data = {
        "sub": user.username,       # 'subject' токена, стандартное поле
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id)
    }
    access_token = create_access_token(data=token_data)
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me", response_model=UserPublic, summary="Получить информацию о текущем пользователе")
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    """
    Возвращает публичную информацию о пользователе, чей токен был предоставлен.
    
    Зависимость `get_current_user` выполняет всю работу по валидации токена
    и извлечению пользователя из БД.
    """
    return current_user