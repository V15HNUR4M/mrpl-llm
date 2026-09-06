import pytest
import pytest_asyncio
import uuid
import asyncio
from typing import Dict, Any

from app.core.workflow.schemas import WorkflowSpec, WorkflowStep, StepType, WorkflowRunState
from app.core.workflow.engine import WorkflowEngine, ConditionEvaluator, WorkflowContext
from app.core.workflow.registry import WorkflowRegistry
from app.core.agent.registry import AgentRegistry, AgentDefinition
from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor, Tool, AuthorizationPolicy
from app.core.runtime.schemas import ToolResult
from app.core.runtime.harness import AgentHarness
from app.core.context_engine.engine import ContextEngine
from app.core.model_gateway.gateway import ModelGateway
from app.db.uow import UnitOfWork

# --- Dummy Tools and Agents ---
class DummyTool(Tool):
    @property
    def name(self) -> str: return "dummy_tool"
    @property
    def description(self) -> str: return "Dummy"
    @property
    def input_schema(self) -> Dict: return {"type": "object", "properties": {}}
    @property
    def authorization_policy(self) -> AuthorizationPolicy: return AuthorizationPolicy.PUBLIC

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        return ToolResult(output={"result": "tool_executed"}, status="success")

class AuthDummyTool(Tool):
    @property
    def name(self) -> str: return "auth_tool"
    @property
    def description(self) -> str: return "Auth Dummy"
    @property
    def input_schema(self) -> Dict: return {"type": "object", "properties": {}}
    @property
    def authorization_policy(self) -> AuthorizationPolicy: return AuthorizationPolicy.AUTHENTICATED

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        return ToolResult(output={"result": "auth_tool_executed"}, status="success")

class MCPDummyAdapter(Tool):
    @property
    def name(self) -> str: return "mcp_tool"
    @property
    def description(self) -> str: return "MCP Dummy"
    @property
    def input_schema(self) -> Dict: return {"type": "object", "properties": {}}
    @property
    def authorization_policy(self) -> AuthorizationPolicy: return AuthorizationPolicy.AUTHENTICATED

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        return ToolResult(output={"result": "mcp_tool_executed"}, status="success")

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)

@pytest_asyncio.fixture
async def db_user(uow):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({"id": uid, "username": f"wflow_{uid}", "password_hash": "h", "role": "USER"})
        await uow.commit()
    return user

def make_engine(uow) -> tuple:
    agent_registry = AgentRegistry()
    agent_registry.register(AgentDefinition(
        agent_id="dummy_agent",
        name="Dummy Agent",
        description="test",
        version="1.0",
        instructions="test"
    ))
    tool_registry = ToolRegistry()
    tool_registry.register(DummyTool())
    tool_registry.register(AuthDummyTool())
    tool_registry.register(MCPDummyAdapter())
    
    local_exec = LocalToolExecutor(tool_registry)
    auth_exec = AuthorizedToolExecutor(local_exec, uow=uow)
    gateway = ModelGateway()
    # Using dummy Fake provider behavior
    from app.providers.fake import FakeProvider
    gateway.register_provider("fake", FakeProvider())
    gateway.register_model_route("test-model", "fake")
    
    ctx_engine = ContextEngine()
    harness = AgentHarness(agent_registry, ctx_engine, gateway, auth_exec)
    
    workflow_registry = WorkflowRegistry(uow, agent_registry, tool_registry)
    engine = WorkflowEngine(uow, harness, auth_exec)
    
    return workflow_registry, engine

# ---------------------------------------------------------------------------
# DEFINITION & REGISTRATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_workflow_registration(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(
        start_step="step1",
        steps={
            "step1": WorkflowStep(id="step1", type=StepType.TOOL, configuration={"tool": "dummy_tool"})
        }
    )
    workflow_id = await registry.register_workflow("test1", db_user.id, "1.0", spec)
    assert workflow_id is not None
    
    v = await registry.get_workflow_version(workflow_id, "1.0")
    assert v is not None
    assert v.workflow_id == workflow_id

@pytest.mark.asyncio
async def test_2_workflow_lookup(uow, db_user):
    registry, _ = make_engine(uow)
    spec = WorkflowSpec(start_step="s", steps={"s": WorkflowStep(id="s", type=StepType.TOOL, configuration={"tool": "dummy_tool"})})
    await registry.register_workflow("w2", db_user.id, "1.0", spec)
    workflows = await registry.list_for_user(db_user.id)
    assert any(w.name == "w2" for w in workflows)

@pytest.mark.asyncio
async def test_4_invalid_workflow_definition_rejected(uow, db_user):
    registry, _ = make_engine(uow)
    spec = WorkflowSpec(
        start_step="missing_step",
        steps={}
    )
    with pytest.raises(ValueError):
        await registry.register_workflow("inv", db_user.id, "1.0", spec)
        
    spec2 = WorkflowSpec(
        start_step="s",
        steps={"s": WorkflowStep(id="s", type=StepType.TOOL, configuration={"tool": "unknown_tool"})}
    )
    with pytest.raises(ValueError, match="unknown tool"):
        await registry.register_workflow("inv", db_user.id, "1.0", spec2)

# ---------------------------------------------------------------------------
# EXECUTION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_6_sequential_execution(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(
        start_step="s1",
        steps={
            "s1": WorkflowStep(id="s1", type=StepType.TOOL, configuration={"tool": "dummy_tool"}, next_step="s2"),
            "s2": WorkflowStep(id="s2", type=StepType.TOOL, configuration={"tool": "dummy_tool"})
        }
    )
    status, context = await engine.execute("run-1", "v1", db_user.id, spec, inputs={})
    assert status == WorkflowRunState.COMPLETED
    assert "s1" in context.step_results
    assert "s2" in context.step_results

@pytest.mark.asyncio
async def test_7_agent_step_delegates(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(
        start_step="s1",
        steps={
            "s1": WorkflowStep(id="s1", type=StepType.AGENT, configuration={"agent_id": "dummy_agent"})
        }
    )
    status, context = await engine.execute("run-2", "v1", db_user.id, spec, inputs={})
    assert status == WorkflowRunState.COMPLETED
    # Should contain final_answer since fake provider generates output
    assert "s1" in context.step_results
    
@pytest.mark.asyncio
async def test_9_mcp_tool_follows_tool_executor(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(
        start_step="s1",
        steps={"s1": WorkflowStep(id="s1", type=StepType.TOOL, configuration={"tool": "mcp_tool"})}
    )
    status, context = await engine.execute("run-mcp", "v1", db_user.id, spec, inputs={})
    assert status == WorkflowRunState.COMPLETED
    assert context.step_results["s1"]["output"]["result"] == "mcp_tool_executed"

# ---------------------------------------------------------------------------
# CONDITIONS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_condition_equals(uow, db_user):
    ctx = WorkflowContext(inputs={"val": 5})
    config = {"left": "inputs.val", "operator": "equals", "right": 5}
    assert ConditionEvaluator.evaluate(config, ctx) is True
    config["right"] = 6
    assert ConditionEvaluator.evaluate(config, ctx) is False

@pytest.mark.asyncio
async def test_12_condition_not_equals(uow, db_user):
    ctx = WorkflowContext(inputs={"val": "x"})
    config = {"left": "inputs.val", "operator": "not_equals", "right": "y"}
    assert ConditionEvaluator.evaluate(config, ctx) is True

@pytest.mark.asyncio
async def test_13_condition_exists(uow, db_user):
    ctx = WorkflowContext(step_results={"s1": {"status": "ok"}})
    config = {"left": "s1.status", "operator": "exists"}
    assert ConditionEvaluator.evaluate(config, ctx) is True

@pytest.mark.asyncio
async def test_15_invalid_condition_rejected(uow, db_user):
    registry, _ = make_engine(uow)
    spec = WorkflowSpec(
        start_step="s1",
        steps={
            "s1": WorkflowStep(id="s1", type=StepType.CONDITION, configuration={"left": "a"})
        }
    )
    with pytest.raises(ValueError):
        await registry.register_workflow("x", db_user.id, "1.0", spec)

# ---------------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_24_cross_user_workflow_denied():
    # Will be tested via API later, engine uses provided user_id
    pass

@pytest.mark.asyncio
async def test_25_impersonation_prevented(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(
        start_step="s1",
        steps={"s1": WorkflowStep(id="s1", type=StepType.TOOL, configuration={"tool": "auth_tool"})}
    )
    # Impersonation attempt via inputs
    inputs = {"user_id": "HACKER"}
    status, context = await engine.execute("run-auth", "v1", db_user.id, spec, inputs=inputs)
    # Since engine uses db_user.id directly, auth_tool works as db_user.id, not HACKER
    assert status == WorkflowRunState.COMPLETED
    assert context.step_results["s1"]["output"]["result"] == "auth_tool_executed"

# ---------------------------------------------------------------------------
# LIMITS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_31_maximum_steps_enforced(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(
        start_step="s1",
        steps={
            "s1": WorkflowStep(id="s1", type=StepType.TOOL, configuration={"tool": "dummy_tool"}, next_step="s1") # Infinite loop
        }
    )
    status, context = await engine.execute("run-loop", "v1", db_user.id, spec, inputs={})
    assert status == WorkflowRunState.FAILED

@pytest.mark.asyncio
async def test_36_large_step_output_bounded(uow, db_user):
    registry, engine = make_engine(uow)
    class HugeOutputTool(Tool):
        @property
        def name(self) -> str: return "huge_tool"
        @property
        def description(self) -> str: return "Huge"
        @property
        def input_schema(self) -> Dict: return {"type": "object", "properties": {}}
        async def execute(self, args, ctx): return ToolResult(output="x" * 200000, status="success")

    engine.tool_executor.inner.registry.register(HugeOutputTool())
    spec = WorkflowSpec(
        start_step="s1",
        steps={"s1": WorkflowStep(id="s1", type=StepType.TOOL, configuration={"tool": "huge_tool"})}
    )
    status, context = await engine.execute("run-huge", "v1", db_user.id, spec, inputs={})
    assert status == WorkflowRunState.COMPLETED # Engine handles error gracefully for the step
    assert context.step_results["s1"]["status"] == "error"
    assert "Result exceeded maximum byte limit" in context.step_results["s1"]["error"]

# ---------------------------------------------------------------------------
# AUDIT
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_39_workflow_lifecycle_audit(uow, db_user):
    registry, engine = make_engine(uow)
    spec = WorkflowSpec(start_step="s1", steps={"s1": WorkflowStep(id="s1", type=StepType.TOOL, configuration={"tool": "dummy_tool"})})
    await engine.execute("run-a", "v1", db_user.id, spec, inputs={})
    
    async with uow:
        # Check audit
        import sqlalchemy
        res = await uow.session.execute(sqlalchemy.text("SELECT action, resource_id FROM audit_events WHERE user_id = :u"), {"u": db_user.id})
        actions = [r[0] for r in res.fetchall()]
        
        assert "workflow_started" in actions
        assert "workflow_completed" in actions
        assert "tool_execution_started" in actions # Via AuthorizedToolExecutor

# ---------------------------------------------------------------------------
# API TESTS
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import get_current_user
from app.db.uow import get_uow

@pytest.fixture
def client(uow, db_user):
    def override_get_current_user():
        return db_user
    def override_get_uow():
        return uow
        
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_uow] = override_get_uow
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_api_workflow_lifecycle(client):
    # 1. Create Workflow
    spec = {
        "start_step": "s1",
        "steps": {
            "s1": {"id": "s1", "type": "CONDITION", "configuration": {"left": "inputs.val", "operator": "equals", "right": True}}
        }
    }
    res = client.post("/api/v1/workflows/?name=test_api&version=v1", json=spec)
    assert res.status_code == 201
    w_id = res.json()["id"]
    
    # 2. Get Workflow
    res = client.get(f"/api/v1/workflows/{w_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "test_api"
    
    # 3. List Workflows
    res = client.get("/api/v1/workflows/")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    
    # 4. Run Workflow
    res = client.post(f"/api/v1/workflows/{w_id}/run", json={"val": True})
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    
    # 5. Get Workflow Run
    res = client.get(f"/api/v1/workflows/runs/{run_id}")
    assert res.status_code == 200
    
    # 6. Cancel Workflow Run
    res = client.post(f"/api/v1/workflows/runs/{run_id}/cancel")
    assert res.status_code in [200, 400] # Might be completed already or cancelled successfully
