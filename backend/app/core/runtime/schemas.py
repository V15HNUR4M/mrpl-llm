from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.core.context_engine.schemas import ContextCandidate

class ExecutionState(str, Enum):
    REQUESTED = "REQUESTED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    CONTEXT_BUILDING = "CONTEXT_BUILDING"
    GENERATING = "GENERATING"
    PROCESSING_RESULT = "PROCESSING_RESULT"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    LIMIT_REACHED = "LIMIT_REACHED"

class ExecutionEvent(BaseModel):
    id: str
    type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default_factory=dict)
    
class ToolRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any]
    call_id: str

class ToolResult(BaseModel):
    output: Any
    context_candidates: List[ContextCandidate] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str = "success"

class AgentDecision(BaseModel):
    final_answer: Optional[str] = None
    tool_requests: List[ToolRequest] = Field(default_factory=list)

class RuntimeSession(BaseModel):
    session_id: str
    conversation_id: str
    agent_id: str
    agent_version: str
    user_id: str
    
    state: ExecutionState = ExecutionState.REQUESTED
    iteration_count: int = 0
    tool_call_count: int = 0
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    events: List[ExecutionEvent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_event(self, event_type: str, data: Dict[str, Any] = None):
        import uuid
        self.events.append(ExecutionEvent(id=str(uuid.uuid4()), type=event_type, data=data or {}))

    def transition_to(self, new_state: ExecutionState):
        valid_transitions = {
            ExecutionState.REQUESTED: [ExecutionState.INITIALIZING],
            ExecutionState.INITIALIZING: [ExecutionState.RUNNING, ExecutionState.FAILED, ExecutionState.CANCELLED],
            ExecutionState.RUNNING: [
                ExecutionState.CONTEXT_BUILDING, ExecutionState.COMPLETED, 
                ExecutionState.FAILED, ExecutionState.CANCELLING, ExecutionState.TIMED_OUT,
                ExecutionState.LIMIT_REACHED
            ],
            ExecutionState.CONTEXT_BUILDING: [
                ExecutionState.GENERATING, ExecutionState.FAILED, ExecutionState.CANCELLING,
                ExecutionState.TIMED_OUT, ExecutionState.LIMIT_REACHED
            ],
            ExecutionState.GENERATING: [
                ExecutionState.PROCESSING_RESULT, ExecutionState.FAILED, ExecutionState.CANCELLING,
                ExecutionState.TIMED_OUT, ExecutionState.LIMIT_REACHED
            ],
            ExecutionState.PROCESSING_RESULT: [
                ExecutionState.COMPLETED, ExecutionState.WAITING_FOR_TOOL, ExecutionState.FAILED,
                ExecutionState.CANCELLING, ExecutionState.TIMED_OUT
            ],
            ExecutionState.WAITING_FOR_TOOL: [
                ExecutionState.TOOL_EXECUTION, ExecutionState.CANCELLING, ExecutionState.TIMED_OUT,
                ExecutionState.FAILED
            ],
            ExecutionState.TOOL_EXECUTION: [
                ExecutionState.RUNNING, ExecutionState.FAILED, ExecutionState.CANCELLING,
                ExecutionState.TIMED_OUT, ExecutionState.LIMIT_REACHED
            ],
            ExecutionState.CANCELLING: [ExecutionState.CANCELLED, ExecutionState.FAILED],
            # Terminal states
            ExecutionState.COMPLETED: [],
            ExecutionState.FAILED: [],
            ExecutionState.CANCELLED: [],
            ExecutionState.TIMED_OUT: [],
            ExecutionState.LIMIT_REACHED: []
        }
        
        if new_state not in valid_transitions.get(self.state, []):
            raise ValueError(f"Invalid state transition from {self.state} to {new_state}")
            
        self.state = new_state
        self.add_event("state_changed", {"new_state": new_state.value})
        
        if new_state in (ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED, ExecutionState.TIMED_OUT, ExecutionState.LIMIT_REACHED):
            self.completed_at = datetime.utcnow()
