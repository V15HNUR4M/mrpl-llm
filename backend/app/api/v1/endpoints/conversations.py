from fastapi import APIRouter, Depends
from typing import List

from app.db.uow import UnitOfWork, get_uow
from app.services.conversation import ConversationService
from app.schemas.conversation import ConversationCreate, ConversationResponse, PaginatedConversationResponse
from app.dependencies import get_current_user
from app.db.models import User

router = APIRouter()

@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    conv_in: ConversationCreate,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        service = ConversationService(uow)
        return await service.create_conversation(current_user.id, conv_in.title, conv_in.metadata_)

@router.get("", response_model=PaginatedConversationResponse)
async def list_conversations(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        service = ConversationService(uow)
        conversations = await service.list_conversations(current_user.id, limit, offset)
        return {
            "items": conversations,
            "pagination": {"limit": limit, "offset": offset, "total": 0} # Total is omitted for simplicity in this implementation
        }

@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        service = ConversationService(uow)
        return await service.get_conversation(conversation_id, current_user.id)
