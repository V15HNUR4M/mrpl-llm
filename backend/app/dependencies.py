from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.core.config import settings
from app.db.uow import UnitOfWork, get_uow
from app.db.models import User
from app.core.errors import MRPLAPIException
import logging

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")
logger = logging.getLogger("mrpl.dependencies")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    uow: UnitOfWork = Depends(get_uow, use_cache=False)
) -> User:
    credentials_exception = MRPLAPIException(
        code="AUTH_INVALID_CREDENTIALS",
        message="Could not validate credentials",
        status_code=status.HTTP_401_UNAUTHORIZED,
        details={"headers": {"WWW-Authenticate": "Bearer"}},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise credentials_exception

    async with uow:
        user = await uow.users.get_by_username(username=username)
        if user is None:
            raise credentials_exception
        if not user.is_active:
            raise MRPLAPIException("AUTH_FORBIDDEN", "Inactive user", 403)
        return user
