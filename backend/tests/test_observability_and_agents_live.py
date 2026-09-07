import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from app.main import app
from app.db.database import Base, engine
from app.core.observability.service import get_observability_service
from app.core.observability.schemas import TelemetryEventCreate


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_observability_service_health_and_telemetry():
    """Verify ObservabilityService records real telemetry and performs healthy DB check."""
    service = get_observability_service()

    # 1. Health check should return healthy database
    health = await service.get_health()
    assert health.status in ("healthy", "degraded")
    assert "database" in health.dependencies
    assert health.dependencies["database"].status == "healthy"
    assert health.dependencies["database"].latency_ms is not None
    assert health.dependencies["database"].latency_ms >= 0

    # 2. Record telemetry events
    id1 = await service.emit_event(
        TelemetryEventCreate(
            component="agent",
            event_type="chat.request",
            status="success",
            duration_ms=125,
            metadata={"agent_name": "general_agent", "model_name": "llama3.2:latest", "user_id": "test_user"},
        )
    )
    assert id1 is not None

    id2 = await service.emit_event(
        TelemetryEventCreate(
            component="tool",
            event_type="excel.generate",
            status="success",
            duration_ms=450,
            metadata={"agent_name": "excel_agent", "file_name": "report.xlsx"},
        )
    )
    assert id2 is not None

    id3 = await service.emit_event(
        TelemetryEventCreate(
            component="llm",
            event_type="llm.failure",
            status="failure",
            duration_ms=50,
            error_type="TimeoutError",
            metadata={"error_message": "Simulated model timeout"},
        )
    )
    assert id3 is not None

    # 3. Retrieve events (with is_admin=True to view system-wide events)
    events = await service.get_events(is_admin=True, limit=10)
    assert len(events) >= 3
    event_types = [e.event_type for e in events]
    assert "chat.request" in event_types
    assert "excel.generate" in event_types
    assert "llm.failure" in event_types

    # 4. Latency metrics
    metrics = await service.get_metrics(is_admin=True)
    assert metrics is not None
    assert "counters" in metrics
    assert "average_latencies_ms" in metrics
    assert metrics["counters"].get("total_operations", 0) >= 3


@pytest.mark.asyncio
async def test_agents_endpoints_and_activity(async_client: AsyncClient):
    """Verify /api/v1/agents and /api/v1/agents/activity endpoints return real backend data."""
    # 1. Register and login
    await async_client.post(
        "/api/v1/auth/register",
        json={"username": "agentuser", "password": "agentpassword123", "email": "agent@test.com"}
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "agentuser", "password": "agentpassword123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    user_id = me_res.json()["id"]

    # 2. List agents
    res = await async_client.get("/api/v1/agents", headers=headers)
    assert res.status_code == 200
    agents = res.json()
    assert len(agents) >= 3

    agent_ids = [a["agent_id"] for a in agents]
    assert "general_agent" in agent_ids
    assert "excel_agent" in agent_ids
    assert "document_agent" in agent_ids
    assert "task_router" in agent_ids

    # Check excel agent details
    excel_agent = next(a for a in agents if a["agent_id"] == "excel_agent")
    assert excel_agent["status"] in ("ready", "running", "disabled", "error")
    assert "excel_operations" in excel_agent["capabilities"]
    # Must not contain fake/unimplemented capabilities
    assert "mcp_client" not in excel_agent["capabilities"]
    assert "vision" not in excel_agent["capabilities"]
    assert any("workbook" in t or "sheet" in t for t in excel_agent["tools"])

    # Check general agent details
    general_agent = next(a for a in agents if a["agent_id"] == "general_agent")
    assert general_agent["status"] in ("ready", "running", "disabled", "error")
    assert "text_generation" in general_agent["capabilities"]

    # 3. Activity feed (record an event with user_id so it matches user isolation)
    obs_service = get_observability_service()
    await obs_service.emit_event(
        TelemetryEventCreate(
            component="agent",
            event_type="agent.run.completed",
            user_id=user_id,
            status="success",
            duration_ms=250,
            metadata={"agent_id": "general_agent", "task": "Test query"},
        )
    )

    act_res = await async_client.get("/api/v1/agents/activity?limit=10", headers=headers)
    assert act_res.status_code == 200
    activities = act_res.json()
    assert isinstance(activities, list)
    assert len(activities) >= 1
    first_act = activities[0]
    assert "id" in first_act
    assert "agent" in first_act
    assert "task" in first_act
    assert "status" in first_act


def test_agent_state_transitions_and_concurrency():
    """Verify live status transitions: Running -> Ready, Running -> Error -> Running -> Ready, and concurrency."""
    from app.core.runtime.state_manager import AgentStateManager

    sm = AgentStateManager()
    agent_id = "excel_agent"

    # Initial state
    assert sm.get_status(agent_id, is_enabled=True) == "ready"
    assert sm.get_status(agent_id, is_enabled=False) == "disabled"

    # 1. Start execution -> Running
    sm.start_execution(agent_id, "req_1")
    assert sm.get_status(agent_id, is_enabled=True) == "running"

    # 2. Complete execution with success -> Ready
    sm.complete_execution(agent_id, "req_1", success=True)
    assert sm.get_status(agent_id, is_enabled=True) == "ready"

    # 3. Start execution -> Running, then fail -> Error
    sm.start_execution(agent_id, "req_2")
    assert sm.get_status(agent_id, is_enabled=True) == "running"
    sm.complete_execution(agent_id, "req_2", success=False)
    assert sm.get_status(agent_id, is_enabled=True) == "error"

    # 4. Subsequent execution recovers from Error -> Running -> Ready (Non-permanent error)
    sm.start_execution(agent_id, "req_3")
    assert sm.get_status(agent_id, is_enabled=True) == "running"
    sm.complete_execution(agent_id, "req_3", success=True)
    assert sm.get_status(agent_id, is_enabled=True) == "ready"

    # 5. Concurrent execution: Two requests in flight simultaneously
    sm.start_execution(agent_id, "corr_A")
    assert sm.get_status(agent_id, is_enabled=True) == "running"
    sm.start_execution(agent_id, "corr_B")
    assert sm.get_status(agent_id, is_enabled=True) == "running"

    # First request completes, but second is still running -> agent stays Running!
    sm.complete_execution(agent_id, "corr_A", success=True)
    assert sm.get_status(agent_id, is_enabled=True) == "running"

    # Second request completes -> agent transitions to Ready
    sm.complete_execution(agent_id, "corr_B", success=True)
    assert sm.get_status(agent_id, is_enabled=True) == "ready"


@pytest.mark.asyncio
async def test_concurrent_telemetry_writes_clean_session_ownership():
    """Verify 10 concurrent telemetry writes execute with clean session ownership and zero corruption."""
    import asyncio
    service = get_observability_service()

    async def write_event(idx: int):
        return await service.emit_event(
            TelemetryEventCreate(
                event_type="agent.run.completed" if idx % 2 == 0 else "tool.execution.completed",
                component="agent" if idx % 2 == 0 else "tool",
                status="success",
                duration_ms=100 + idx * 10,
                agent_id="excel_agent" if idx % 2 == 0 else "general_agent",
                operation=f"operation_{idx}",
                metadata={"test_index": idx, "user_id": "concurrent_tester"}
            )
        )

    # Launch 10 concurrent database writes
    results = await asyncio.gather(*[write_event(i) for i in range(10)])
    
    # All 10 must succeed and return generated UUIDs
    assert len(results) == 10
    assert all(r is not None for r in results)
    assert len(set(results)) == 10  # Unique IDs

    # Query events back
    events = await service.get_events(is_admin=True, limit=50)
    assert len(events) >= 10
