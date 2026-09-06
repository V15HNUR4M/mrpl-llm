"""
Track 6G Acceptance Tests — Memory Authorization + Audit
"""

import pytest
import pytest_asyncio
import uuid

from app.db.uow import UnitOfWork
from app.services.semantic_memory import MemoryService
from app.services.memory_conflict import MemoryConflictService
from app.services.memory_extraction import MemoryExtractionService
from app.core.model_gateway.gateway import ModelGateway
from app.core.model_gateway.provider import ModelProvider
from app.core.model_gateway.schemas import (
    GenerationRequest, GenerationResponse, Usage,
    StreamingEvent, ModelInfo, ModelCapabilities, Message as GenMessage
)
import json
from typing import AsyncGenerator
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)


@pytest_asyncio.fixture
async def user_a(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"user_a_{uid}",
            "password_hash": "hashed",
            "role": "USER"
        })
        await uow.commit()
    return user


@pytest_asyncio.fixture
async def user_b(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"user_b_{uid}",
            "password_hash": "hashed",
            "role": "USER"
        })
        await uow.commit()
    return user

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_user_can_access_own_memory(uow: UnitOfWork, user_a):
    async with uow:
        svc = MemoryService(uow)
        mem = await svc.create_memory(user_a.id, "I like python")
        
        fetched = await svc.get_memory(user_a.id, mem.id)
        assert fetched is not None
        assert fetched.id == mem.id


@pytest.mark.asyncio
async def test_2_user_cannot_access_another_users_memory(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        mem_a = await svc.create_memory(user_a.id, "User A secret")
        mem_b = await svc.create_memory(user_b.id, "User B secret")

        # User B tries to read User A's memory
        fetched = await svc.get_memory(user_b.id, mem_a.id)
        assert fetched is None  # Denied, acts as 404


@pytest.mark.asyncio
async def test_3_user_cannot_update_another_users_memory(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        mem_a = await svc.create_memory(user_a.id, "User A secret")

        # User B tries to update User A's memory
        updated = await svc.update_memory(user_b.id, mem_a.id, {"content": "Hacked"})
        assert updated is None

        # Verify unchanged
        check = await uow.semantic_memories.get_by_id(mem_a.id)
        assert check.content == "User A secret"


@pytest.mark.asyncio
async def test_4_user_cannot_deactivate_another_users_memory(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        mem_a = await svc.create_memory(user_a.id, "User A secret")

        # User B tries to deactivate User A's memory
        success = await svc.deactivate_memory(user_b.id, mem_a.id)
        assert success is False

        # Verify unchanged
        check = await uow.semantic_memories.get_by_id(mem_a.id)
        assert check.is_active is True


@pytest.mark.asyncio
async def test_5_retrieval_is_user_scoped(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        await svc.create_memory(user_a.id, "User likes Python")
        await svc.create_memory(user_b.id, "User likes Java")

        retrieved = await svc.retrieve_memories(user_a.id, "User likes")
        assert len(retrieved) == 1
        assert "Python" in retrieved[0].content


@pytest.mark.asyncio
async def test_6_context_candidates_are_user_scoped(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        await svc.create_memory(user_a.id, "User likes Python")
        await svc.create_memory(user_b.id, "User likes Java")

        candidates = await svc.get_memory_candidates(user_a.id)
        assert len(candidates) == 1
        assert "Python" in candidates[0].content


@pytest.mark.asyncio
async def test_7_conflict_resolution_is_user_scoped(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        mem_b = await svc.create_memory(user_b.id, "User lives in Chennai.")
        mem_a = await svc.create_memory(user_a.id, "User now lives in Bengaluru.")
        
        conflict_svc = MemoryConflictService(uow)
        # Conflict runs for User A, should NOT see User B's memory
        result = await conflict_svc.detect_and_resolve(user_a.id, mem_a)
        assert len(result.superseded_memory_ids) == 0
        
        # User B's memory remains active
        check = await uow.semantic_memories.get_by_id(mem_b.id)
        assert check.is_active is True


@pytest.mark.asyncio
async def test_8_extraction_uses_authenticated_identity(uow: UnitOfWork, user_a, user_b):
    class JsonProvider(ModelProvider):
        def __init__(self, resp): self._resp = resp
        async def generate(self, req: GenerationRequest) -> GenerationResponse:
            return GenerationResponse(text=self._resp, model=req.model, finish_reason="stop", usage=Usage(input_tokens=5, output_tokens=5, total_tokens=10))
        async def stream(self, req: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]: yield StreamingEvent(type="completed")
        async def health(self) -> bool: return True
        async def get_model_info(self, model_id: str) -> ModelInfo: return ModelInfo(model_id=model_id, provider="json", capabilities=ModelCapabilities(text_generation=True), context_window=8192)
        async def list_models(self): return []

    # The LLM attempts to output a different user ID, but extraction ignores it
    # because the user_id parameter passed from HTTP determines persistence.
    extraction_json = json.dumps([
        {"content": "Extracted fact", "memory_type": "FACT", "confidence": 0.9, "user_id": user_b.id}
    ])
    gw = ModelGateway()
    gw.register_provider("json", JsonProvider(extraction_json))
    gw.register_model_route("test-model", "json")

    async with uow:
        svc = MemoryExtractionService(uow, gw)
        persisted = await svc.extract_from_messages(user_a.id, [GenMessage(role="user", content="I am a test")], model_id="test-model")
        
        # Must be persisted under user_a.id despite LLM payload
        assert len(persisted) == 1
        assert persisted[0].user_id == user_a.id


@pytest.mark.asyncio
async def test_9_memory_creation_is_attributed_correctly(uow: UnitOfWork, user_a):
    async with uow:
        svc = MemoryService(uow)
        mem = await svc.create_memory(user_a.id, "Fact")
        assert mem.user_id == user_a.id


@pytest.mark.asyncio
async def test_10_audit_event_generated(uow: UnitOfWork, user_a):
    async with uow:
        svc = MemoryService(uow)
        mem = await svc.create_memory(user_a.id, "Fact to audit")
        
        # Verify audit event
        audits = await uow.session.execute(
            text("SELECT action, result, resource_id FROM audit_events WHERE resource_type = 'memory' AND user_id = :uid"), 
            {"uid": user_a.id}
        )
        records = audits.fetchall()
        assert len(records) >= 1
        assert any(r.action == "memory_created" and r.result == "success" and r.resource_id == mem.id for r in records)


@pytest.mark.asyncio
async def test_11_unauthorized_operation_does_not_mutate_state(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        mem_a = await svc.create_memory(user_a.id, "Fact")

        await svc.update_memory(user_b.id, mem_a.id, {"content": "New content"})
        await svc.deactivate_memory(user_b.id, mem_a.id)

        # Ensure no changes
        check = await uow.semantic_memories.get_by_id(mem_a.id)
        assert check.content == "Fact"
        assert check.is_active is True


@pytest.mark.asyncio
async def test_12_audit_does_not_expose_full_memory_content_unnecessarily(uow: UnitOfWork, user_a):
    async with uow:
        svc = MemoryService(uow)
        mem = await svc.create_memory(user_a.id, "Super secret private content")
        
        audits = await uow.session.execute(
            text("SELECT metadata FROM audit_events WHERE resource_type = 'memory' AND resource_id = :mid"), 
            {"mid": mem.id}
        )
        records = audits.fetchall()
        for r in records:
            # metadata JSON should not contain the super secret content
            metadata_str = str(r.metadata)
            assert "Super secret private content" not in metadata_str


@pytest.mark.asyncio
async def test_13_user_isolation_under_multiple_memories(uow: UnitOfWork, user_a, user_b):
    async with uow:
        svc = MemoryService(uow)
        for i in range(5):
            await svc.create_memory(user_a.id, f"A fact {i}")
            await svc.create_memory(user_b.id, f"B fact {i}")

        a_mems = await svc.list_memories(user_a.id)
        assert len(a_mems) == 5
        assert all(m.user_id == user_a.id for m in a_mems)


@pytest.mark.asyncio
async def test_21_important_security_test(uow: UnitOfWork, user_a, user_b):
    """
    Mandatory Acceptance Scenario from prompt:
    User A creates Memory X.
    User B attempts GET X, UPDATE X, DEACTIVATE X.
    Expected: ALL DENIED. Memory unchanged, is_active=True, user_id=A.
    """
    async with uow:
        svc = MemoryService(uow)
        mem_x = await svc.create_memory(user_a.id, "User lives in Chennai")

        # User B attempts operations
        get_res = await svc.get_memory(user_b.id, mem_x.id)
        assert get_res is None

        up_res = await svc.update_memory(user_b.id, mem_x.id, {"content": "Hacked"})
        assert up_res is None

        deact_res = await svc.deactivate_memory(user_b.id, mem_x.id)
        assert deact_res is False

        # Memory unchanged
        check = await uow.semantic_memories.get_by_id(mem_x.id)
        assert check.user_id == user_a.id
        assert check.is_active is True
        assert check.content == "User lives in Chennai"
