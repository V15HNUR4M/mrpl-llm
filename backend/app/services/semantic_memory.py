from typing import List, Optional, Dict, Any
from app.db.uow import UnitOfWork
from app.core.context_engine.schemas import ContextCandidate

class MemoryService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def _audit(self, user_id: str, action: str, memory_id: Optional[str] = None, result: str = "success", details: Optional[Dict] = None):
        try:
            await self.uow.audit.create({
                "user_id": user_id,
                "action": action,
                "resource_type": "memory",
                "resource_id": memory_id,
                "result": result,
                "metadata_": details or {}
            })
        except Exception:
            # Audit failure must not block operation
            pass

    async def create_memory(self, user_id: str, content: str, memory_type: str = "FACT") -> Any:
        """Creates a new semantic memory for a user."""
        memory = await self.uow.semantic_memories.create({
            "user_id": user_id,
            "content": content,
            "memory_type": memory_type,
            "is_active": True
        })
        await self._audit(user_id, "memory_created", memory.id, "success", {"memory_type": memory_type})
        await self.uow.commit()
        return memory

    async def get_memory(self, user_id: str, memory_id: str) -> Optional[Any]:
        """Retrieves a memory by ID, ensuring ownership."""
        memory = await self.uow.semantic_memories.get_by_id(memory_id)
        if memory:
            if memory.user_id == user_id:
                await self._audit(user_id, "memory_read", memory_id, "success")
                return memory
            else:
                # Unauthorized access attempt
                await self._audit(user_id, "memory_read", memory_id, "denied")
                # Important: commit the audit event even though operation failed
                await self.uow.commit()
        return None

    async def list_memories(self, user_id: str, limit: int = 50) -> List[Any]:
        """Lists active memories for a user."""
        memories = await self.uow.semantic_memories.list_active_by_user(user_id, limit=limit)
        await self._audit(user_id, "memory_listed", None, "success", {"count": len(memories)})
        await self.uow.commit()
        return memories

    async def update_memory(self, user_id: str, memory_id: str, updates: Dict[str, Any]) -> Optional[Any]:
        """Updates a memory, ensuring ownership."""
        memory = await self.get_memory(user_id, memory_id)
        if not memory:
            # get_memory already audits denied access if memory exists for another user
            return None
        
        # Prevent user_id reassignment
        if "user_id" in updates:
            del updates["user_id"]
            
        updated = await self.uow.semantic_memories.update(memory, updates)
        await self._audit(user_id, "memory_updated", memory_id, "success")
        await self.uow.commit()
        return updated

    async def deactivate_memory(self, user_id: str, memory_id: str) -> bool:
        """Soft deletes (deactivates) a memory, ensuring ownership."""
        memory = await self.get_memory(user_id, memory_id)
        if not memory:
            return False
            
        await self.uow.semantic_memories.update(memory, {"is_active": False})
        await self._audit(user_id, "memory_deactivated", memory_id, "success")
        await self.uow.commit()
        return True

    async def get_memory_candidates(self, user_id: str, limit: int = 50) -> List[ContextCandidate]:
        """
        Retrieves active semantic memories for a user and converts them to ContextCandidates.
        These are NOT automatically injected into the model context in Track 6C.
        """
        memories = await self.list_memories(user_id, limit=limit)
        candidates = []
        for mem in memories:
            candidates.append(ContextCandidate(
                id=mem.id,
                type="memory",
                content=mem.content,
                priority=3,
                metadata={"memory_type": mem.memory_type}
            ))
        return candidates

    async def retrieve_memories(self, user_id: str, query: str, limit: int = 5) -> List[ContextCandidate]:
        """
        Retrieves relevant active memories for a user based on a query.
        Baseline 6D implementation: Returns recent active memories bounded by limit,
        optionally prioritizing simple keyword matches (if any keywords match).
        """
        # Baseline deterministic retrieval without vector db
        all_memories = await self.list_memories(user_id, limit=50)
        
        query_words = set(query.lower().split())
        
        # Simple scoring: count of intersecting words
        scored_memories = []
        for mem in all_memories:
            mem_words = set(mem.content.lower().split())
            score = len(query_words.intersection(mem_words))
            scored_memories.append((score, mem))
            
        # Sort by score (desc), then fallback to existing deterministic order (updated_at desc)
        # Python's sort is stable, so we just sort by score
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        # Take top 'limit'
        top_memories = [m for _, m in scored_memories[:limit]]
        
        candidates = []
        for mem in top_memories:
            candidates.append(ContextCandidate(
                id=mem.id,
                type="memory",
                content=mem.content,
                priority=3,
                metadata={"memory_type": mem.memory_type}
            ))
            
        await self._audit(user_id, "memory_retrieved", None, "success", {"query": query, "count": len(candidates)})
        await self.uow.commit()
        return candidates
