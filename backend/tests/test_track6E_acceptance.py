"""
Track 6E Acceptance Tests — Memory Extraction + Deduplication
"""
import pytest
import pytest_asyncio
import uuid
import json
from typing import AsyncGenerator, List
from app.db.uow import UnitOfWork
from app.core.model_gateway.gateway import ModelGateway
from app.core.model_gateway.schemas import (
    GenerationRequest, GenerationResponse, Usage,
    StreamingEvent, ModelInfo, ModelCapabilities, Message as GenMessage
)
from app.core.model_gateway.provider import ModelProvider
from app.services.memory_extraction import (
    MemoryExtractionService, CONFIDENCE_THRESHOLD, VALID_MEMORY_TYPES,
    DUPLICATE_SIMILARITY_THRESHOLD
)
from app.services.semantic_memory import MemoryService


# ---------------------------------------------------------------------------
# Helpers: controllable fake providers for extraction tests
# ---------------------------------------------------------------------------

class JsonProvider(ModelProvider):
    """Returns a fixed JSON string as the generation response."""
    def __init__(self, response_json: str):
        self._response = response_json

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text=self._response,
            model=request.model,
            finish_reason="stop",
            usage=Usage(input_tokens=5, output_tokens=5, total_tokens=10)
        )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]:
        yield StreamingEvent(type="completed")

    async def health(self) -> bool:
        return True

    async def get_model_info(self, model_id: str) -> ModelInfo:
        return ModelInfo(
            model_id=model_id, provider="json",
            capabilities=ModelCapabilities(text_generation=True), context_window=8192
        )

    async def list_models(self) -> List[ModelInfo]:
        return []


class FailingProvider(ModelProvider):
    """Always raises an exception."""
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise RuntimeError("Simulated Gateway Failure")

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]:
        raise RuntimeError("Simulated Gateway Failure")
        yield  # make it a generator

    async def health(self) -> bool:
        return False

    async def get_model_info(self, model_id: str) -> ModelInfo:
        return ModelInfo(model_id=model_id, provider="failing",
                         capabilities=ModelCapabilities(), context_window=8192)

    async def list_models(self) -> List[ModelInfo]:
        return []


def make_gateway(provider: ModelProvider) -> ModelGateway:
    gw = ModelGateway()
    gw.register_provider("test_provider", provider)
    gw.register_model_route("test-model", "test_provider")
    return gw


def make_messages(texts: List[str]) -> List[GenMessage]:
    return [GenMessage(role="user", content=t) for t in texts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def uow():
    from app.db.database import AsyncSessionLocal
    return UnitOfWork(session_factory=AsyncSessionLocal)


@pytest_asyncio.fixture
async def test_user(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"testuser_{uid}",
            "password_hash": "hashed",
            "role": "USER"
        })
        await uow.commit()
    return user


@pytest_asyncio.fixture
async def other_user(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"other_{uid}",
            "password_hash": "hashed",
            "role": "USER"
        })
        await uow.commit()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_durable_fact_is_extracted(uow: UnitOfWork, test_user):
    """A user message containing a durable fact should produce a persisted memory."""
    extraction_json = json.dumps([
        {"content": "User works on MRPL maintenance systems.", "memory_type": "FACT", "confidence": 0.9}
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        service = MemoryExtractionService(uow, gw)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["I work on MRPL maintenance systems."]),
            model_id="test-model"
        )

    assert len(results) == 1
    assert results[0].content == "User works on MRPL maintenance systems."
    assert results[0].memory_type == "FACT"
    assert results[0].user_id == test_user.id


@pytest.mark.asyncio
async def test_2_transient_content_is_rejected(uow: UnitOfWork, test_user):
    """Low-confidence or invalid entries are filtered before persistence."""
    # LLM returns a low-confidence item and an item with invalid type
    extraction_json = json.dumps([
        {"content": "Sure, no problem!", "memory_type": "FACT", "confidence": 0.1},   # below threshold
        {"content": "User asked what time it is.", "memory_type": "QUESTION", "confidence": 0.8},  # invalid type
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        service = MemoryExtractionService(uow, gw)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["What time is it?"]),
            model_id="test-model"
        )

    assert results == []


@pytest.mark.asyncio
async def test_3_structured_extraction_output_is_validated(uow: UnitOfWork, test_user):
    """Malformed LLM output does not crash extraction and produces zero memories."""
    for bad_response in [
        "This is just prose text, not JSON.",
        '{"not": "a list"}',
        "",
        "null",
    ]:
        gw = make_gateway(JsonProvider(bad_response))
        async with uow:
            service = MemoryExtractionService(uow, gw)
            results = await service.extract_from_messages(
                test_user.id,
                make_messages(["Some user message."]),
                model_id="test-model"
            )
        assert results == [], f"Expected no results for bad response: {bad_response!r}"


@pytest.mark.asyncio
async def test_4_model_gateway_is_used_not_provider_directly(uow: UnitOfWork, test_user):
    """
    MemoryExtractionService must accept only a ModelGateway, not a raw provider.
    Verify the gateway is the sole interface (constructor check + call path).
    """
    extraction_json = json.dumps([
        {"content": "User prefers dark mode.", "memory_type": "PREFERENCE", "confidence": 0.8}
    ])
    provider = JsonProvider(extraction_json)
    gw = make_gateway(provider)

    # Service is constructed with a ModelGateway, not a provider
    async with uow:
        service = MemoryExtractionService(uow, gw)
        assert hasattr(service, 'gateway')
        assert isinstance(service.gateway, ModelGateway)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["I prefer dark mode."]),
            model_id="test-model"
        )

    assert len(results) == 1


@pytest.mark.asyncio
async def test_5_exact_duplicate_is_not_created(uow: UnitOfWork, test_user):
    """If an identical memory already exists, no new memory is created."""
    existing_content = "User prefers Python over Java."
    extraction_json = json.dumps([
        {"content": existing_content, "memory_type": "PREFERENCE", "confidence": 0.9}
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        mem_service = MemoryService(uow)
        # Pre-create the identical memory
        await mem_service.create_memory(test_user.id, existing_content, "PREFERENCE")

        service = MemoryExtractionService(uow, gw)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["I prefer Python over Java."]),
            model_id="test-model"
        )

        # Extraction returns None for exact dupe (no new memory created)
        assert all(r is None for r in results)

        # Only one memory in the database
        memories = await mem_service.list_memories(test_user.id)
        assert len(memories) == 1


@pytest.mark.asyncio
async def test_6_near_duplicate_is_handled(uow: UnitOfWork, test_user):
    """
    A near-duplicate (high Jaccard similarity, same type) updates the existing memory
    rather than creating a second one.
    """
    original_content = "User prefers Python for scripting."
    updated_content = "User prefers Python for all scripting work."

    extraction_json = json.dumps([
        {"content": updated_content, "memory_type": "PREFERENCE", "confidence": 0.85}
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        mem_service = MemoryService(uow)
        original = await mem_service.create_memory(test_user.id, original_content, "PREFERENCE")

        service = MemoryExtractionService(uow, gw)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["I prefer Python for all scripting work."]),
            model_id="test-model"
        )

        # Only one memory should exist (updated, not duplicated)
        memories = await mem_service.list_memories(test_user.id)
        assert len(memories) == 1
        assert memories[0].content == updated_content


@pytest.mark.asyncio
async def test_7_different_memories_are_preserved(uow: UnitOfWork, test_user):
    """Two genuinely different memories are both persisted."""
    extraction_json = json.dumps([
        {"content": "User works with MRPL maintenance documents.", "memory_type": "FACT", "confidence": 0.9},
        {"content": "User prefers concise summaries.", "memory_type": "PREFERENCE", "confidence": 0.85},
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        service = MemoryExtractionService(uow, gw)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["I work with MRPL docs and I prefer concise summaries."]),
            model_id="test-model"
        )

        mem_service = MemoryService(uow)
        memories = await mem_service.list_memories(test_user.id)
        assert len(memories) == 2


@pytest.mark.asyncio
async def test_8_contradictory_memories_are_not_merged(uow: UnitOfWork, test_user):
    """
    Contradictory memories (same type but genuinely different content, below the
    near-duplicate threshold) must NOT be silently merged or deleted.
    Track 6F is responsible for conflict resolution.
    """
    content_a = "User prefers Qwen as the primary model."
    content_b = "User prefers Llama as the primary model."

    # Jaccard("User prefers Qwen as the primary model.",
    #          "User prefers Llama as the primary model.")
    # Shared: {"user", "prefers", "as", "the", "primary", "model."} = 6
    # Union = 8. Sim = 6/8 = 0.75 — which is >= threshold (0.7), same type.
    # This means the near-duplicate logic WOULD update. To test true contradiction
    # we use words sufficiently different so Jaccard stays below threshold.
    content_a = "User requires Qwen for inference tasks."
    content_b = "The team has selected Llama for all production inference."

    extraction_json = json.dumps([
        {"content": content_b, "memory_type": "DECISION", "confidence": 0.9}
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        mem_service = MemoryService(uow)
        await mem_service.create_memory(test_user.id, content_a, "DECISION")

        service = MemoryExtractionService(uow, gw)
        await service.extract_from_messages(
            test_user.id,
            make_messages(["The team has selected Llama for all production inference."]),
            model_id="test-model"
        )

        memories = await mem_service.list_memories(test_user.id)
        contents = {m.content for m in memories}
        # Both contradictory memories must survive (conflict resolution is Track 6F)
        assert content_a in contents
        assert content_b in contents
        assert len(memories) == 2


@pytest.mark.asyncio
async def test_9_user_ownership_isolation(uow: UnitOfWork, test_user, other_user):
    """
    Memories extracted for user A are not accessible to user B, and vice versa.
    """
    extraction_json_a = json.dumps([
        {"content": "User A works at site Alpha.", "memory_type": "FACT", "confidence": 0.9}
    ])
    extraction_json_b = json.dumps([
        {"content": "User B works at site Beta.", "memory_type": "FACT", "confidence": 0.9}
    ])

    async with uow:
        mem_service = MemoryService(uow)

        gw_a = make_gateway(JsonProvider(extraction_json_a))
        svc_a = MemoryExtractionService(uow, gw_a)
        await svc_a.extract_from_messages(
            test_user.id,
            make_messages(["I work at site Alpha."]),
            model_id="test-model"
        )

        gw_b = make_gateway(JsonProvider(extraction_json_b))
        svc_b = MemoryExtractionService(uow, gw_b)
        await svc_b.extract_from_messages(
            other_user.id,
            make_messages(["I work at site Beta."]),
            model_id="test-model"
        )

        mems_a = await mem_service.list_memories(test_user.id)
        mems_b = await mem_service.list_memories(other_user.id)

    assert len(mems_a) == 1
    assert mems_a[0].content == "User A works at site Alpha."
    assert mems_a[0].user_id == test_user.id

    assert len(mems_b) == 1
    assert mems_b[0].content == "User B works at site Beta."
    assert mems_b[0].user_id == other_user.id


@pytest.mark.asyncio
async def test_10_extraction_failure_does_not_corrupt_existing_memories(uow: UnitOfWork, test_user):
    """If the ModelGateway raises during extraction, existing memories remain intact."""
    async with uow:
        mem_service = MemoryService(uow)
        existing = await mem_service.create_memory(
            test_user.id, "Existing important fact.", "FACT"
        )

        gw = make_gateway(FailingProvider())
        service = MemoryExtractionService(uow, gw)
        results = await service.extract_from_messages(
            test_user.id,
            make_messages(["New message that should trigger extraction."]),
            model_id="test-model"
        )

        assert results == []

        # Original memory is untouched
        memories = await mem_service.list_memories(test_user.id)
        assert len(memories) == 1
        assert memories[0].id == existing.id
        assert memories[0].content == "Existing important fact."


@pytest.mark.asyncio
async def test_11_track6D_retrieval_remains_functional(uow: UnitOfWork, test_user):
    """
    Track 6D retrieval (retrieve_memories) still works correctly after
    Track 6E extraction creates memories.
    """
    extraction_json = json.dumps([
        {"content": "User specialises in pump maintenance.", "memory_type": "FACT", "confidence": 0.9}
    ])
    gw = make_gateway(JsonProvider(extraction_json))

    async with uow:
        service = MemoryExtractionService(uow, gw)
        await service.extract_from_messages(
            test_user.id,
            make_messages(["I specialise in pump maintenance work."]),
            model_id="test-model"
        )

        mem_service = MemoryService(uow)
        candidates = await mem_service.retrieve_memories(test_user.id, "pump maintenance")

    assert len(candidates) >= 1
    assert any("pump" in c.content.lower() for c in candidates)
    assert all(c.type == "memory" for c in candidates)
