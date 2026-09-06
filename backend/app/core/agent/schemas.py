from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class AgentCapabilities(BaseModel):
    text_generation: bool = True
    structured_output: bool = False
    vision: bool = False
    tool_calling: bool = False

class AgentContextPolicy(BaseModel):
    rag: bool = False
    conversation_memory: bool = False
    semantic_memory: bool = False
    recent_messages_count: int = 10

class AgentMemoryPolicy(BaseModel):
    read: bool = False
    write: bool = False

class AgentToolsPolicy(BaseModel):
    allowed: List[str] = Field(default_factory=list)

class AgentWorkflowsPolicy(BaseModel):
    allowed: List[str] = Field(default_factory=list)

class AgentExecutionLimits(BaseModel):
    max_steps: int = 10
    timeout_seconds: int = 120
    max_tool_calls: int = 20

class AgentDefinition(BaseModel):
    agent_id: str
    name: str
    description: str
    version: str
    status: str = "enabled"
    instructions: str
    
    model_requirements: AgentCapabilities = Field(default_factory=AgentCapabilities)
    context_policy: AgentContextPolicy = Field(default_factory=AgentContextPolicy)
    memory_policy: AgentMemoryPolicy = Field(default_factory=AgentMemoryPolicy)
    tool_permissions: AgentToolsPolicy = Field(default_factory=AgentToolsPolicy)
    workflow_permissions: AgentWorkflowsPolicy = Field(default_factory=AgentWorkflowsPolicy)
    execution_limits: AgentExecutionLimits = Field(default_factory=AgentExecutionLimits)
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
