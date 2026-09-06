import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import Base, engine

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
async def test_register_and_login(async_client: AsyncClient):
    # Register user
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "testpassword123", "email": "test@test.com"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    
    # Login
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "testpassword123"}
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    
    # Get Me
    token = token_data["access_token"]
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"

@pytest.mark.asyncio
async def test_login_contract_oauth2_form(async_client: AsyncClient):
    # Register test user
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"username": "oauthuser", "password": "securepassword123"}
    )
    assert reg_resp.status_code == 200

    # 1. Login with proper form-encoded username & password
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "oauthuser", "password": "securepassword123"}
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 2. Invalid credentials returns 401
    bad_login = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "oauthuser", "password": "wrongpassword"}
    )
    assert bad_login.status_code == 401

    # 3. Use access token to get user profile
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "oauthuser"

@pytest.mark.asyncio
async def test_conversations_and_messages(async_client: AsyncClient):
    # Register and get token
    await async_client.post("/api/v1/auth/register", json={"username": "chatuser", "password": "password123"})
    login_resp = await async_client.post("/api/v1/auth/login", data={"username": "chatuser", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create conversation
    conv_resp = await async_client.post(
        "/api/v1/conversations",
        json={"title": "Test Conversation"},
        headers=headers
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]
    
    # List conversations
    list_conv_resp = await async_client.get("/api/v1/conversations", headers=headers)
    assert list_conv_resp.status_code == 200
    assert len(list_conv_resp.json()["items"]) == 1
    
    # Add message
    msg_resp = await async_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Hello World!"},
        headers=headers
    )
    assert msg_resp.status_code == 201
    assert msg_resp.json()["content"] == "Hello World!"
    assert msg_resp.json()["sequence_number"] == 1
    
    # List messages
    list_msg_resp = await async_client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert list_msg_resp.status_code == 200
    assert len(list_msg_resp.json()["items"]) == 1

@pytest.mark.asyncio
async def test_unauthorized_access(async_client: AsyncClient):
    # 1. No token
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401

    # 2. Invalid token
    response = await async_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"})
    assert response.status_code == 401
    
    # 3. Create two users, make sure User B cannot access User A's conversation
    # Register User A
    await async_client.post("/api/v1/auth/register", json={"username": "userA", "password": "password123"})
    token_a = (await async_client.post("/api/v1/auth/login", data={"username": "userA", "password": "password123"})).json()["access_token"]
    
    # Register User B
    await async_client.post("/api/v1/auth/register", json={"username": "userB", "password": "password123"})
    token_b = (await async_client.post("/api/v1/auth/login", data={"username": "userB", "password": "password123"})).json()["access_token"]
    
    # User A creates a conversation
    conv_resp = await async_client.post(
        "/api/v1/conversations",
        json={"title": "Secret Conversation"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    conv_id = conv_resp.json()["id"]
    
    # User B tries to read User A's conversation
    response = await async_client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response.status_code == 404 # CONVERSATION_NOT_FOUND (security through obscurity)

    # User B tries to add a message to User A's conversation
    response = await async_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "I am a hacker"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_list_agents_contract(async_client: AsyncClient):
    # 1. Unauthenticated request must return 401
    unauth_resp = await async_client.get("/api/v1/agents")
    assert unauth_resp.status_code == 401

    # 2. Authenticated user request must return 200
    await async_client.post("/api/v1/auth/register", json={"username": "agentuser", "password": "password123"})
    login_resp = await async_client.post("/api/v1/auth/login", data={"username": "agentuser", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await async_client.get("/api/v1/agents", headers=headers)
    assert resp.status_code == 200
    agents = resp.json()
    assert isinstance(agents, list)
    assert len(agents) > 0

    # 3. Verify agent structure
    agent_ids = [a["agent_id"] for a in agents]
    assert "general_agent" in agent_ids

    for agent in agents:
        assert "agent_id" in agent
        assert "name" in agent
        assert "description" in agent
        assert "version" in agent
        assert "status" in agent
        # Ensure internals are not exposed
        assert "instructions" not in agent

