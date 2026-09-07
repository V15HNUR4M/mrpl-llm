from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field

# Standard Event Type Constants
EVENT_CHAT_REQUEST = "chat.request"
EVENT_ROUTER_TASK_ROUTED = "router.task_routed"

EVENT_AGENT_RUN_STARTED = "agent.run.started"
EVENT_AGENT_RUN_COMPLETED = "agent.run.completed"
EVENT_AGENT_RUN_FAILED = "agent.run.failed"
EVENT_AGENT_STEP_STARTED = "agent.step.started"
EVENT_AGENT_STEP_COMPLETED = "agent.step.completed"
EVENT_AGENT_STEP_FAILED = "agent.step.failed"
EVENT_AGENT_RUN_TIMEOUT = "agent.run.timeout"

EVENT_MODEL_REQUEST = "model.request"
EVENT_MODEL_RESPONSE = "model.response"
EVENT_MODEL_ERROR = "model.error"
EVENT_MODEL_GEN_STARTED = "model.generation.started"
EVENT_MODEL_GEN_COMPLETED = "model.generation.completed"
EVENT_MODEL_GEN_FAILED = "model.generation.failed"
EVENT_MODEL_GEN_TIMEOUT = "model.generation.timeout"

EVENT_MODEL_STREAM_STARTED = "model.stream.started"
EVENT_MODEL_STREAM_COMPLETED = "model.stream.completed"
EVENT_MODEL_STREAM_FAILED = "model.stream.failed"

EVENT_RAG_QUERY = "rag.query"
EVENT_RAG_COMPLETED = "rag.completed"
EVENT_RAG_FAILED = "rag.failed"

EVENT_TOOL_STARTED = "tool.started"
EVENT_TOOL_COMPLETED = "tool.completed"
EVENT_TOOL_FAILED = "tool.failed"
EVENT_TOOL_EXEC_STARTED = "tool.execution.started"
EVENT_TOOL_EXEC_COMPLETED = "tool.execution.completed"
EVENT_TOOL_EXEC_DENIED = "tool.execution.denied"
EVENT_TOOL_EXEC_FAILED = "tool.execution.failed"
EVENT_TOOL_EXEC_TIMEOUT = "tool.execution.timeout"

EVENT_FILE_GENERATED = "file.generated"

EVENT_WORKFLOW_RUN_STARTED = "workflow.run.started"
EVENT_WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
EVENT_WORKFLOW_RUN_COMPLETED = "workflow.run.completed"
EVENT_WORKFLOW_RUN_FAILED = "workflow.run.failed"
EVENT_WORKFLOW_RUN_TIMEOUT = "workflow.run.timeout"
EVENT_WORKFLOW_RUN_CANCELLED = "workflow.run.cancelled"

EVENT_MULTIMODAL_ATTACHMENT = "multimodal.attachment"
EVENT_MULTIMODAL_OCR = "multimodal.ocr"


class TelemetryEventCreate(BaseModel):
    event_type: str
    component: str
    severity: Literal["DEBUG", "INFO", "WARN", "ERROR"] = "INFO"
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_id: Optional[str] = None
    agent_id: Optional[str] = None
    operation: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TelemetryEventResponse(BaseModel):
    id: str
    timestamp: datetime
    event_type: str
    component: str
    severity: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_id: Optional[str] = None
    agent_id: Optional[str] = None
    operation: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_")

    class Config:
        from_attributes = True
        populate_by_name = True


class MetricsSummary(BaseModel):
    counters: Dict[str, int] = Field(default_factory=dict)
    gauges: Dict[str, float] = Field(default_factory=dict)
    average_latencies_ms: Dict[str, float] = Field(default_factory=dict)


class DependencyHealth(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


class HealthStatus(BaseModel):
    status: str
    liveness: bool
    readiness: bool
    timestamp: datetime
    dependencies: Dict[str, DependencyHealth] = Field(default_factory=dict)
