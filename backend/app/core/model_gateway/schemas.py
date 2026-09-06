from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

class MultimodalContent(BaseModel):
    attachment_id: str
    media_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None # For tool messages
    images: Optional[List[MultimodalContent]] = None

class GenerationRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: Dict[str, Any]  # Expected to contain "name" and "arguments"

class GenerationResponse(BaseModel):
    text: str
    model: str
    finish_reason: str = "stop"
    tool_calls: List[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class StreamingEvent(BaseModel):
    type: Literal["text_delta", "completed", "error"]
    text: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Usage] = None

class ModelCapabilities(BaseModel):
    text_generation: bool = False
    streaming: bool = False
    embeddings: bool = False
    vision: bool = False
    tool_calling: bool = False
    structured_output: bool = False

class ModelInfo(BaseModel):
    model_id: str
    provider: str
    capabilities: ModelCapabilities
    context_window: int = 8192
