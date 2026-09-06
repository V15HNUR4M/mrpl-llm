from datetime import timedelta
from typing import Optional
from app.db.uow import UnitOfWork
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.core.errors import MRPLAPIException

class AuthService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        user = await self.uow.users.get_by_username(username)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def create_user(self, user_in: dict) -> dict:
        existing_user = await self.uow.users.get_by_username(user_in["username"])
        if existing_user:
            raise MRPLAPIException("USER_ALREADY_EXISTS", "Username is already taken.", 400)
            
        hashed_password = get_password_hash(user_in.pop("password"))
        user_in["password_hash"] = hashed_password
        
        user = await self.uow.users.create(user_in)
        return user
