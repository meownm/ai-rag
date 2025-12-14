from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import get_current_user, get_db, get_or_create_tenant
from models import (
    Organization,
    OrganizationCreate,
    OrganizationResponse,
    User,
    UserInviteRequest,
    UserOrganizationLink,
    UserOrganizationRole,
    UserRole,
)

router = APIRouter(prefix="/admin", tags=["Administration"])


def _ensure_admin(user: User):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(payload: OrganizationCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ensure_admin(current_user)
    tenant = await get_or_create_tenant(db, payload.tenant_name or payload.name)

    existing = await db.execute(select(Organization).where(Organization.name == payload.name))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization already exists")

    organization = Organization(name=payload.name, tenant_id=tenant.id)
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return organization


@router.post(
    "/organizations/{organization_id}/invite",
    response_model=UserOrganizationLink,
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    organization_id: str,
    payload: UserInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    organization = await db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    existing_user = await db.execute(select(User).where(User.idp_subject == payload.idp_subject))
    user = existing_user.scalars().first()
    if not user:
        user = User(
            username=payload.username,
            hashed_password=None,
            is_active=True,
            role=payload.role,
            tenant_id=organization.tenant_id,
            idp_subject=payload.idp_subject,
        )
        db.add(user)
        await db.flush()
    else:
        user.role = payload.role
        user.tenant_id = organization.tenant_id
        db.add(user)

    link = await db.execute(
        select(UserOrganizationRole).where(
            UserOrganizationRole.user_id == user.id,
            UserOrganizationRole.organization_id == organization.id,
        )
    )
    link_instance = link.scalars().first()
    if not link_instance:
        link_instance = UserOrganizationRole(user_id=user.id, organization_id=organization.id, role=payload.role)
        db.add(link_instance)
    else:
        link_instance.role = payload.role
        db.add(link_instance)

    await db.commit()
    await db.refresh(link_instance)

    return UserOrganizationLink(
        user_id=user.id,
        username=user.username,
        organization_id=organization.id,
        role=payload.role,
    )


@router.get("/organizations/{organization_id}/users", response_model=List[UserOrganizationLink])
async def list_organization_users(
    organization_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    organization = await db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    result = await db.execute(
        select(UserOrganizationRole, User)
        .join(User, UserOrganizationRole.user_id == User.id)
        .where(UserOrganizationRole.organization_id == organization.id)
    )

    links: List[UserOrganizationLink] = []
    for role_link, user in result.all():
        links.append(
            UserOrganizationLink(
                user_id=user.id,
                username=user.username,
                organization_id=organization.id,
                role=UserRole(role_link.role),
            )
        )
    return links
