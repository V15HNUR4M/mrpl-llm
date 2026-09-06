from fastapi import APIRouter, Depends
from typing import List

from app.db.uow import UnitOfWork, get_uow
from app.services.conversation import ConversationService
from app.schemas.message import MessageCreate, MessageResponse, PaginatedMessageResponse
from app.dependencies import get_current_user
from app.db.models import User

router = APIRouter()

@router.post("", response_model=MessageResponse, status_code=201)
async def create_message(
    conversation_id: str,
    msg_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        service = ConversationService(uow)
        return await service.add_message(conversation_id, current_user.id, msg_in.model_dump())

@router.get("", response_model=PaginatedMessageResponse)
async def list_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        service = ConversationService(uow)
        messages = await service.list_messages(conversation_id, current_user.id, limit, offset)
        return {
            "items": messages,
            "pagination": {"limit": limit, "offset": offset, "total": 0}
        }
