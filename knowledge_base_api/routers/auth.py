from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from core import create_access_token, get_current_user, get_db, verify_password
from models import User, UserPublic

router = APIRouter(tags=["Auth & Users"])


@router.post("/token", summary="Получить JWT токен доступа")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db=Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()

    if not user or not user.is_active or not verify_password(form_data.password, user.hashed_password or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "sub": user.idp_subject or user.username,
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
    }
    access_token = create_access_token(data=token_data)

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserPublic, summary="Получить информацию о текущем пользователе")
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
