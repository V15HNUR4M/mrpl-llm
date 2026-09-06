import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.core.agent.registry import AgentRegistry
from app.db.uow import get_uow
from app.db.models import User
from app.core.security import create_access_token

@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient):
    # Reroute the default model to fake for integration tests
    from app.main import app
    from app.core.config import settings
    app.state.model_gateway.register_model_route(settings.DEFAULT_CHAT_MODEL, "fake")
    
    await async_client.post("/api/v1/auth/register", json={"username": "agentuser", "password": "password123"})
    login_resp = await async_client.post("/api/v1/auth/login", data={"username": "agentuser", "password": "password123"})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_api_run_general_agent(async_client: AsyncClient, auth_headers):
    # Create conversation first
    conv_resp = await async_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "Test Conv"}
    )
    conv_id = conv_resp.json()["id"]

    # general_agent is pre-registered in main.py
    response = await async_client.post(
        "/api/v1/agents/general_agent/run",
        headers=auth_headers,
        json={"message": "Hello MRPL", "conversation_id": conv_id}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] is not None
    assert "Fake response for" in data["final_answer"]
    
@pytest.mark.asyncio
async def test_api_run_disabled_agent(async_client: AsyncClient, auth_headers):
    # Create conversation first
    conv_resp = await async_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "Test Conv"}
    )
    conv_id = conv_resp.json()["id"]

    # disabled_agent is pre-registered in main.py
    response = await async_client.post(
        "/api/v1/agents/disabled_agent/run",
        headers=auth_headers,
        json={"message": "Hello MRPL", "conversation_id": conv_id}
    )
    assert response.status_code == 400
    assert "disabled" in response.json()["detail"].lower()
    
@pytest.mark.asyncio
async def test_api_run_unknown_agent(async_client: AsyncClient, auth_headers):
    # Create conversation first
    conv_resp = await async_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "Test Conv"}
    )
    conv_id = conv_resp.json()["id"]

    response = await async_client.post(
        "/api/v1/agents/unknown_agent/run",
        headers=auth_headers,
        json={"message": "Hello MRPL", "conversation_id": conv_id}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_default_chat_model_configuration():
    from app.core.config import settings
    assert settings.DEFAULT_CHAT_MODEL == "llama3.2:latest"

@pytest.mark.asyncio
async def test_api_stream_general_agent_persists_assistant_message_and_no_leak(async_client: AsyncClient, auth_headers):
    import json
    import warnings
    from sqlalchemy.exc import SAWarning

    # Create conversation
    conv_resp = await async_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "Stream Conv"}
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    # Catch any SAWarning during streaming
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always", SAWarning)

        # Call streaming endpoint
        response = await async_client.post(
            "/api/v1/agents/general_agent/stream",
            headers=auth_headers,
            json={"message": "Explain refinery catalysts", "conversation_id": conv_id}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        events = []
        for line in response.text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

        # Verify event sequence
        event_types = [e["type"] for e in events]
        assert "session_created" in event_types
        assert "state_changed" in event_types
        assert "text_delta" in event_types
        assert "completed" in event_types
        assert "error" not in event_types

        # Verify assistant message was persisted to database
        msgs_resp = await async_client.get(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=auth_headers
        )
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()["items"]
        assert len(messages) >= 2
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles
        assistant_msg = next(m for m in messages if m["role"] == "assistant")
        assert len(assistant_msg["content"]) > 0

        # Verify no SAWarning (connection leak) was emitted
        connection_warnings = [
            w for w in captured_warnings 
            if issubclass(w.category, SAWarning) and "non-checked-in connection" in str(w.message)
        ]
        assert len(connection_warnings) == 0

