from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class ConversationBase(BaseModel):
    title: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None

class ConversationCreate(ConversationBase):
    pass

class ConversationUpdate(ConversationBase):
    status: Optional[str] = None

class ConversationResponse(ConversationBase):
    id: str
    user_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime]

    class Config:
        from_attributes = True

class PaginatedConversationResponse(BaseModel):
    items: List[ConversationResponse]
    pagination: Dict[str, int]
