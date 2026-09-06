from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class StepType(str, Enum):
    AGENT = "AGENT"
    TOOL = "TOOL"
    CONDITION = "CONDITION"

class WorkflowStep(BaseModel):
    id: str
    type: StepType
    configuration: Dict[str, Any] = Field(default_factory=dict)
    next_step: Optional[str] = None
    fallback_step: Optional[str] = None

class WorkflowSpec(BaseModel):
    start_step: str
    steps: Dict[str, WorkflowStep]
    input_schema: Dict[str, Any] = Field(default_factory=dict)

class WorkflowRunState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"

class WorkflowContext(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    step_results: Dict[str, Any] = Field(default_factory=dict)
