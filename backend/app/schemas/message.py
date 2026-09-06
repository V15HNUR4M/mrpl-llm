from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class MessageBase(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system|tool)$")
    content: str
    model_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: str
    conversation_id: str
    sequence_number: int
    created_at: datetime

    class Config:
        from_attributes = True

class PaginatedMessageResponse(BaseModel):
    items: List[MessageResponse]
    pagination: Dict[str, int]
