from datetime import timedelta
from typing import Optional, List, Tuple
from app.db.uow import UnitOfWork
from app.db.models import User
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.core.errors import MRPLAPIException

VALID_ROLES = {"ADMIN", "USER"}

class AuthService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        user = await self.uow.users.get_by_username(username)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def create_user(self, user_in: dict) -> User:
        """Standard self-registration (default role USER)."""
        existing_user = await self.uow.users.get_by_username(user_in["username"])
        if existing_user:
            raise MRPLAPIException("USER_ALREADY_EXISTS", "Username is already taken.", 400)
            
        if user_in.get("email"):
            existing_email = await self.uow.users.get_by_email(user_in["email"])
            if existing_email:
                raise MRPLAPIException("EMAIL_ALREADY_EXISTS", "Email address is already in use.", 400)

        hashed_password = get_password_hash(user_in.pop("password"))
        user_in["password_hash"] = hashed_password
        user_in["role"] = "USER"
        user_in["is_active"] = True
        
        user = await self.uow.users.create(user_in)
        return user

    async def create_user_by_admin(self, user_in: dict) -> User:
        """Admin-controlled user creation with explicit role assignment."""
        username = user_in.get("username", "").strip()
        if not username:
            raise MRPLAPIException("INVALID_INPUT", "Username is required.", 400)

        existing_user = await self.uow.users.get_by_username(username)
        if existing_user:
            raise MRPLAPIException("USER_ALREADY_EXISTS", f"Username '{username}' is already taken.", 400)

        email = user_in.get("email")
        if email:
            existing_email = await self.uow.users.get_by_email(email)
            if existing_email:
                raise MRPLAPIException("EMAIL_ALREADY_EXISTS", f"Email '{email}' is already in use.", 400)

        role = str(user_in.get("role", "USER")).upper().strip()
        if role not in VALID_ROLES:
            raise MRPLAPIException("INVALID_ROLE", f"Invalid role '{role}'. Allowed roles: {', '.join(sorted(VALID_ROLES))}", 400)

        password = user_in.pop("password", None)
        if not password or len(password) < 8:
            raise MRPLAPIException("INVALID_PASSWORD", "Password must be at least 8 characters long.", 400)

        user_data = {
            "username": username,
            "email": email,
            "display_name": user_in.get("display_name"),
            "password_hash": get_password_hash(password),
            "role": role,
            "is_active": user_in.get("is_active", True)
        }

        user = await self.uow.users.create(user_data)
        return user

    async def update_user_by_admin(self, user_id: str, updates: dict, actor: User) -> User:
        """Admin-controlled user update with self-deactivation and superuser protections."""
        target_user = await self.uow.users.get_by_id(user_id)
        if not target_user:
            raise MRPLAPIException("USER_NOT_FOUND", "User not found.", 404)

        # Self-deactivation guard
        if updates.get("is_active") is False and target_user.id == actor.id:
            raise MRPLAPIException("CANNOT_DEACTIVATE_SELF", "Administrators cannot deactivate their own account.", 400)

        # Primary superuser deactivation guard
        if updates.get("is_active") is False and target_user.username == settings.FIRST_SUPERUSER:
            raise MRPLAPIException("CANNOT_DEACTIVATE_PRIMARY_ADMIN", "Primary administrator account cannot be deactivated.", 400)

        # Role demotion guard on self
        if "role" in updates and updates["role"]:
            norm_role = str(updates["role"]).upper().strip()
            if norm_role not in VALID_ROLES:
                raise MRPLAPIException("INVALID_ROLE", f"Invalid role '{norm_role}'. Allowed: {', '.join(sorted(VALID_ROLES))}", 400)
            if norm_role != "ADMIN" and target_user.id == actor.id:
                raise MRPLAPIException("CANNOT_DEMOTE_SELF", "Administrators cannot revoke their own administrative privileges.", 400)
            updates["role"] = norm_role

        # Email uniqueness check if modified
        if "email" in updates and updates["email"] and updates["email"] != target_user.email:
            existing_email = await self.uow.users.get_by_email(updates["email"])
            if existing_email and existing_email.id != target_user.id:
                raise MRPLAPIException("EMAIL_ALREADY_EXISTS", f"Email '{updates['email']}' is already in use.", 400)

        # Password reset
        if "password" in updates and updates["password"]:
            if len(updates["password"]) < 8:
                raise MRPLAPIException("INVALID_PASSWORD", "Password must be at least 8 characters long.", 400)
            updates["password_hash"] = get_password_hash(updates.pop("password"))
        elif "password" in updates:
            del updates["password"]

        # Prevent username change
        if "username" in updates:
            del updates["username"]

        updated_user = await self.uow.users.update(target_user, updates)
        return updated_user

    async def soft_deactivate_user(self, user_id: str, actor: User) -> User:
        """Soft deactivates a user (sets is_active=False). Never physically deletes user data."""
        return await self.update_user_by_admin(user_id, {"is_active": False}, actor)

    async def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None
    ) -> Tuple[List[User], int]:
        """Lists users with pagination, role/status filters, and keyword search."""
        return await self.uow.users.list_users(
            limit=limit,
            offset=offset,
            role=role,
            is_active=is_active,
            search=search
        )
