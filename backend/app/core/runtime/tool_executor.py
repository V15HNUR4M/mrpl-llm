"""
Track 7 — Extended Tool Executor with:
  - ToolDefinition: structured metadata (enabled, input_schema, authorization_policy)
  - ToolRegistry: authoritative, enable/disable, list
  - InputValidator: jsonschema-based validation
  - AuthorizedToolExecutor: auth pre-check + audit before execution
  - LocalToolExecutor: actual dispatch to Tool.execute()
  - FakeToolExecutor: kept for tests
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

import jsonschema

from app.core.runtime.schemas import ToolRequest, ToolResult

# ---------------------------------------------------------------------------
# Authorization Policy
# ---------------------------------------------------------------------------

class AuthorizationPolicy(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"

# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """
    Structured metadata for a registered tool.
    The LLM sees only name, description, and input_schema — never internal logic.
    """
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema for arguments
    authorization_policy: AuthorizationPolicy = AuthorizationPolicy.PUBLIC
    enabled: bool = True


# ---------------------------------------------------------------------------
# Tool abstract base
# ---------------------------------------------------------------------------

class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON Schema for arguments."""

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.PUBLIC

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult: ...

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            authorization_policy=self.authorization_policy,
            enabled=self.enabled,
        )


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

class InputValidator:
    """Validates tool arguments against JSON Schema."""

    @staticmethod
    def validate(arguments: Dict[str, Any], schema: Dict[str, Any]) -> Optional[str]:
        """Returns an error message string if invalid, None if valid."""
        try:
            jsonschema.validate(instance=arguments, schema=schema)
            return None
        except jsonschema.ValidationError as e:
            return e.message
        except jsonschema.SchemaError as e:
            return f"Invalid tool schema: {e.message}"


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Authoritative catalogue of registered tools.
    No reflection, no arbitrary lookup by dynamic names.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._disabled: set = set()

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def disable(self, name: str) -> None:
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        self._disabled.discard(name)

    def get(self, name: str) -> Optional[Tool]:
        """Returns the tool if it exists (does NOT check enabled state here)."""
        return self._tools.get(name)

    def is_enabled(self, name: str) -> bool:
        if name in self._disabled:
            return False
        tool = self._tools.get(name)
        return tool is not None and tool.enabled

    def list_tools(self, include_disabled: bool = False) -> List[ToolDefinition]:
        result = []
        for tool in self._tools.values():
            if include_disabled or self.is_enabled(tool.name):
                result.append(tool.definition())
        return result

    def list_enabled_names(self) -> List[str]:
        return [t.name for t in self._tools.values() if self.is_enabled(t.name)]


# ---------------------------------------------------------------------------
# ToolExecutor base
# ---------------------------------------------------------------------------

class ToolExecutor(ABC):
    @abstractmethod
    async def execute(self, tool_call: ToolRequest, context: Dict[str, Any], allowed_tools: List[str] = None) -> ToolResult:
        """Execute a tool call. Returns a ToolResult; never raises."""


# ---------------------------------------------------------------------------
# LocalToolExecutor (pure dispatch — no auth, no audit)
# ---------------------------------------------------------------------------

class LocalToolExecutor(ToolExecutor):
    """
    Dispatches to concrete Tool implementations.
    Performs schema validation. No authorization logic here.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, tool_call: ToolRequest, context: Dict[str, Any], allowed_tools: List[str] = None) -> ToolResult:
        # Check agent-level allow-list
        if allowed_tools is not None and tool_call.tool not in allowed_tools:
            return ToolResult(
                output=f"Tool '{tool_call.tool}' is not allowed for this agent.",
                status="error",
                metadata={"error_type": "not_allowed"}
            )

        # Registry lookup (unknown tool)
        tool = self.registry.get(tool_call.tool)
        if not tool:
            return ToolResult(
                output=f"Unknown tool '{tool_call.tool}'",
                status="error",
                metadata={"error_type": "unknown_tool"}
            )

        # Enabled check
        if not self.registry.is_enabled(tool_call.tool):
            return ToolResult(
                output=f"Tool '{tool_call.tool}' is disabled.",
                status="error",
                metadata={"error_type": "disabled"}
            )

        # Input schema validation
        validation_error = InputValidator.validate(tool_call.arguments, tool.input_schema)
        if validation_error:
            return ToolResult(
                output=f"Invalid arguments: {validation_error}",
                status="error",
                metadata={"error_type": "validation_error"}
            )

        # Execute with isolation — a crash in the tool does not propagate
        try:
            return await tool.execute(tool_call.arguments, context)
        except Exception as e:
            return ToolResult(
                output=f"Tool execution failed: {str(e)}",
                status="error",
                metadata={"error_type": "execution_error"}
            )


# ---------------------------------------------------------------------------
# AuthorizedToolExecutor (wraps LocalToolExecutor; owns auth + audit)
# ---------------------------------------------------------------------------

class AuthorizedToolExecutor(ToolExecutor):
    """
    Security wrapper around LocalToolExecutor.

    Responsibilities:
    - Enforce tool authorization against authenticated user identity BEFORE execution
    - Emit AuditEvents for security-relevant operations
    - Timeout individual tool calls
    - Never bypass the Registry
    """

    def __init__(self, inner: LocalToolExecutor, tool_timeout: float = 30.0, uow=None, observability_service=None):
        self.inner = inner
        self.tool_timeout = tool_timeout
        self.uow = uow  # Optional UnitOfWork for audit emission
        self.observability_service = observability_service

    async def execute(self, tool_call: ToolRequest, context: Dict[str, Any], allowed_tools: List[str] = None) -> ToolResult:
        import time
        t0 = time.time()
        user_id: str = context.get("user_id", "")
        tool_name: str = tool_call.tool

        # Fetch tool definition for auth check
        tool = self.inner.registry.get(tool_name)

        # Authorization: unknown/disabled handled by LocalToolExecutor,
        # but we still pre-check here so we can emit a proper denial event.
        if tool and tool.authorization_policy == AuthorizationPolicy.AUTHENTICATED and not user_id:
            dur = int((time.time() - t0) * 1000)
            await self._audit(user_id, "tool_execution_denied", tool_name, "denied", context)
            await self._emit_telemetry("tool.execution.denied", tool_name, user_id, "denied", context, duration_ms=dur, error_type="authorization_error")
            return ToolResult(
                output=f"Tool '{tool_name}' requires authentication.",
                status="error",
                metadata={"error_type": "authorization_error"}
            )

        if tool and tool.authorization_policy == AuthorizationPolicy.ADMIN:
            role = context.get("role", "")
            if role != "ADMIN":
                dur = int((time.time() - t0) * 1000)
                await self._audit(user_id, "tool_execution_denied", tool_name, "denied", context)
                await self._emit_telemetry("tool.execution.denied", tool_name, user_id, "denied", context, duration_ms=dur, error_type="authorization_error")
                return ToolResult(
                    output=f"Tool '{tool_name}' requires administrative privileges.",
                    status="error",
                    metadata={"error_type": "authorization_error"}
                )

        # Emit start audit & telemetry
        await self._audit(user_id, "tool_execution_started", tool_name, "started", context)
        await self._emit_telemetry("tool.execution.started", tool_name, user_id, "started", context)

        # Execute with per-tool timeout
        try:
            async with asyncio.timeout(self.tool_timeout):
                result = await self.inner.execute(tool_call, context, allowed_tools)
        except asyncio.TimeoutError:
            dur = int((time.time() - t0) * 1000)
            await self._audit(user_id, "tool_timeout", tool_name, "timeout", context)
            await self._emit_telemetry("tool.execution.timeout", tool_name, user_id, "timeout", context, duration_ms=dur, error_type="timeout")
            return ToolResult(
                output=f"Tool '{tool_name}' timed out after {self.tool_timeout}s.",
                status="error",
                metadata={"error_type": "timeout"}
            )

        dur = int((time.time() - t0) * 1000)
        # Audit outcome & telemetry
        if result.status == "error":
            err_type = result.metadata.get("error_type", "error")
            event_action = "tool_execution_denied" if err_type in ("not_allowed", "authorization_error", "disabled") else "tool_execution_failed"
            telemetry_type = "tool.execution.denied" if err_type in ("not_allowed", "authorization_error", "disabled") else "tool.execution.failed"
            telemetry_status = "denied" if event_action == "tool_execution_denied" else result.status
            await self._audit(user_id, event_action, tool_name, result.status, context)
            await self._emit_telemetry(telemetry_type, tool_name, user_id, telemetry_status, context, duration_ms=dur, error_type=err_type)
        else:
            await self._audit(user_id, "tool_execution_completed", tool_name, "success", context)
            await self._emit_telemetry("tool.execution.completed", tool_name, user_id, "success", context, duration_ms=dur)

        return result

    async def _emit_telemetry(self, event_type: str, tool_name: str, user_id: str, status: str, context: Dict[str, Any], duration_ms: int = None, error_type: str = None) -> None:
        if not self.observability_service:
            return
        try:
            from app.core.observability.schemas import TelemetryEventCreate
            severity = "WARN" if event_type == "tool.execution.denied" or status == "denied" else ("ERROR" if status in ("error", "failed", "timeout") else "INFO")
            event = TelemetryEventCreate(
                event_type=event_type,
                component="tools",
                severity=severity,
                user_id=user_id or None,
                request_id=context.get("request_id"),
                correlation_id=context.get("correlation_id"),
                session_id=context.get("session_id"),
                duration_ms=duration_ms,
                status=status,
                error_type=error_type,
                metadata={"tool": tool_name}
            )
            await self.observability_service.emit_event(event)
        except Exception:
            pass

    async def _audit(self, user_id: str, action: str, tool_name: str, result: str, context: Dict[str, Any]) -> None:
        if not self.uow:
            return
        try:
            async with self.uow as uow:
                await uow.audit.create({
                    "user_id": user_id or None,
                    "action": action,
                    "resource_type": "tool",
                    "resource_id": tool_name,
                    "result": result,
                    "metadata_": {
                        "session_id": context.get("session_id"),
                        "agent_id": context.get("agent_id"),
                    }
                })
        except Exception:
            # Audit failure MUST NOT block tool execution (fail-open for availability)
            pass


# ---------------------------------------------------------------------------
# FakeToolExecutor (kept for test compatibility)
# ---------------------------------------------------------------------------

class FakeToolExecutor(ToolExecutor):
    """Fake executor used only for tests."""

    async def execute(self, tool_call: ToolRequest, context: Dict[str, Any], allowed_tools: List[str] = None) -> ToolResult:
        if tool_call.tool == "fail_tool":
            raise ValueError("Intentional tool failure")
        return ToolResult(
            output={"fake_result": f"Executed {tool_call.tool} with args {tool_call.arguments}"},
            status="success"
        )
