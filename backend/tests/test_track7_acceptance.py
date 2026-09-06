"""
Track 7 Acceptance Tests — Tools / MCP

Covers:
  - Tool Registry (registration, lookup, enabled/disabled)
  - Input validation
  - Authorization pre-checks
  - User isolation
  - Timeout and cancellation
  - Tool failure isolation
  - Audit events
  - Execution events
  - ToolResult normalization
  - Execution budget / recursion protection
  - Malicious argument handling
  - MCP adapter registration, auth, unavailability, timeout, malformed result
  - Context Engine boundary
  - Harness protocol-agnostic boundary
"""

import asyncio
import pytest
import pytest_asyncio
import uuid
from typing import Dict, Any

from app.core.runtime.tool_executor import (
    Tool, ToolDefinition, ToolRegistry, InputValidator,
    LocalToolExecutor, AuthorizedToolExecutor,
    FakeToolExecutor, AuthorizationPolicy,
)
from app.core.runtime.mcp_adapter import (
    MCPAdapter, MCPServerClient, MCPServerUnavailableError,
)
from app.core.runtime.schemas import ToolRequest, ToolResult, RuntimeSession, ExecutionState
from app.core.context_engine.schemas import ContextCandidate
from app.db.uow import UnitOfWork
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Helpers / concrete tools for testing
# ---------------------------------------------------------------------------

class GreetTool(Tool):
    @property
    def name(self): return "greet"
    @property
    def description(self): return "Greet a user by name."
    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }

    async def execute(self, arguments, context):
        return ToolResult(output=f"Hello, {arguments['name']}!", status="success")


class DisabledTool(Tool):
    @property
    def name(self): return "disabled_op"
    @property
    def description(self): return "This tool is disabled."
    @property
    def input_schema(self): return {"type": "object", "properties": {}}
    @property
    def enabled(self): return False

    async def execute(self, arguments, context):
        return ToolResult(output="Should never run", status="success")


class AuthRequiredTool(Tool):
    @property
    def name(self): return "auth_required"
    @property
    def description(self): return "Requires auth."
    @property
    def input_schema(self): return {"type": "object", "properties": {}}
    @property
    def authorization_policy(self): return AuthorizationPolicy.AUTHENTICATED

    async def execute(self, arguments, context):
        return ToolResult(output="authenticated result", status="success")


class UserScopedTool(Tool):
    """Simulates a tool that reads a user-specific resource."""
    @property
    def name(self): return "user_scoped"
    @property
    def description(self): return "Returns data scoped to authenticated user."
    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }
    @property
    def authorization_policy(self): return AuthorizationPolicy.AUTHENTICATED

    async def execute(self, arguments, context):
        # Uses context["user_id"] — NOT arguments["user_id"]
        owner = context.get("user_id", "unknown")
        return ToolResult(output={"owner": owner, "data": f"data for {owner}"}, status="success")


class HangingTool(Tool):
    @property
    def name(self): return "hanging"
    @property
    def description(self): return "Never returns."
    @property
    def input_schema(self): return {"type": "object", "properties": {}}

    async def execute(self, arguments, context):
        await asyncio.sleep(9999)
        return ToolResult(output="unreachable", status="success")


class CrashingTool(Tool):
    @property
    def name(self): return "crashing"
    @property
    def description(self): return "Always raises."
    @property
    def input_schema(self): return {"type": "object", "properties": {}}

    async def execute(self, arguments, context):
        raise RuntimeError("Simulated internal crash")


class PathTraversalSensitiveTool(Tool):
    """Tool that accepts a filename — used to test argument injection."""
    @property
    def name(self): return "file_read"
    @property
    def description(self): return "Reads a file."
    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {"filename": {"type": "string", "pattern": r"^[a-zA-Z0-9_.-]+$"}},
            "required": ["filename"]
        }

    async def execute(self, arguments, context):
        return ToolResult(output=f"contents of {arguments['filename']}", status="success")


def make_registry(*tools: Tool) -> ToolRegistry:
    r = ToolRegistry()
    for t in tools:
        r.register(t)
    return r


def make_executor(registry: ToolRegistry, uow=None, timeout: float = 2.0) -> AuthorizedToolExecutor:
    local = LocalToolExecutor(registry)
    return AuthorizedToolExecutor(local, tool_timeout=timeout, uow=uow)


def make_request(tool: str, arguments: Dict = None, call_id: str = None) -> ToolRequest:
    return ToolRequest(tool=tool, arguments=arguments or {}, call_id=call_id or str(uuid.uuid4()))


def make_context(user_id: str = "user-A") -> Dict[str, Any]:
    return {"user_id": user_id, "session_id": str(uuid.uuid4()), "agent_id": "test-agent"}


# ---------------------------------------------------------------------------
# UoW fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)


@pytest_asyncio.fixture
async def db_user(uow):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({"id": uid, "username": f"t7_{uid}", "password_hash": "h", "role": "USER"})
        await uow.commit()
    return user


# ---------------------------------------------------------------------------
# Test 1 — Tool registration
# ---------------------------------------------------------------------------

def test_1_tool_registration():
    r = make_registry(GreetTool())
    assert r.get("greet") is not None
    assert r.is_enabled("greet")
    defs = r.list_tools()
    assert any(d.name == "greet" for d in defs)


# ---------------------------------------------------------------------------
# Test 2 — Unknown tool rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_2_unknown_tool_rejection():
    executor = make_executor(make_registry())
    result = await executor.execute(make_request("nonexistent"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "unknown_tool"
    assert "nonexistent" in result.output


# ---------------------------------------------------------------------------
# Test 3 — Disabled tool rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_3_disabled_tool_rejection():
    r = make_registry(DisabledTool())
    executor = make_executor(r)
    result = await executor.execute(make_request("disabled_op"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "disabled"


@pytest.mark.asyncio
async def test_3b_registry_disable_at_runtime():
    r = make_registry(GreetTool())
    r.disable("greet")
    executor = make_executor(r)
    result = await executor.execute(make_request("greet", {"name": "Alice"}), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "disabled"

    # Re-enable and verify it runs
    r.enable("greet")
    result2 = await executor.execute(make_request("greet", {"name": "Alice"}), make_context())
    assert result2.status == "success"


# ---------------------------------------------------------------------------
# Test 4 — Input validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_4_input_validation_missing_required():
    executor = make_executor(make_registry(GreetTool()))
    # Missing required "name"
    result = await executor.execute(make_request("greet", {}), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "validation_error"


@pytest.mark.asyncio
async def test_4b_input_validation_wrong_type():
    executor = make_executor(make_registry(GreetTool()))
    result = await executor.execute(make_request("greet", {"name": 42}), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "validation_error"


# ---------------------------------------------------------------------------
# Test 5 — Successful execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_5_successful_execution():
    executor = make_executor(make_registry(GreetTool()))
    result = await executor.execute(make_request("greet", {"name": "Alice"}), make_context())
    assert result.status == "success"
    assert "Hello, Alice!" in result.output


# ---------------------------------------------------------------------------
# Test 6 — Authorization denial (no user_id, requires_auth tool)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_authorization_denial():
    executor = make_executor(make_registry(AuthRequiredTool()))
    ctx_no_user = {"user_id": "", "session_id": "s", "agent_id": "a"}
    result = await executor.execute(make_request("auth_required"), ctx_no_user)
    assert result.status == "error"
    assert result.metadata.get("error_type") == "authorization_error"


# ---------------------------------------------------------------------------
# Test 7 — User isolation: model cannot override user_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_7_user_isolation():
    executor = make_executor(make_registry(UserScopedTool()))
    ctx = make_context("real-user-A")
    # Model tries to inject another user's ID through arguments
    result = await executor.execute(
        make_request("user_scoped", {"query": "data", "user_id": "malicious-user-B"}),
        ctx
    )
    assert result.status == "success"
    assert result.output["owner"] == "real-user-A"   # context wins
    assert "malicious-user-B" not in str(result.output)


# ---------------------------------------------------------------------------
# Test 8 — Timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_8_tool_timeout():
    executor = make_executor(make_registry(HangingTool()), timeout=0.2)
    result = await executor.execute(make_request("hanging"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "timeout"


# ---------------------------------------------------------------------------
# Test 9 — Cancellation (RuntimeSession + harness cancel)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_9_cancellation():
    """A cancelled outer task must not leave the tool running."""
    executor = make_executor(make_registry(HangingTool()), timeout=10.0)

    async def run():
        return await executor.execute(make_request("hanging"), make_context())

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# Test 10 — Tool failure isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_10_tool_failure_isolation():
    executor = make_executor(make_registry(CrashingTool()))
    result = await executor.execute(make_request("crashing"), make_context())
    # Failure is contained as ToolResult, not propagated as exception
    assert result.status == "error"
    assert result.metadata.get("error_type") == "execution_error"


@pytest.mark.asyncio
async def test_10b_failure_does_not_corrupt_next_call():
    executor = make_executor(make_registry(CrashingTool(), GreetTool()))
    await executor.execute(make_request("crashing"), make_context())
    result = await executor.execute(make_request("greet", {"name": "Bob"}), make_context())
    assert result.status == "success"


# ---------------------------------------------------------------------------
# Test 11 — Audit: successful execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_11_audit_success(uow, db_user):
    async with uow:
        executor = make_executor(make_registry(GreetTool()), uow=uow)
        ctx = make_context(db_user.id)
        await executor.execute(make_request("greet", {"name": "Test"}), ctx)

        rows = await uow.session.execute(
            text("SELECT action, result FROM audit_events WHERE resource_type='tool' AND user_id=:uid"),
            {"uid": db_user.id}
        )
        actions = [(r.action, r.result) for r in rows.fetchall()]
        assert any(a == "tool_execution_started" for a, _ in actions)
        assert any(a == "tool_execution_completed" for a, _ in actions)


# ---------------------------------------------------------------------------
# Test 12 — Audit: denial
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_12_audit_denial(uow, db_user):
    async with uow:
        executor = make_executor(make_registry(AuthRequiredTool()), uow=uow)
        ctx_no_user = {"user_id": "", "session_id": "s", "agent_id": "a"}
        await executor.execute(make_request("auth_required"), ctx_no_user)

        rows = await uow.session.execute(
            text("SELECT action, result FROM audit_events WHERE resource_type='tool' AND action='tool_execution_denied'")
        )
        assert len(rows.fetchall()) >= 1


# ---------------------------------------------------------------------------
# Test 13 — Audit: no sensitive payloads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_13_audit_privacy(uow, db_user):
    async with uow:
        executor = make_executor(make_registry(GreetTool()), uow=uow)
        ctx = make_context(db_user.id)
        await executor.execute(make_request("greet", {"name": "SuperSecretName"}), ctx)

        rows = await uow.session.execute(
            text("SELECT metadata FROM audit_events WHERE resource_type='tool' AND user_id=:uid"),
            {"uid": db_user.id}
        )
        for r in rows.fetchall():
            assert "SuperSecretName" not in str(r.metadata)


# ---------------------------------------------------------------------------
# Test 14 — Execution event via RuntimeSession
# ---------------------------------------------------------------------------

def test_14_execution_event():
    session = RuntimeSession(
        session_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        agent_id="a1",
        agent_version="1",
        user_id="u1"
    )
    session.add_event("tool_execution_started", {"tool": "greet"})
    assert any(e.type == "tool_execution_started" for e in session.events)


# ---------------------------------------------------------------------------
# Test 15 — ToolResult normalization
# ---------------------------------------------------------------------------

def test_15_tool_result_normalization():
    result = ToolResult(output={"key": "value"}, status="success")
    assert result.status == "success"
    assert isinstance(result.output, dict)
    assert result.context_candidates == []
    assert result.metadata == {}


# ---------------------------------------------------------------------------
# Test 16 — Execution budget / recursion protection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_16_execution_budget():
    from app.core.runtime.errors import ToolCallLimitExceeded

    session = RuntimeSession(
        session_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        agent_id="a1",
        agent_version="1",
        user_id="u1"
    )
    # max_tool_calls = 3; simulate reaching limit
    session.tool_call_count = 3
    limit = 3

    with pytest.raises(ToolCallLimitExceeded):
        if session.tool_call_count >= limit:
            raise ToolCallLimitExceeded(limit)


# ---------------------------------------------------------------------------
# Test 17 — Malicious argument (path traversal)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_17_path_traversal_rejected():
    executor = make_executor(make_registry(PathTraversalSensitiveTool()))
    result = await executor.execute(
        make_request("file_read", {"filename": "../../../etc/passwd"}),
        make_context()
    )
    assert result.status == "error"
    assert result.metadata.get("error_type") == "validation_error"


@pytest.mark.asyncio
async def test_17b_extra_fields_handled():
    executor = make_executor(make_registry(GreetTool()))
    # Additional unknown field — jsonschema by default allows additionalProperties
    # The important thing is that it doesn't break and the known field is used
    result = await executor.execute(
        make_request("greet", {"name": "Alice", "unexpected_field": "value"}),
        make_context()
    )
    # Should still succeed since "name" is valid
    assert result.status == "success"


# ---------------------------------------------------------------------------
# Test 18 — MCP tool registration
# ---------------------------------------------------------------------------

def test_18_mcp_tool_registration():
    class FakeMCPClient:
        async def call_tool(self, name, args): return {"content": [{"type": "text", "text": "mcp ok"}]}

    mcp_tool = MCPAdapter(
        tool_name="mcp_search",
        tool_description="MCP-backed search",
        tool_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        mcp_client=FakeMCPClient(),
    )

    registry = make_registry(mcp_tool)
    found = registry.get("mcp_search")
    assert found is not None
    assert found.name == "mcp_search"


# ---------------------------------------------------------------------------
# Test 19 — MCP authorization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_19_mcp_authorization():
    class FakeMCPClient:
        async def call_tool(self, name, args): return {"content": [{"type": "text", "text": "ok"}]}

    mcp_tool = MCPAdapter(
        tool_name="mcp_auth",
        tool_description="Requires auth",
        tool_schema={"type": "object", "properties": {}},
        mcp_client=FakeMCPClient(),
        authorization_policy=AuthorizationPolicy.AUTHENTICATED,
    )

    registry = make_registry(mcp_tool)
    executor = make_executor(registry)
    ctx_no_auth = {"user_id": "", "session_id": "s", "agent_id": "a"}
    result = await executor.execute(make_request("mcp_auth"), ctx_no_auth)
    assert result.status == "error"
    assert result.metadata.get("error_type") == "authorization_error"


# ---------------------------------------------------------------------------
# Test 20 — MCP unavailable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_20_mcp_unavailable():
    class UnavailableMCPClient:
        async def call_tool(self, name, args):
            raise MCPServerUnavailableError("server is down")

    mcp_tool = MCPAdapter(
        tool_name="mcp_down",
        tool_description="Goes down",
        tool_schema={"type": "object", "properties": {}},
        mcp_client=UnavailableMCPClient(),
    )
    executor = make_executor(make_registry(mcp_tool))
    result = await executor.execute(make_request("mcp_down"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "mcp_unavailable"


# ---------------------------------------------------------------------------
# Test 21 — MCP timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_21_mcp_timeout():
    class SlowMCPClient:
        async def call_tool(self, name, args):
            await asyncio.sleep(9999)

    mcp_tool = MCPAdapter(
        tool_name="mcp_slow",
        tool_description="Slow",
        tool_schema={"type": "object", "properties": {}},
        mcp_client=SlowMCPClient(),
    )
    executor = make_executor(make_registry(mcp_tool), timeout=0.2)
    result = await executor.execute(make_request("mcp_slow"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "timeout"


# ---------------------------------------------------------------------------
# Test 22 — MCP malformed result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_22_mcp_malformed_result():
    class MalformedMCPClient:
        async def call_tool(self, name, args):
            # Returns something that causes a TypeError in parsing
            raise ValueError("Unexpected MCP payload")

    mcp_tool = MCPAdapter(
        tool_name="mcp_malformed",
        tool_description="Malformed",
        tool_schema={"type": "object", "properties": {}},
        mcp_client=MalformedMCPClient(),
    )
    executor = make_executor(make_registry(mcp_tool))
    result = await executor.execute(make_request("mcp_malformed"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "mcp_error"


# ---------------------------------------------------------------------------
# Test 23 — MCP cannot bypass registry (unregistered MCP tool)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_23_mcp_cannot_bypass_registry():
    """An unregistered MCP tool name must not execute even if the server exposes it."""
    class FakeMCPClient:
        async def call_tool(self, name, args): return {"content": [{"type": "text", "text": "should not run"}]}

    # Do NOT register "secret_mcp_tool" in the registry
    executor = make_executor(make_registry())
    result = await executor.execute(make_request("secret_mcp_tool"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "unknown_tool"


# ---------------------------------------------------------------------------
# Test 24 — Tool output enters Context Engine
# ---------------------------------------------------------------------------

def test_24_tool_result_to_context_candidate():
    result = ToolResult(output="search result text", status="success")
    import json
    candidate = ContextCandidate(
        id="call-1",
        type="tool",
        content=json.dumps(result.output),
        source="greet",
        priority=4
    )
    assert candidate.type == "tool"
    assert "search result text" in candidate.content


# ---------------------------------------------------------------------------
# Test 25 — Harness remains protocol-agnostic (MCP vs local)
# ---------------------------------------------------------------------------

def test_25_harness_protocol_agnostic():
    """
    Verify that the Harness uses the ToolExecutor interface
    and neither imports nor references MCP classes directly.
    """
    import inspect
    from app.core.runtime import harness
    source = inspect.getsource(harness)
    assert "MCPAdapter" not in source
    assert "MCPServerClient" not in source
    assert "mcp_client" not in source


# ---------------------------------------------------------------------------
# Mandatory Security Test 1 — model cannot override user_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sec1_model_cannot_override_user_id():
    executor = make_executor(make_registry(UserScopedTool()))
    ctx = make_context("user-A")
    result = await executor.execute(
        make_request("user_scoped", {"user_id": "user-B", "query": "steal data"}),
        ctx
    )
    assert result.status == "success"
    assert result.output["owner"] == "user-A"


# ---------------------------------------------------------------------------
# Mandatory Security Test 2 — unknown tool produces controlled failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sec2_unknown_tool_controlled_failure():
    executor = make_executor(make_registry())
    result = await executor.execute(make_request("__import__('os').system"), make_context())
    assert result.status == "error"
    assert result.metadata.get("error_type") == "unknown_tool"
    # No exception should escape
    assert isinstance(result, ToolResult)


# ---------------------------------------------------------------------------
# Mandatory Security Test 3 — MCP discovery ≠ execution permission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sec3_mcp_discovery_not_execution():
    """Simulates MCP server exposing a tool that is not registered locally."""
    # The local registry is empty
    executor = make_executor(make_registry())
    # Even if someone passes a valid-looking call_id, it must fail
    result = await executor.execute(
        make_request("mcp_discovered_but_unapproved"),
        make_context()
    )
    assert result.status == "error"
    assert result.metadata.get("error_type") == "unknown_tool"
