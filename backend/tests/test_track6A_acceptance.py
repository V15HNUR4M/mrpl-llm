import pytest
import uuid
import json
from httpx import AsyncClient

from app.db.uow import UnitOfWork
from app.services.conversation import ConversationService
from app.core.config import settings
from app.core.runtime.schemas import RuntimeSession, ExecutionState
from app.core.context_engine.schemas import ContextCandidate

import pytest_asyncio

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)

@pytest.fixture(autouse=True)
def setup_fake_model():
    from app.main import app
    from app.core.config import settings
    app.state.model_gateway.register_model_route(settings.DEFAULT_CHAT_MODEL, "fake")

@pytest_asyncio.fixture
async def track6_user(uow: UnitOfWork):
    # Setup test user
    user_id = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": user_id,
            "username": f"testuser_{user_id}",
            "password_hash": "hash",
            "role": "USER",
            "is_active": True
        })
        await uow.commit()
    return user

@pytest_asyncio.fixture
async def other_user(uow: UnitOfWork):
    user_id = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": user_id,
            "username": f"otheruser_{user_id}",
            "password_hash": "hash",
            "role": "USER",
            "is_active": True
        })
        await uow.commit()
    return user

@pytest_asyncio.fixture
async def test_conv(uow: UnitOfWork, track6_user):
    conv_id = str(uuid.uuid4())
    async with uow:
        conv = await uow.conversations.create({
            "id": conv_id,
            "user_id": track6_user.id,
            "title": "Test Conversation"
        })
        await uow.commit()
    return conv

@pytest.fixture
def auth_headers(track6_user):
    from app.dependencies import oauth2_scheme
    from jose import jwt
    token = jwt.encode({"sub": track6_user.username}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def other_auth_headers(other_user):
    from jose import jwt
    token = jwt.encode({"sub": other_user.username}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_1_empty_conversation(async_client: AsyncClient, auth_headers, test_conv):
    # Running an agent on an empty conversation should just work and have 0 recent messages in context
    # We test this by making a request to the agent run endpoint and checking the response.
    # Since our fake model returns standard response, we just ensure it doesn't fail.
    
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Hello!", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "final_answer" in data
    assert data["final_answer"]

@pytest.mark.asyncio
async def test_2_recent_messages_and_3_chronological_ordering(uow: UnitOfWork, track6_user, test_conv):
    # Test retrieving recent messages
    async with uow:
        service = ConversationService(uow)
        
        # Add 3 messages
        await service.add_message(test_conv.id, track6_user.id, {"role": "user", "content": "msg 1"})
        await service.add_message(test_conv.id, track6_user.id, {"role": "assistant", "content": "msg 2"})
        await service.add_message(test_conv.id, track6_user.id, {"role": "user", "content": "msg 3"})
        await uow.commit()
        
    async with uow:
        service = ConversationService(uow)
        recent = await service.get_recent_messages(test_conv.id, track6_user.id, limit=10)
        
        assert len(recent) == 3
        # Ensure chronological ordering oldest to newest
        assert recent[0].content == "msg 1"
        assert recent[1].content == "msg 2"
        assert recent[2].content == "msg 3"

@pytest.mark.asyncio
async def test_4_bounded_message_retrieval(uow: UnitOfWork, track6_user, test_conv):
    # Add 15 messages
    async with uow:
        service = ConversationService(uow)
        for i in range(15):
            await service.add_message(test_conv.id, track6_user.id, {"role": "user", "content": f"msg {i}"})
        await uow.commit()
        
    async with uow:
        service = ConversationService(uow)
        recent = await service.get_recent_messages(test_conv.id, track6_user.id, limit=10)
        
        # Should only return 10 messages (bounded)
        assert len(recent) == 10
        # And it should be the MOST RECENT 10 messages (msg 5 to msg 14), in chronological order
        assert recent[0].content == "msg 5"
        assert recent[-1].content == "msg 14"

@pytest.mark.asyncio
async def test_5_ownership_isolation(async_client: AsyncClient, other_auth_headers, test_conv):
    # Try to run agent on someone else's conversation
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Hello!", "conversation_id": test_conv.id},
        headers=other_auth_headers
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_6_non_existent_conversation(async_client: AsyncClient, auth_headers):
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Hello!", "conversation_id": "invalid-id"},
        headers=auth_headers
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_7_context_engine_integration_and_8_token_bound():
    # Directly test ContextEngine + ContextAssemblyPipeline to ensure recent_messages are assembled correctly
    from app.core.context_engine.engine import ContextEngine
    from app.core.context_engine.schemas import ContextCandidate
    
    engine = ContextEngine(model_context_limit=100) # tiny budget
    
    candidates = [
        ContextCandidate(id="sys", type="system", content="System instruction", priority=1, token_count=10),
        ContextCandidate(id="req", type="request", content="My request", priority=2, token_count=10)
    ]
    
    # 20 recent messages with high token count
    for i in range(20):
        candidates.append(
            ContextCandidate(
                id=f"msg_{i}", type="message", content=f"Long msg {i}", 
                priority=5, token_count=10, metadata={"sequence_number": i}
            )
        )
        
    package = engine.assemble_context(candidates)
    
    # Budget is 100. Sys + req = 20. Remaining 80 / 10 = 8 messages.
    # So it should bound the context and not blow up.
    assert len(package.recent_messages) <= 8
    
    # Ensure they maintain chronological sequence
    seqs = [m.metadata.get("sequence_number") for m in package.recent_messages]
    assert seqs == sorted(seqs), "Messages should be chronologically ordered"

@pytest.mark.asyncio
async def test_9_existing_chat_regression(async_client: AsyncClient, auth_headers, test_conv):
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Testing execution path", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # Verify the message was persisted
    messages_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{test_conv.id}/messages",
        headers=auth_headers
    )
    assert messages_res.status_code == 200
    msgs = messages_res.json()["items"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Testing execution path"
    assert msgs[1]["role"] == "assistant"
    
@pytest.mark.asyncio
async def test_10_sse_regression(async_client: AsyncClient, auth_headers, test_conv):
    # Streaming Request
    async with async_client.stream("POST", f"{settings.API_V1_STR}/agents/general_agent/stream", json={"message": "Testing stream", "conversation_id": test_conv.id}, headers=auth_headers) as response:
        assert response.status_code == 200
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)
                
        # Check event types
        event_types = [e["type"] for e in events]
        assert "session_created" in event_types
        assert "completed" in event_types
    
    # Check that streaming also persisted the user and assistant messages
    messages_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{test_conv.id}/messages",
        headers=auth_headers
    )
    msgs = messages_res.json()["items"]
    # If the previous test ran, there might be 4 messages, or 2 if run in isolation.
    # Let's just check the last two.
    assert msgs[-2]["role"] == "user"
    assert msgs[-2]["content"] == "Testing stream"
    assert msgs[-1]["role"] == "assistant"
