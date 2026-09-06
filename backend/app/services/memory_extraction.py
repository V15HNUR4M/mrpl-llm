"""
Track 6E — Memory Extraction Service

Extracts durable semantic memories from conversation messages using the
existing ModelGateway. Never calls Ollama or any provider directly.

Flow:
  conversation messages
       ↓
  MemoryExtractionService.extract_from_messages()
       ↓
  ModelGateway (structured prompt → JSON response)
       ↓
  validate (schema + ownership bound)
       ↓
  deduplicate against existing active memories
       ↓
  MemoryService.create_memory() or update_memory()
       ↓
  Persistent Memory
"""

import json
import re
from typing import List, Optional, Any
from dataclasses import dataclass

from app.db.uow import UnitOfWork
from app.core.model_gateway.gateway import ModelGateway
from app.core.model_gateway.schemas import GenerationRequest, Message as GenMessage
from app.services.semantic_memory import MemoryService
from app.services.memory_conflict import MemoryConflictService

# Allowed memory types that extraction may produce
VALID_MEMORY_TYPES = {"FACT", "PREFERENCE", "PROJECT_CONTEXT", "DECISION", "TASK", "ENTITY", "EVENT"}

# Minimum confidence required to persist a memory
CONFIDENCE_THRESHOLD = 0.5

# Minimum content length to be considered meaningful
MIN_CONTENT_LENGTH = 5

# Near-duplicate detection: if Jaccard similarity of word sets exceeds this,
# treat as duplicate and update rather than create.
DUPLICATE_SIMILARITY_THRESHOLD = 0.7


@dataclass
class ExtractedMemoryCandidate:
    """Structured output from the extraction LLM call."""
    content: str
    memory_type: str
    confidence: float


class MemoryExtractionService:
    """
    Extracts durable, user-level memories from conversation messages using the
    ModelGateway. Validates, deduplicates, and delegates persistence to MemoryService.

    Boundaries:
    - Does NOT call providers/Ollama directly.
    - Does NOT inject text directly into prompts or bypass the Context Engine.
    - Calls MemoryConflictService (Track 6F) after creating a new memory.
    """

    _EXTRACTION_PROMPT_TEMPLATE = """You are a memory extraction assistant. Analyze the following user messages and identify durable facts, preferences, or decisions that are worth remembering long-term.

MESSAGES:
{messages}

Extract up to 5 important memories. Each memory must be:
- A durable fact, preference, project context, decision, task, entity, or event.
- NOT a transient question, greeting, or conversational filler.
- NOT a question the user asked.
- NOT the assistant's answer or explanation.
- Specific and concise (1-2 sentences maximum).

Respond ONLY with a valid JSON array. Each element must have:
  "content": string (the memory text, max 200 chars)
  "memory_type": one of FACT, PREFERENCE, PROJECT_CONTEXT, DECISION, TASK, ENTITY, EVENT
  "confidence": float between 0.0 and 1.0

If no durable memories are found, respond with an empty array: []

Example:
[
  {{"content": "User prefers Python for scripting tasks.", "memory_type": "PREFERENCE", "confidence": 0.9}},
  {{"content": "Project uses SQLite as the local database.", "memory_type": "PROJECT_CONTEXT", "confidence": 0.85}}
]

Respond with JSON only. No explanation, no markdown code fences."""

    def __init__(self, uow: UnitOfWork, gateway: ModelGateway):
        self.uow = uow
        self.gateway = gateway

    async def extract_from_messages(
        self,
        user_id: str,
        messages: List[Any],  # List of Message-like objects with .role and .content
        model_id: Optional[str] = None,
    ) -> List[Any]:
        """
        Main entry point. Extracts memories from a list of conversation messages
        for the given user, deduplicates, and persists them.

        Returns the list of Memory objects that were created or updated.
        """
        # Only consider user messages for extraction (not assistant/system)
        user_messages = [m for m in messages if getattr(m, "role", None) == "user"]
        if not user_messages:
            return []

        from app.core.config import settings
        target_model = model_id or settings.DEFAULT_CHAT_MODEL

        # Build prompt
        message_text = "\n".join(
            f"User: {m.content}" for m in user_messages
        )
        prompt = self._EXTRACTION_PROMPT_TEMPLATE.format(messages=message_text)

        # Call ModelGateway (never the provider directly)
        try:
            gen_req = GenerationRequest(
                model=target_model,
                messages=[GenMessage(role="user", content=prompt)],
            )
            response = await self.gateway.generate(gen_req)
            raw_text = response.text.strip()
        except Exception:
            # Extraction failure must not corrupt existing memories
            return []

        # Parse structured output
        candidates = self._parse_extraction_response(raw_text)
        if not candidates:
            return []

        # Persist with deduplication
        memory_service = MemoryService(self.uow)
        persisted = []
        for candidate in candidates:
            result = await self._deduplicate_and_persist(user_id, candidate, memory_service)
            if result is not None:
                persisted.append(result)

        try:
            await self.uow.audit.create({
                "user_id": user_id,
                "action": "memory_extraction",
                "resource_type": "memory",
                "resource_id": None,
                "result": "success",
                "metadata_": {"extracted_count": len(persisted)}
            })
            await self.uow.commit()
        except Exception:
            pass

        return persisted

    # ------------------------------------------------------------------
    # Parsing and validation
    # ------------------------------------------------------------------

    def _parse_extraction_response(self, raw_text: str) -> List[ExtractedMemoryCandidate]:
        """
        Parses and validates the structured JSON response from the LLM.
        Returns a list of validated ExtractedMemoryCandidate objects.
        Silently drops any malformed or low-confidence entries.
        """
        # Strip accidental markdown fences if the model adds them
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip().rstrip("`").strip()

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return []

        if not isinstance(data, list):
            return []

        candidates = []
        for item in data:
            if not isinstance(item, dict):
                continue
            candidate = self._validate_candidate(item)
            if candidate is not None:
                candidates.append(candidate)

        return candidates

    def _validate_candidate(self, item: dict) -> Optional[ExtractedMemoryCandidate]:
        """
        Validates a single extraction candidate dict.
        Returns None if the candidate is invalid or below confidence threshold.
        """
        content = item.get("content", "")
        memory_type = item.get("memory_type", "")
        confidence = item.get("confidence", 0.0)

        # Type checks
        if not isinstance(content, str) or not isinstance(confidence, (int, float)):
            return None

        # Content must be meaningful
        content = content.strip()
        if len(content) < MIN_CONTENT_LENGTH or len(content) > 200:
            return None

        # memory_type must be in the allowed set
        memory_type = str(memory_type).upper().strip()
        if memory_type not in VALID_MEMORY_TYPES:
            return None

        # Confidence must meet threshold
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None
        if confidence < CONFIDENCE_THRESHOLD:
            return None

        return ExtractedMemoryCandidate(
            content=content,
            memory_type=memory_type,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _jaccard_similarity(self, a: str, b: str) -> float:
        """Deterministic, bounded Jaccard similarity on normalised word sets.
        Strips leading/trailing punctuation from each token for consistent matching.
        """
        import string
        def normalise(text: str):
            return {w.strip(string.punctuation).lower() for w in text.split() if w.strip(string.punctuation)}
        words_a = normalise(a)
        words_b = normalise(b)
        if not words_a and not words_b:
            return 1.0
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    async def _deduplicate_and_persist(
        self,
        user_id: str,
        candidate: ExtractedMemoryCandidate,
        memory_service: MemoryService,
    ) -> Optional[Any]:
        """
        Checks existing active memories for the user for exact or near-duplicate content.
        - Exact duplicate: same content → skip (no-op).
        - Near-duplicate (Jaccard >= threshold, same type): update content.
        - No match: create new memory.
        - Contradictory content (same type, different fact): leave both (Track 6F handles resolution).
        """
        existing = await memory_service.list_memories(user_id, limit=50)

        best_match: Optional[Any] = None
        best_similarity = 0.0

        for mem in existing:
            sim = self._jaccard_similarity(candidate.content, mem.content)
            if sim > best_similarity:
                best_similarity = sim
                best_match = mem

        # Exact duplicate: do nothing
        if best_match is not None and best_similarity == 1.0:
            return None

        # Near-duplicate of the same type: update content
        if (
            best_match is not None
            and best_similarity >= DUPLICATE_SIMILARITY_THRESHOLD
            and best_match.memory_type == candidate.memory_type
        ):
            updated = await memory_service.update_memory(
                user_id, best_match.id, {"content": candidate.content}
            )
            return updated

        # No duplicate found: create new memory
        created = await memory_service.create_memory(
            user_id, candidate.content, candidate.memory_type
        )
        # Track 6F: detect and resolve any conflict the new memory creates.
        # Failure must not prevent the memory from being created.
        try:
            conflict_service = MemoryConflictService(self.uow)
            await conflict_service.detect_and_resolve(user_id, created)
        except Exception:
            pass
        return created
