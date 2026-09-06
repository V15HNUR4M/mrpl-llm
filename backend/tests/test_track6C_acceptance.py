import pytest
import pytest_asyncio
import uuid
from app.db.uow import UnitOfWork

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)

@pytest_asyncio.fixture
async def track6c_user(uow: UnitOfWork):
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

@pytest.mark.asyncio
async def test_1_memory_creation_and_persistence(uow: UnitOfWork, track6c_user):
    from app.services.semantic_memory import MemoryService
    service = MemoryService(uow)
    
    async with uow:
        mem = await service.create_memory(track6c_user.id, "User prefers Python", "PREFERENCE")
        assert mem is not None
        assert mem.id is not None
        assert mem.user_id == track6c_user.id
        assert mem.content == "User prefers Python"
        assert mem.memory_type == "PREFERENCE"
        assert mem.is_active is True
        
        # Verify persistence
        db_mem = await service.get_memory(track6c_user.id, mem.id)
        assert db_mem is not None
        assert db_mem.content == "User prefers Python"

@pytest.mark.asyncio
async def test_2_user_ownership_isolation(uow: UnitOfWork, track6c_user, other_user):
    from app.services.semantic_memory import MemoryService
    service = MemoryService(uow)
    
    async with uow:
        mem = await service.create_memory(track6c_user.id, "Secret project A", "FACT")
        
        # Track 6c user can access
        assert await service.get_memory(track6c_user.id, mem.id) is not None
        
        # Other user cannot access
        assert await service.get_memory(other_user.id, mem.id) is None
        
        # Other user cannot list
        other_mems = await service.list_memories(other_user.id)
        assert len(other_mems) == 0
        
        # Other user cannot update
        updated = await service.update_memory(other_user.id, mem.id, {"content": "Hacked"})
        assert updated is None
        
        # Other user cannot deactivate
        deactivated = await service.deactivate_memory(other_user.id, mem.id)
        assert deactivated is False

@pytest.mark.asyncio
async def test_3_update_and_deactivation(uow: UnitOfWork, track6c_user):
    from app.services.semantic_memory import MemoryService
    service = MemoryService(uow)
    
    async with uow:
        mem = await service.create_memory(track6c_user.id, "Fact 1", "FACT")
        
        # Update
        updated = await service.update_memory(track6c_user.id, mem.id, {"content": "Fact 1 updated"})
        assert updated.content == "Fact 1 updated"
        
        # Deactivate
        deactivated = await service.deactivate_memory(track6c_user.id, mem.id)
        assert deactivated is True
        
        # Deactivated memory is not listed
        active_mems = await service.list_memories(track6c_user.id)
        assert len(active_mems) == 0
        
        # Deactivated memory is not returned as candidate
        candidates = await service.get_memory_candidates(track6c_user.id)
        assert len(candidates) == 0
        
        # It still exists in db though
        db_mem = await service.get_memory(track6c_user.id, mem.id)
        assert db_mem is not None
        assert db_mem.is_active is False

@pytest.mark.asyncio
async def test_4_multiple_memories_and_ordering(uow: UnitOfWork, track6c_user):
    from app.services.semantic_memory import MemoryService
    service = MemoryService(uow)
    
    async with uow:
        # Create multiple memories
        for i in range(5):
            await service.create_memory(track6c_user.id, f"Memory {i}", "FACT")
            
        mems = await service.list_memories(track6c_user.id)
        assert len(mems) == 5
        
        # Update memory 2 to change order (updated_at desc)
        await service.update_memory(track6c_user.id, mems[2].id, {"content": "Memory 2 updated"})
        
        mems_after = await service.list_memories(track6c_user.id)
        assert mems_after[0].id == mems[2].id # Now the most recently updated is first

@pytest.mark.asyncio
async def test_5_conversion_to_context_candidate(uow: UnitOfWork, track6c_user):
    from app.services.semantic_memory import MemoryService
    service = MemoryService(uow)
    
    async with uow:
        await service.create_memory(track6c_user.id, "Candidate info", "FACT")
        
        candidates = await service.get_memory_candidates(track6c_user.id)
        assert len(candidates) == 1
        
        candidate = candidates[0]
        assert type(candidate).__name__ == "ContextCandidate"
        assert candidate.type == "memory"
        assert candidate.content == "Candidate info"
        assert candidate.priority == 3
        assert candidate.metadata.get("memory_type") == "FACT"

@pytest.mark.asyncio
async def test_6_separation_from_conversations(uow: UnitOfWork, track6c_user):
    # Semantic memory should be distinct from conversation summaries/messages
    from app.services.semantic_memory import MemoryService
    service = MemoryService(uow)
    
    async with uow:
        mem = await service.create_memory(track6c_user.id, "Independent semantic fact", "FACT")
        assert mem is not None
        
        # Verify it's independent - not tied to any conversation_id
        # Our Memory model intentionally lacks conversation_id to keep it purely user-level
        assert not hasattr(mem, "conversation_id")
