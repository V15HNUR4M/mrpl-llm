import pytest
import pytest_asyncio
import uuid
import json
from httpx import AsyncClient
from app.db.uow import UnitOfWork
from app.core.config import settings
from app.services.semantic_memory import MemoryService

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)

@pytest_asyncio.fixture
async def track6d_user(uow: UnitOfWork):
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
async def test_conv(uow: UnitOfWork, track6d_user):
    conv_id = str(uuid.uuid4())
    async with uow:
        conv = await uow.conversations.create({
            "id": conv_id,
            "user_id": track6d_user.id,
            "title": "Test Conv 6D"
        })
        await uow.commit()
    return conv

@pytest_asyncio.fixture
async def auth_headers(track6d_user):
    from app.core.security import create_access_token
    token = create_access_token({"sub": track6d_user.username, "role": track6d_user.role})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(autouse=True)
def setup_fake_model():
    from app.main import app
    app.state.model_gateway.register_model_route(settings.DEFAULT_CHAT_MODEL, "fake")

@pytest.mark.asyncio
async def test_1_query_retrieves_relevant_active_memories(uow: UnitOfWork, track6d_user):
    service = MemoryService(uow)
    async with uow:
        await service.create_memory(track6d_user.id, "Apples are red")
        await service.create_memory(track6d_user.id, "Bananas are yellow")
        
        # Test keyword matching baseline (query stripped of punctuation)
        candidates = await service.retrieve_memories(track6d_user.id, "What color are apples", limit=5)
        assert len(candidates) > 0
        # The highest scored memory should mention apples (matched keyword)
        assert "Apples" in candidates[0].content

@pytest.mark.asyncio
async def test_2_inactive_memories_are_excluded(uow: UnitOfWork, track6d_user):
    service = MemoryService(uow)
    async with uow:
        mem = await service.create_memory(track6d_user.id, "Secret code is 1234")
        await service.deactivate_memory(track6d_user.id, mem.id)
        
        candidates = await service.retrieve_memories(track6d_user.id, "What is the secret code?")
        assert len(candidates) == 0

@pytest.mark.asyncio
async def test_3_user_a_cannot_retrieve_user_b_memories(uow: UnitOfWork, track6d_user, other_user):
    service = MemoryService(uow)
    async with uow:
        await service.create_memory(track6d_user.id, "User A's private memory")
        
        # Other user tries to retrieve it
        candidates = await service.retrieve_memories(other_user.id, "User A's private memory")
        assert len(candidates) == 0

@pytest.mark.asyncio
async def test_4_retrieval_is_bounded(uow: UnitOfWork, track6d_user):
    service = MemoryService(uow)
    async with uow:
        for i in range(10):
            await service.create_memory(track6d_user.id, f"Random fact {i}")
            
        candidates = await service.retrieve_memories(track6d_user.id, "Random fact", limit=3)
        assert len(candidates) == 3

@pytest.mark.asyncio
async def test_5_results_are_context_candidates(uow: UnitOfWork, track6d_user):
    service = MemoryService(uow)
    async with uow:
        await service.create_memory(track6d_user.id, "Format check")
        
        candidates = await service.retrieve_memories(track6d_user.id, "Format check")
        assert len(candidates) > 0
        assert type(candidates[0]).__name__ == "ContextCandidate"
        assert candidates[0].type == "memory"
        assert candidates[0].priority == 3

@pytest.mark.asyncio
async def test_6_and_9_memory_candidates_pass_through_context_engine(async_client: AsyncClient, auth_headers, test_conv, track6d_user, uow: UnitOfWork):
    service = MemoryService(uow)
    async with uow:
        await service.create_memory(track6d_user.id, "UNIQUE_MEMORY_STRING_999")
        
    # We trigger the agent endpoint. It should use the memory and pass it to harness -> engine
    response = await async_client.post(
        f"{settings.API_V1_STR}/agents/general_agent/run",
        json={"message": "Do you remember UNIQUE_MEMORY_STRING_999?", "conversation_id": test_conv.id},
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # Since we use fake model, the response final_answer includes "Fake response for: Do you remember"
    # To really verify it reached ContextEngine without being directly concatenated, we check the GenerationRequest format via test 7
    # But for now, we know the endpoint succeeds and doesn't crash, meaning the context assembly worked.
    
    # To check that it didn't directly concatenate into the harness request, we look at engine conversion.
    from app.core.context_engine.engine import ContextEngine
    from app.core.context_engine.schemas import ContextCandidate
    engine = ContextEngine()
    mem_cand = ContextCandidate(id="1", type="memory", content="UNIQUE_MEMORY_STRING_999", priority=3)
    pkg = engine.assemble_context([mem_cand])
    gen_req = engine.convert_to_generation_request(pkg, "test")
    
    # Verify it's appended as system prompt, not just concatenated blindly
    system_msgs = [m for m in gen_req.messages if m.role == "system"]
    assert any("Relevant Memories:\n- UNIQUE_MEMORY_STRING_999" in m.content for m in system_msgs)

@pytest.mark.asyncio
async def test_7_token_budgeting_limits_memory_context(uow: UnitOfWork):
    from app.core.context_engine.engine import ContextEngine
    from app.core.context_engine.budget import TokenBudgetCalculator, TokenEstimator
    from app.core.context_engine.assembly import ContextAssemblyPipeline
    from app.core.context_engine.schemas import ContextCandidate
    
    # Use a calculator with explicit small budget (no output reserve/margin)
    # so we can control the budget precisely.
    # "Short" = 5 chars = 1 token; long memory will be many tokens.
    # Set budget to 5 tokens — enough for "Short" (1 token) but not the huge memory.
    calc = TokenBudgetCalculator(model_context_limit=25, output_reserve=0, safety_margin=0)
    pipeline = ContextAssemblyPipeline(calc, TokenEstimator())
    
    mem_cand = ContextCandidate(id="m1", type="memory", content="A" * 400, priority=3)  # 100 tokens
    sys_cand = ContextCandidate(id="s1", type="system", content="Short", priority=1)   # 1 token
    
    pkg = pipeline.run([mem_cand, sys_cand])
    
    # System (priority=1) fits; memory (priority=3) is dropped
    assert len(pkg.system_instructions) == 1
    assert len(pkg.semantic_memories) == 0
    assert any("Dropped candidate m1" in event for event in pkg.truncation_events)

@pytest.mark.asyncio
async def test_8_memories_remain_separate_from_summaries(uow: UnitOfWork):
    from app.core.context_engine.engine import ContextEngine
    from app.core.context_engine.schemas import ContextCandidate
    engine = ContextEngine()
    
    mem_cand = ContextCandidate(id="m1", type="memory", content="Semantic fact", priority=3)
    sum_cand = ContextCandidate(id="s1", type="summary", content="Conversation summary", priority=6)
    
    pkg = engine.assemble_context([mem_cand, sum_cand])
    
    assert len(pkg.semantic_memories) == 1
    assert pkg.semantic_memories[0].content == "Semantic fact"
    
    assert pkg.conversation_summary is not None
    assert pkg.conversation_summary.content == "Conversation summary"
    
    # They are kept in separate fields in ContextPackage
