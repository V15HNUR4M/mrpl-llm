from fastapi import APIRouter, Depends, Query, status
from typing import Optional

from app.db.uow import UnitOfWork, get_uow
from app.db.models import User
from app.dependencies import require_admin
from app.services.auth import AuthService
from app.schemas.user import (
    AdminUserCreate,
    AdminUserUpdate,
    UserResponse,
    PaginatedUserResponse
)
from app.core.errors import MRPLAPIException

router = APIRouter()

@router.get("", response_model=PaginatedUserResponse)
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    role: Optional[str] = Query(None, description="Filter by role (ADMIN, USER)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by username, email, or display name"),
    current_admin: User = Depends(require_admin),
    uow: UnitOfWork = Depends(get_uow)
):
    """
    List registered users with pagination, role/status filtering, and search.
    Requires ADMIN privileges.
    """
    async with uow:
        auth_service = AuthService(uow)
        users, total = await auth_service.list_users(
            limit=limit,
            offset=offset,
            role=role,
            is_active=is_active,
            search=search
        )
        return {
            "items": users,
            "total": total,
            "limit": limit,
            "offset": offset
        }

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: AdminUserCreate,
    current_admin: User = Depends(require_admin),
    uow: UnitOfWork = Depends(get_uow)
):
    """
    Create a new user with an assigned role (ADMIN or USER) and initial credentials.
    Requires ADMIN privileges.
    """
    async with uow:
        auth_service = AuthService(uow)
        user = await auth_service.create_user_by_admin(user_in.model_dump())
        await uow.commit()
        return user

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    uow: UnitOfWork = Depends(get_uow)
):
    """
    Retrieve user details by user ID.
    Requires ADMIN privileges.
    """
    async with uow:
        user = await uow.users.get_by_id(user_id)
        if not user:
            raise MRPLAPIException("USER_NOT_FOUND", "User not found.", 404)
        return user

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_in: AdminUserUpdate,
    current_admin: User = Depends(require_admin),
    uow: UnitOfWork = Depends(get_uow)
):
    """
    Update a user's role, active status, display name, or reset password.
    Guards prevent an admin from deactivating or demoting themselves.
    Requires ADMIN privileges.
    """
    async with uow:
        auth_service = AuthService(uow)
        update_data = user_in.model_dump(exclude_unset=True)
        updated = await auth_service.update_user_by_admin(user_id, update_data, current_admin)
        await uow.commit()
        return updated

@router.delete("/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    uow: UnitOfWork = Depends(get_uow)
):
    """
    Soft-deactivate a user account (sets is_active=False).
    Does NOT delete existing user data (conversations, messages, files, memories are preserved).
    Guards prevent deactivating self or the primary system administrator.
    Requires ADMIN privileges.
    """
    async with uow:
        auth_service = AuthService(uow)
        deactivated = await auth_service.soft_deactivate_user(user_id, current_admin)
        await uow.commit()
        return deactivated
