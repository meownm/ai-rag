import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import create_access_token, create_refresh_token, get_current_user, get_db
from models import TelegramLinkStart, TelegramLinkStatus, TokenPair, User, UserTelegramLink

router = APIRouter(prefix="/telegram", tags=["Telegram Links"])


@router.post("/links/start", response_model=TelegramLinkStatus, status_code=status.HTTP_201_CREATED)
async def start_link(payload: TelegramLinkStart, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(UserTelegramLink).where(UserTelegramLink.telegram_id == payload.telegram_id))
    link = existing.scalars().first()
    state_token = str(uuid.uuid4())

    if link:
        link.state_token = state_token
        link.username = payload.username
        link.verified_at = None
        db.add(link)
    else:
        link = UserTelegramLink(
            telegram_id=payload.telegram_id,
            username=payload.username,
            state_token=state_token,
        )
        db.add(link)

    await db.commit()
    return TelegramLinkStatus(state_token=state_token, verified=bool(link.verified_at))


@router.get("/links/{state_token}", response_model=TelegramLinkStatus)
async def link_status(state_token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserTelegramLink).where(UserTelegramLink.state_token == state_token))
    link = result.scalars().first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link request not found")
    return TelegramLinkStatus(state_token=state_token, verified=bool(link.verified_at))


@router.post("/links/{state_token}/verify", response_model=TokenPair)
async def verify_link(
    state_token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(UserTelegramLink).where(UserTelegramLink.state_token == state_token))
    link = result.scalars().first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link request not found")

    link.user_id = current_user.id
    link.verified_at = datetime.datetime.utcnow()
    link.state_token = state_token
    db.add(link)
    await db.commit()

    token_data = {
        "sub": current_user.idp_subject or current_user.username,
        "user_id": str(current_user.id),
        "tenant_id": str(current_user.tenant_id),
    }
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(jwt_exp_delta(access_token)),
    )


def jwt_exp_delta(token: str) -> float:
    # FastAPI path operation dependency scopes make importing here safe.
    from jose import jwt

    payload = jwt.decode(token, "", options={"verify_signature": False, "verify_aud": False})
    exp = payload.get("exp")
    return float(exp - datetime.datetime.utcnow().timestamp())


@router.post("/links/{state_token}/exchange", response_model=TokenPair)
async def exchange_tokens(state_token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserTelegramLink).where(UserTelegramLink.state_token == state_token))
    link = result.scalars().first()
    if not link or not link.verified_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link request is not verified yet")

    user = await db.get(User, link.user_id) if link.user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Linked user is not active")

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
