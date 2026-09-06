import pytest
import pytest_asyncio
import uuid
import json
from httpx import AsyncClient
from app.db.uow import UnitOfWork
from app.core.config import settings

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)

@pytest_asyncio.fixture
async def track6b_user(uow: UnitOfWork):
    # Setup test user
    user_id = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": user_id,
            "username": f"testuser_{user_id}",
            "password_hash": "hashed_pass",
            "role": "USER"
        })
        await uow.commit()
    return user

@pytest_asyncio.fixture
async def other_user(uow: UnitOfWork):
    user_id = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": user_id,
            "username": f"testuser_{user_id}",
            "password_hash": "hashed_pass",
            "role": "USER"
        })
        await uow.commit()
    return user

@pytest_asyncio.fixture
async def test_conv(uow: UnitOfWork, track6b_user):
    conv_id = str(uuid.uuid4())
    async with uow:
        conv = await uow.conversations.create({
            "id": conv_id,
            "user_id": track6b_user.id,
            "title": "Test Conv 6B"
        })
        await uow.commit()
    return conv

@pytest_asyncio.fixture
async def auth_headers(track6b_user):
    from app.core.security import create_access_token
    token = create_access_token({"sub": track6b_user.username, "role": track6b_user.role})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(autouse=True)
def setup_fake_model():
    from app.main import app
    from app.core.config import settings
    app.state.model_gateway.register_model_route(settings.DEFAULT_CHAT_MODEL, "fake")

@pytest.mark.asyncio
async def test_1_empty_conversation_no_summary(async_client: AsyncClient, auth_headers, test_conv, uow: UnitOfWork):
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Hello!", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    async with uow:
        summary = await uow.summaries.get_by_conversation_id(test_conv.id)
        assert summary is None

@pytest.mark.asyncio
async def test_2_short_conversation_no_summary(async_client: AsyncClient, auth_headers, test_conv, uow: UnitOfWork):
    # Add a few messages (below threshold of 10)
    async with uow:
        for i in range(5):
            await uow.messages.create({
                "conversation_id": test_conv.id,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "sequence_number": i + 1
            })
        await uow.commit()

    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "New message", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    async with uow:
        summary = await uow.summaries.get_by_conversation_id(test_conv.id)
        assert summary is None

@pytest.mark.asyncio
async def test_3_threshold_triggers_summary(async_client: AsyncClient, auth_headers, test_conv, uow: UnitOfWork):
    # Add messages above the threshold (threshold is 10 for eligible unsummarized messages + 10 recent = 20 messages)
    # The recent window is 10 messages. Oldest recent seq is 12 (if there are 21 messages before new request).
    async with uow:
        for i in range(21):
            await uow.messages.create({
                "conversation_id": test_conv.id,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i+1}",
                "sequence_number": i + 1
            })
        await uow.commit()

    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Trigger summary", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    async with uow:
        summary = await uow.summaries.get_by_conversation_id(test_conv.id)
        assert summary is not None
        assert summary.last_sequence_number == 11 # Oldest recent seq (12) - 1
        assert "Fake response for: Summarize the following" in summary.content

@pytest.mark.asyncio
async def test_4_ownership_isolation(async_client: AsyncClient, other_user, test_conv, uow: UnitOfWork):
    # Try to hit the conversation with another user's token
    from app.core.security import create_access_token
    token = create_access_token({"sub": other_user.username, "role": other_user.role})
    other_headers = {"Authorization": f"Bearer {token}"}
    
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Hack", "conversation_id": test_conv.id},
        headers=other_headers
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_5_reuse_existing_summary(async_client: AsyncClient, auth_headers, test_conv, uow: UnitOfWork):
    # Seed a summary
    async with uow:
        summary = await uow.summaries.create({
            "conversation_id": test_conv.id,
            "content": "Old summary",
            "last_sequence_number": 5
        })
        # Add some new messages, but less than threshold (e.g. 5 unsummarized + 10 recent = 15 total)
        for i in range(5, 20):
            await uow.messages.create({
                "conversation_id": test_conv.id,
                "role": "user",
                "content": f"New message {i}",
                "sequence_number": i + 1
            })
        await uow.commit()
        
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Check summary", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # Should not have regenerated because unsummarized is seq 6 to 11 (6 messages < 10 threshold)
    async with uow:
        summary = await uow.summaries.get_by_conversation_id(test_conv.id)
        assert summary.content == "Old summary"
        assert summary.last_sequence_number == 5

@pytest.mark.asyncio
async def test_6_update_existing_summary(async_client: AsyncClient, auth_headers, test_conv, uow: UnitOfWork):
    # Seed a summary
    async with uow:
        summary = await uow.summaries.create({
            "conversation_id": test_conv.id,
            "content": "Old summary",
            "last_sequence_number": 5
        })
        # Add new messages above threshold (e.g. 10 unsummarized + 10 recent = 20 total -> sequence up to 25)
        for i in range(5, 25):
            await uow.messages.create({
                "conversation_id": test_conv.id,
                "role": "user",
                "content": f"New message {i}",
                "sequence_number": i + 1
            })
        await uow.commit()
        
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Check summary update", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # Unsummarized is seq 6 to 16 (11 messages >= 10). Should update.
    async with uow:
        summary = await uow.summaries.get_by_conversation_id(test_conv.id)
        assert summary.last_sequence_number == 15
        assert "Fake response for: Summarize the following" in summary.content

@pytest.mark.asyncio
async def test_7_failed_summarization_preserves_summary(test_conv, uow: UnitOfWork):
    async with uow:
        summary = await uow.summaries.create({
            "conversation_id": test_conv.id,
            "content": "Valid Old Summary",
            "last_sequence_number": 5
        })
        for i in range(5, 25):
            await uow.messages.create({
                "conversation_id": test_conv.id,
                "role": "user",
                "content": f"New message {i}",
                "sequence_number": i + 1
            })
        await uow.commit()

    from app.core.model_gateway.gateway import ModelGateway
    gateway = ModelGateway()
    class FailingProvider:
        async def generate(self, req):
            raise Exception("Simulated Gateway Failure")
        async def stream(self, req):
            raise Exception("Simulated Gateway Failure")
    gateway.register_provider("failing", FailingProvider())
    gateway.register_model_route("fail-model", "failing")
    
    from app.core.config import settings
    original_model = settings.DEFAULT_CHAT_MODEL
    settings.DEFAULT_CHAT_MODEL = "fail-model"
    
    try:
        from app.services.summary import ConversationSummaryService
        service = ConversationSummaryService(uow, gateway)
        
        # Oldest recent seq is 16
        candidate = await service.get_summary_candidate(test_conv.id, test_conv.user_id, 16)
        
        assert candidate is not None
        assert candidate.type == "summary"
        assert candidate.content == "Valid Old Summary"
        
        async with uow:
            db_summary = await uow.summaries.get_by_conversation_id(test_conv.id)
            assert db_summary.content == "Valid Old Summary"
            assert db_summary.last_sequence_number == 5
    finally:
        settings.DEFAULT_CHAT_MODEL = original_model

@pytest.mark.asyncio
async def test_8_summary_candidate_token_budgeting(test_conv, uow: UnitOfWork):
    async with uow:
        summary = await uow.summaries.create({
            "conversation_id": test_conv.id,
            "content": "A very long summary " * 500,
            "last_sequence_number": 5
        })
        for i in range(5, 10):
            await uow.messages.create({
                "conversation_id": test_conv.id,
                "role": "user",
                "content": f"Recent msg {i}",
                "sequence_number": i + 1
            })
        await uow.commit()

    from app.services.summary import ConversationSummaryService
    from app.main import app
    service = ConversationSummaryService(uow, app.state.model_gateway)

    candidate = await service.get_summary_candidate(test_conv.id, test_conv.user_id, 6)
    
    assert candidate is not None
    assert type(candidate).__name__ == "ContextCandidate"
    assert candidate.type == "summary"

    from app.core.context_engine.engine import ContextEngine
    from app.core.context_engine.schemas import ContextCandidate
    from app.core.config import settings
    
    engine = ContextEngine(model_context_limit=100)

    recent_candidates = [
        ContextCandidate(id=str(i), type="message", content=f"Recent msg {i}", priority=5)
        for i in range(5, 10)
    ]
    all_candidates = [candidate] + recent_candidates

    package = engine.assemble_context(all_candidates)
    
    assert package.conversation_summary is None
    dropped_summary = any("summary" in event for event in package.truncation_events)
    assert dropped_summary

    gen_req = engine.convert_to_generation_request(package, settings.DEFAULT_CHAT_MODEL)
    for msg in gen_req.messages:
        assert "A very long summary" not in msg.content
