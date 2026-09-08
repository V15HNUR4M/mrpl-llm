from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from app.core.config import settings
from app.core.security import create_access_token
from app.core.errors import MRPLAPIException
from app.db.uow import UnitOfWork, get_uow
from app.services.auth import AuthService
from app.schemas.user import UserCreate, UserResponse, Token
from app.dependencies import get_current_user
from app.db.models import User

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        auth_service = AuthService(uow)
        user = await auth_service.authenticate_user(form_data.username, form_data.password)
        if not user:
            raise MRPLAPIException("AUTH_INVALID_CREDENTIALS", "Incorrect username or password", 401)
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", response_model=UserResponse)
async def register(
    user_in: UserCreate,
    uow: UnitOfWork = Depends(get_uow)
):
    if not settings.ENABLE_PUBLIC_REGISTRATION:
        raise MRPLAPIException(
            code="REGISTRATION_DISABLED",
            message="Public self-registration is disabled. Please contact your system administrator to obtain an account.",
            status_code=403
        )
    async with uow:
        auth_service = AuthService(uow)
        user = await auth_service.create_user(user_in.model_dump())
        return user

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
