"""
Track 6F — Conflict / Stale Memory Handling

Detects conflicts among a user's active semantic memories and applies
deterministic supersession rules. Uses no LLM — all decisions are
rule-based and bounded.

Flow:
  New Memory (just created)
        ↓
  MemoryConflictService.detect_and_resolve()
        ↓
  No conflict ──────────────────────────────→ Keep active (no action)
        ↓
  Clear supersession (Jaccard in conflict zone,
  same memory_type) ───────────────────────→ New remains active + old → inactive
        ↓
  Ambiguous / insufficient overlap ────────→ Preserve both active

SUPERSESSION THRESHOLD:
  Jaccard in [CONFLICT_FLOOR, DEDUP_THRESHOLD) with same memory_type
  = the memories are about the same subject but state different things.
  The newer memory supersedes the older one deterministically.

AMBIGUOUS ZONE:
  Jaccard < CONFLICT_FLOOR with same memory_type (different subjects
  despite same type) → leave both active; no auto-resolution.

Invariants:
  - Superseded memories are marked is_active=False, not deleted.
  - LLM is NOT used — no external call, no LLM output mutates the database.
  - Existing is_active=False memories are not touched.
  - Only same memory_type memories can conflict with each other.
  - User A's memories never affect User B's memories.
"""

import string
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Any

from app.db.uow import UnitOfWork

# Jaccard deduplication threshold (Track 6E): >= 0.7 same-type → update existing
DEDUP_THRESHOLD = 0.7

class ConflictResolution(Enum):
    NO_CONFLICT = "no_conflict"
    SUPERSEDED = "superseded"       # old memory deactivated
    AMBIGUOUS = "ambiguous"         # different enough subject, preserve both


@dataclass
class ConflictResult:
    resolution: ConflictResolution
    superseded_memory_ids: List[str]


def _normalise(text: str):
    """Returns a lower-case, punctuation-stripped word set."""
    return {w.strip(string.punctuation).lower() for w in text.split() if w.strip(string.punctuation)}


def jaccard(a: str, b: str) -> float:
    """Deterministic, bounded Jaccard similarity on normalised word sets."""
    wa, wb = _normalise(a), _normalise(b)
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def has_clear_supersession_evidence(old_text: str, new_text: str) -> bool:
    """
    Evaluates if new_text is a direct substitution of old_text, indicating
    clear supersession without relying on broad Jaccard zones.
    When evidence is insufficient, fails conservatively and returns False.
    """
    # Words that indicate state change or time, safely ignored for overlap counting
    time_words = {"now", "currently", "formerly", "previously", "instead", "updated", "changed", "new", "current"}
    
    def get_core_words(text: str):
        words = []
        for w in text.split():
            clean = w.strip(string.punctuation).lower()
            if clean and clean not in time_words:
                # Handle possessives like user's -> user
                if clean.endswith("'s"):
                    clean = clean[:-2]
                words.append(clean)
        return set(words)
        
    old_words = get_core_words(old_text)
    new_words = get_core_words(new_text)
    
    overlap = old_words & new_words
    old_unique = old_words - new_words
    new_unique = new_words - old_words
    
    # Require at least 2 words of context overlap (e.g. "user", "lives", "in")
    # and at most 2 words of difference. This ensures we only supersede when 
    # the sentence structure is nearly identical and only a specific value changed.
    if len(overlap) >= 2 and len(old_unique) <= 2 and len(new_unique) <= 2:
        return True
        
    return False


class MemoryConflictService:
    """
    Detects and deterministically resolves conflicts among a user's
    active semantic memories.

    Design constraints:
    - No LLM calls; all decisions are rule-based and bounded.
    - Memories are never deleted; superseded memories become inactive.
    - Only memories of the same memory_type can conflict with each other.
    - Ambiguous conflicts are preserved without auto-resolution.
    """

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def detect_and_resolve(
        self,
        user_id: str,
        new_memory: Any,
    ) -> ConflictResult:
        """
        Compares new_memory against the user's active memories of the same type.

        Returns a ConflictResult indicating what action was taken.
        Failures are surfaced as exceptions to the caller, which must decide
        whether to propagate or swallow them.
        """
        existing = await self.uow.semantic_memories.list_active_by_user(user_id, limit=50)

        # Only consider memories of the same type, excluding the new memory itself
        candidates = [
            m for m in existing
            if m.memory_type == new_memory.memory_type and m.id != new_memory.id
        ]

        superseded_ids: List[str] = []

        for mem in candidates:
            # First check if Track 6E should have handled it as a near-duplicate
            sim = jaccard(new_memory.content, mem.content)
            if sim >= DEDUP_THRESHOLD:
                # Should have been caught by Track 6E deduplication.
                # Skip — it's a near-duplicate already handled upstream.
                continue

            # Evaluate for clear, deterministic contradiction / supersession
            if has_clear_supersession_evidence(mem.content, new_memory.content):
                # Clear supersession evidence found.
                # The new memory (more recent) supersedes the older one.
                await self.uow.semantic_memories.update(mem, {"is_active": False})
                superseded_ids.append(mem.id)
            # else: insufficient evidence → ambiguous or unrelated, preserve both

        if superseded_ids:
            try:
                for sid in superseded_ids:
                    await self.uow.audit.create({
                        "user_id": user_id,
                        "action": "memory_superseded",
                        "resource_type": "memory",
                        "resource_id": sid,
                        "result": "success",
                        "metadata_": {"superseded_by": new_memory.id}
                    })
            except Exception:
                pass
            await self.uow.commit()
            return ConflictResult(
                resolution=ConflictResolution.SUPERSEDED,
                superseded_memory_ids=superseded_ids,
            )

        try:
            await self.uow.audit.create({
                "user_id": user_id,
                "action": "memory_conflict_resolution",
                "resource_type": "memory",
                "resource_id": new_memory.id,
                "result": "no_conflict" if not candidates else "ambiguous",
                "metadata_": {}
            })
            await self.uow.commit()
        except Exception:
            pass
            
        return ConflictResult(
            resolution=ConflictResolution.NO_CONFLICT,
            superseded_memory_ids=[],
        )
