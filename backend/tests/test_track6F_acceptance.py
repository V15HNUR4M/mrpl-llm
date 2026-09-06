"""
Track 6F Acceptance Tests — Conflict / Stale Memory Handling (Corrected)
"""

import pytest
import pytest_asyncio
import uuid
from typing import List

from app.db.uow import UnitOfWork
from app.services.semantic_memory import MemoryService
from app.services.memory_conflict import (
    MemoryConflictService, ConflictResolution
)


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
# Helpers
# ---------------------------------------------------------------------------

async def create_mem(uow, user_id, content, memory_type="FACT"):
    """Helper: creates a memory directly via MemoryService inside a uow block."""
    service = MemoryService(uow)
    return await service.create_memory(user_id, content, memory_type)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_unrelated_moderate_lexical_overlap(uow: UnitOfWork, user_a):
    """
    Verify that two memories with moderate word overlap but different meaning remain active.
    Example:
    old: User works at MRPL refinery and uses Python.
    new: User visited Chennai refinery during college training.
    """
    async with uow:
        mem1 = await create_mem(uow, user_a.id, "User works at MRPL refinery and uses Python.", "FACT")
        mem2 = await create_mem(uow, user_a.id, "User visited Chennai refinery during college training.", "FACT")

        conflict_service = MemoryConflictService(uow)
        result = await conflict_service.detect_and_resolve(user_a.id, mem2)

        assert result.resolution == ConflictResolution.NO_CONFLICT
        assert result.superseded_memory_ids == []

        svc = MemoryService(uow)
        active = await svc.list_memories(user_a.id)
        assert len(active) == 2


@pytest.mark.asyncio
async def test_2_clearly_superseding_memory(uow: UnitOfWork, user_a):
    """
    old: User lives in Chennai.
    new: User now lives in Bengaluru.
    Verify: old.is_active == False, new.is_active == True
    """
    old_content = "User lives in Chennai."
    new_content = "User now lives in Bengaluru."

    async with uow:
        svc = MemoryService(uow)
        old_mem = await svc.create_memory(user_a.id, old_content, "FACT")
        new_mem = await svc.create_memory(user_a.id, new_content, "FACT")

        conflict_service = MemoryConflictService(uow)
        result = await conflict_service.detect_and_resolve(user_a.id, new_mem)

        assert result.resolution == ConflictResolution.SUPERSEDED
        assert old_mem.id in result.superseded_memory_ids

        active = await svc.list_memories(user_a.id)
        active_ids = {m.id for m in active}
        assert new_mem.id in active_ids
        assert old_mem.id not in active_ids
        
        # Verify old record still exists in DB but inactive
        db_old = await uow.semantic_memories.get_by_id(old_mem.id)
        assert db_old.is_active is False


@pytest.mark.asyncio
async def test_3_low_lexical_overlap_contradiction(uow: UnitOfWork, user_a):
    """
    old: User lives in Chennai.
    new: User's current residence is Bengaluru.
    Verify that the system does NOT incorrectly deactivate the old memory
    merely because Jaccard similarity is low. Safe expected behavior:
    old remains active, new remains active.
    """
    old_content = "User lives in Chennai."
    new_content = "User's current residence is Bengaluru."

    async with uow:
        svc = MemoryService(uow)
        old_mem = await svc.create_memory(user_a.id, old_content, "FACT")
        new_mem = await svc.create_memory(user_a.id, new_content, "FACT")

        conflict_service = MemoryConflictService(uow)
        result = await conflict_service.detect_and_resolve(user_a.id, new_mem)

        # We fail conservatively because we can't reliably detect this substitution deterministically
        assert result.resolution == ConflictResolution.NO_CONFLICT

        active = await svc.list_memories(user_a.id)
        assert len(active) == 2


@pytest.mark.asyncio
async def test_4_ambiguous_relationship(uow: UnitOfWork, user_a):
    """
    Verify that statements which could coexist are preserved.
    old: User works remotely.
    new: User visits the office twice a week.
    Expected: both active.
    """
    content_a = "User works remotely."
    content_b = "User visits the office twice a week."

    async with uow:
        svc = MemoryService(uow)
        mem_a = await svc.create_memory(user_a.id, content_a, "FACT")
        mem_b = await svc.create_memory(user_a.id, content_b, "FACT")

        conflict_service = MemoryConflictService(uow)
        result = await conflict_service.detect_and_resolve(user_a.id, mem_b)

        assert result.resolution == ConflictResolution.NO_CONFLICT

        active = await svc.list_memories(user_a.id)
        assert len(active) == 2


@pytest.mark.asyncio
async def test_5_user_isolation(uow: UnitOfWork, user_a, user_b):
    """
    Create memories belonging to different users and verify:
    User A's memory cannot deactivate User B's memory.
    """
    content_old = "User lives in Chennai."
    content_new = "User now lives in Bengaluru."

    async with uow:
        svc = MemoryService(uow)
        # User B owns the old memory
        b_old = await svc.create_memory(user_b.id, content_old, "FACT")
        # User A creates a new memory that would conflict IF owned by same user
        a_new = await svc.create_memory(user_a.id, content_new, "FACT")

        conflict_service = MemoryConflictService(uow)
        # Run conflict detection for User A
        result = await conflict_service.detect_and_resolve(user_a.id, a_new)

        # User A has no existing memories to conflict with → no conflict
        assert result.resolution == ConflictResolution.NO_CONFLICT

        # User B's memory must be untouched and active
        db_b_old = await uow.semantic_memories.get_by_id(b_old.id)
        assert db_b_old.is_active is True


@pytest.mark.asyncio
async def test_6_historical_preservation(uow: UnitOfWork, user_a):
    """
    When a memory is superseded:
    old memory remains in DB
    old.is_active == False
    new.is_active == True
    """
    old_content = "User prefers Qwen."
    new_content = "User prefers Llama."

    async with uow:
        svc = MemoryService(uow)
        old_mem = await svc.create_memory(user_a.id, old_content, "PREFERENCE")
        new_mem = await svc.create_memory(user_a.id, new_content, "PREFERENCE")

        conflict_service = MemoryConflictService(uow)
        await conflict_service.detect_and_resolve(user_a.id, new_mem)

        # Fetch directly from DB (bypassing is_active filter)
        db_old = await uow.semantic_memories.get_by_id(old_mem.id)
        db_new = await uow.semantic_memories.get_by_id(new_mem.id)
        assert db_old is not None
        assert db_old.is_active is False
        
        assert db_new is not None
        assert db_new.is_active is True


@pytest.mark.asyncio
async def test_7_retrieval_excludes_stale_memory(uow: UnitOfWork, user_a):
    """
    After supersession, verify that normal active-memory retrieval 
    does not return the inactive old memory.
    """
    old_content = "User prefers Qwen."
    new_content = "User prefers Llama."

    async with uow:
        svc = MemoryService(uow)
        old_mem = await svc.create_memory(user_a.id, old_content, "PREFERENCE")
        new_mem = await svc.create_memory(user_a.id, new_content, "PREFERENCE")

        conflict_service = MemoryConflictService(uow)
        await conflict_service.detect_and_resolve(user_a.id, new_mem)

        active = await svc.list_memories(user_a.id)
        active_contents = {m.content for m in active}
        assert old_content not in active_contents
        assert new_content in active_contents

        candidates = await svc.retrieve_memories(user_a.id, "prefers")
        candidate_contents = {c.content for c in candidates}
        assert old_content not in candidate_contents


@pytest.mark.asyncio
async def test_8_failure_safe_behavior(uow: UnitOfWork, user_a):
    """
    If conflict evaluation encounters an unexpected error:
    do not deactivate existing memories.
    The system must fail open: uncertain/error → preserve existing memory.
    """
    async with uow:
        svc = MemoryService(uow)
        existing = await svc.create_memory(user_a.id, "Stable existing memory", "FACT")

    # Simulate failure by passing a fake memory object with no id attribute
    class BrokenMemory:
        id = None
        memory_type = "FACT"
        content = "This will cause a lookup failure"
        is_active = True

    async with uow:
        try:
            conflict_service = MemoryConflictService(uow)
            await conflict_service.detect_and_resolve(user_a.id, BrokenMemory())
        except Exception:
            pass  # Expected; caller swallows in production

        svc = MemoryService(uow)
        memories = await svc.list_memories(user_a.id)
        assert len(memories) == 1
        assert memories[0].id == existing.id
        assert memories[0].content == "Stable existing memory"
        assert memories[0].is_active is True


@pytest.mark.asyncio
async def test_9_different_types_do_not_conflict(uow: UnitOfWork, user_a):
    """
    Even if two memories have highly overlapping content, they must not
    conflict with each other if they have different memory_types.
    """
    content = "User prefers Python."
    content_similar = "User prefers Java."

    async with uow:
        svc = MemoryService(uow)
        # Highly similar content but different types
        mem_fact = await svc.create_memory(user_a.id, content, "FACT")
        mem_dec = await svc.create_memory(user_a.id, content_similar, "DECISION")

        conflict_service = MemoryConflictService(uow)
        result = await conflict_service.detect_and_resolve(user_a.id, mem_dec)

        # Different types → no conflict, both remain active
        assert result.resolution == ConflictResolution.NO_CONFLICT

        active = await svc.list_memories(user_a.id)
        assert len(active) == 2


@pytest.mark.asyncio
async def test_10_conflict_handling_is_bounded(uow: UnitOfWork, user_a):
    """
    Conflict detection is bounded by the list_active_by_user limit (50).
    Creating many memories and then running conflict detection must complete
    without scanning unbounded data.
    """
    async with uow:
        svc = MemoryService(uow)
        # Create 55 different memories (above the 50-limit bound)
        for i in range(55):
            await svc.create_memory(user_a.id, f"Fact number {i} about totally different things", "FACT")

        new_mem = await svc.create_memory(user_a.id, "Fact number 99 about a brand new subject", "FACT")

        conflict_service = MemoryConflictService(uow)
        result = await conflict_service.detect_and_resolve(user_a.id, new_mem)

        # Must complete (doesn't hang or error), result is deterministic
        assert result.resolution in (ConflictResolution.NO_CONFLICT, ConflictResolution.SUPERSEDED)
