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
