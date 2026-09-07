from typing import List, Dict, Any, Optional
from app.db.uow import UnitOfWork
from app.core.errors import MRPLAPIException

class ConversationService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def create_conversation(self, user_id: str, title: Optional[str] = None, metadata_: Optional[Dict[str, Any]] = None) -> dict:
        conv_data = {
            "user_id": user_id,
            "title": title or "New Conversation",
            "metadata_": metadata_
        }
        return await self.uow.conversations.create(conv_data)

    async def get_conversation(self, conversation_id: str, user_id: str) -> dict:
        conversation = await self.uow.conversations.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise MRPLAPIException("CONVERSATION_NOT_FOUND", "Conversation not found", 404)
        return conversation

    async def list_conversations(self, user_id: str, limit: int = 20, offset: int = 0) -> List[dict]:
        return await self.uow.conversations.list_for_user(user_id, limit, offset)

    async def update_conversation_title(self, conversation_id: str, user_id: str, title: str) -> dict:
        conversation = await self.get_conversation(conversation_id, user_id)
        return await self.uow.conversations.update(conversation, {"title": title})

    async def add_message(self, conversation_id: str, user_id: str, message_data: dict) -> dict:
        # Verify ownership
        await self.get_conversation(conversation_id, user_id)
        
        # Get sequence number
        messages = await self.uow.messages.list_by_conversation(conversation_id, limit=1000)
        sequence_number = len(messages) + 1
        
        msg_in = {
            "conversation_id": conversation_id,
            "role": message_data["role"],
            "content": message_data["content"],
            "sequence_number": sequence_number,
            "model_id": message_data.get("model_id"),
            "agent_id": message_data.get("agent_id"),
            "metadata_": message_data.get("metadata_")
        }
        
        message = await self.uow.messages.create(msg_in)
        
        # Update conversation updated_at
        conversation = await self.uow.conversations.get_by_id(conversation_id)
        await self.uow.conversations.update(conversation, {}) # Triggers onupdate
        
        return message

    async def list_messages(self, conversation_id: str, user_id: str, limit: int = 50, offset: int = 0) -> List[dict]:
        # Verify ownership
        await self.get_conversation(conversation_id, user_id)
        return await self.uow.messages.list_by_conversation(conversation_id, limit, offset)

    async def get_recent_messages(self, conversation_id: str, user_id: str, limit: int = 10) -> List[dict]:
        # Verify ownership
        await self.get_conversation(conversation_id, user_id)
        return await self.uow.messages.list_recent_by_conversation(conversation_id, limit)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        # Verify ownership (raises 404 if nonexistent or belongs to another user)
        conversation = await self.get_conversation(conversation_id, user_id)
        # Deleting the loaded ORM instance triggers cascading deletion of related messages and summaries
        await self.uow.session.delete(conversation)
        await self.uow.session.flush()
        return True
