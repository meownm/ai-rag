import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from core import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_db,
    verify_password,
)
from models import TokenPair, User, UserPublic

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
    refresh_token = create_refresh_token(data=token_data)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(jwt_exp_delta(access_token)),
    )


@router.get("/users/me", response_model=UserPublic, summary="Получить информацию о текущем пользователе")
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.post("/token/refresh", response_model=TokenPair)
async def refresh_access_token(payload: dict, db=Depends(get_db)):
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token is required")

    claims = decode_token(refresh_token, expected_type="refresh")
    user_id = claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await db.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    token_data = {
        "sub": user.idp_subject or user.username,
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
    }
    new_access = create_access_token(data=token_data)
    new_refresh = create_refresh_token(data=token_data)
    return TokenPair(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=int(jwt_exp_delta(new_access)),
    )


def jwt_exp_delta(token: str) -> float:
    from jose import jwt

    payload = jwt.decode(token, "", options={"verify_signature": False, "verify_aud": False})
    exp = payload.get("exp")
    return float(exp - datetime.datetime.utcnow().timestamp())
