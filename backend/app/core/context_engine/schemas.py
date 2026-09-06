from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ContextCandidate(BaseModel):
    id: str
    type: str  # e.g., "system", "request", "message", "summary", "rag", "tool", "memory"
    content: str
    source: Optional[str] = None
    priority: int = 10  # Lower is higher priority (1 is top priority)
    relevance_score: float = 0.0
    token_count: int = 0
    attachments: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ContextPackage(BaseModel):
    system_instructions: List[ContextCandidate] = Field(default_factory=list)
    current_request: Optional[ContextCandidate] = None
    recent_messages: List[ContextCandidate] = Field(default_factory=list)
    conversation_summary: Optional[ContextCandidate] = None
    semantic_memories: List[ContextCandidate] = Field(default_factory=list)
    rag_context: List[ContextCandidate] = Field(default_factory=list)
    tool_context: List[ContextCandidate] = Field(default_factory=list)
    agent_state: Optional[ContextCandidate] = None
    
    token_usage: Dict[str, int] = Field(default_factory=dict)
    token_budget: Dict[str, int] = Field(default_factory=dict)
    truncation_events: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
