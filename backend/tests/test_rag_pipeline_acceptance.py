import pytest
import pytest_asyncio
import uuid
from pathlib import Path
from httpx import AsyncClient
from sqlalchemy.future import select

from app.core.config import settings
from app.db.models import User
from app.core.rag.embeddings import OllamaEmbeddingProvider, FakeEmbeddingProvider
from app.core.rag.errors import EmbeddingError
from app.core.rag.vector_store import ChromaVectorStore
from app.core.rag.tools import SearchDocumentsTool, GetDocumentTool
from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor, AuthorizationPolicy
from app.core.runtime.harness import AgentHarness
from app.core.runtime.schemas import RuntimeSession, ToolRequest, ExecutionState
from app.core.agent.registry import AgentRegistry, AgentDefinition
from app.core.context_engine.engine import ContextEngine
from app.core.context_engine.schemas import ContextCandidate
from app.core.model_gateway.gateway import ModelGateway
from app.providers.fake import FakeProvider
from app.db.database import AsyncSessionLocal
from app.services.auth import AuthService
from app.db.uow import UnitOfWork

@pytest_asyncio.fixture
async def seeded_admin(app_lifespan):
    from app.main import app
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.username == settings.FIRST_SUPERUSER))
        admin = res.scalars().first()
        admin_id = admin.id

    rag_service = app.state.rag_service
    # Re-ingest the two reports in the test database for the active admin
    backend_root = Path(__file__).resolve().parent.parent
    inspection_path = backend_root / "data" / "uploads" / "Pump_P204_Inspection_Report.txt"
    maintenance_path = backend_root / "data" / "uploads" / "Pump_P204_Maintenance_Report.txt"

    with open(inspection_path, "rb") as f:
        await rag_service.ingest_document(
            file_bytes=f.read(),
            filename="Pump_P204_Inspection_Report.txt",
            mime_type="text/plain",
            owner_id=admin_id
        )

    with open(maintenance_path, "rb") as f:
        await rag_service.ingest_document(
            file_bytes=f.read(),
            filename="Pump_P204_Maintenance_Report.txt",
            mime_type="text/plain",
            owner_id=admin_id
        )

    return admin

# ---------------------------------------------------------------------------
# Requirement 1: No silent fallback from Ollama to Fake in runtime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_silent_fallback():
    provider = OllamaEmbeddingProvider(model="nonexistent-model-xyz", base_url="http://127.0.0.1:99999", timeout=1.0)
    with pytest.raises(EmbeddingError):
        await provider.embed_text("test failure mode")

# ---------------------------------------------------------------------------
# Requirement 2 & 8: Embedding dimensions and no auto-drop of Chroma collections
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_embedding_dimensions_nomic_to_chroma():
    embedder = OllamaEmbeddingProvider(model=settings.DEFAULT_EMBEDDING_MODEL, base_url=settings.OLLAMA_BASE_URL)
    vec = await embedder.embed_text("dimension check")
    assert len(vec) == 768, f"Expected 768 dimensions from {settings.DEFAULT_EMBEDDING_MODEL}, got {len(vec)}"

    vstore = ChromaVectorStore(collection_name="mrpl_knowledge")
    coll = vstore.client.get_collection("mrpl_knowledge")
    res = coll.get(limit=1, include=["embeddings"])
    if res["embeddings"] is not None and len(res["embeddings"]) > 0:
        assert len(res["embeddings"][0]) == 768

    search_results = await vstore.similarity_search(vec, top_k=2, filters={})
    assert isinstance(search_results, list)

# ---------------------------------------------------------------------------
# Requirement 3: Canonical architecture chain
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_canonical_architecture_authorized_executor_rejection(app_lifespan):
    from app.main import app
    tool_registry = ToolRegistry()
    rag_service = app.state.rag_service
    tool = SearchDocumentsTool(rag_service)
    tool_registry.register(tool)

    assert tool.authorization_policy == AuthorizationPolicy.AUTHENTICATED

    local_exec = LocalToolExecutor(tool_registry)
    auth_exec = AuthorizedToolExecutor(local_exec)

    req = ToolRequest(tool="search_documents", arguments={"query": "test"}, call_id="c1")
    result = await auth_exec.execute(req, context={"user_id": ""})
    assert result.status == "error"
    assert "requires authentication" in result.output

# ---------------------------------------------------------------------------
# Requirement 4: Prevent duplicate identical retrieval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_redundant_duplicate_retrieval(seeded_admin):
    from app.main import app
    harness: AgentHarness = app.state.agent_harness
    agent = harness.registry.get("general_agent")
    session = RuntimeSession(
        session_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        agent_id="general_agent",
        agent_version="1.0",
        user_id=seeded_admin.id
    )

    candidates = []
    # 1. First retrieval
    ev1 = await harness._perform_rag_retrieval(session, agent, "pump p204 abnormalities", candidates)
    first_count = len(candidates)
    assert first_count > 0, "Initial retrieval should populate candidates"

    # 2. Second retrieval with identical query must skip and return empty events
    ev2 = await harness._perform_rag_retrieval(session, agent, "pump p204 abnormalities", candidates)
    assert len(ev2) == 0
    assert len(candidates) == first_count, "Candidates should not duplicate identical query"

# ---------------------------------------------------------------------------
# Requirement 5 & 6: Canonical type="rag" and citation-only SSE events
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_context_candidate_type_and_sanitized_sse(seeded_admin):
    from app.main import app
    harness: AgentHarness = app.state.agent_harness
    agent = harness.registry.get("general_agent")
    session = RuntimeSession(
        session_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        agent_id="general_agent",
        agent_version="1.0",
        user_id=seeded_admin.id
    )

    candidates = []
    events = await harness._perform_rag_retrieval(session, agent, "inspection report", candidates)

    for c in candidates:
        assert c.type == "rag"

    for ev in events:
        assert ev["type"] == "context_candidate"
        cand = ev["candidate"]
        assert cand["type"] == "rag"
        assert "content" not in cand
        assert "metadata" in cand
        assert "filename" in cand["metadata"]

# ---------------------------------------------------------------------------
# Requirement 7: Cross-user isolation tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_user_isolation(app_lifespan):
    from app.main import app
    rag_service = app.state.rag_service

    uow = UnitOfWork(session_factory=AsyncSessionLocal)
    async with uow:
        auth_service = AuthService(uow)
        user_a = await auth_service.create_user({"username": f"user_a_{uuid.uuid4().hex[:6]}", "password": "password123", "role": "USER"})
        user_b = await auth_service.create_user({"username": f"user_b_{uuid.uuid4().hex[:6]}", "password": "password123", "role": "USER"})
        await uow.commit()

    # Ingest document for User A
    doc_a = await rag_service.ingest_document(
        file_bytes=b"CONFIDENTIAL USER A DATA: Project Alpha secret passkey is 12345.",
        filename="alpha_secrets.txt",
        mime_type="text/plain",
        owner_id=user_a.id
    )

    # Ingest document for User B
    doc_b = await rag_service.ingest_document(
        file_bytes=b"CONFIDENTIAL USER B DATA: Project Beta budget is 99999 dollars.",
        filename="beta_budget.txt",
        mime_type="text/plain",
        owner_id=user_b.id
    )

    search_tool = SearchDocumentsTool(rag_service)
    get_tool = GetDocumentTool(rag_service)

    # User A searches for User B's secret - must NOT retrieve any of User B's content or documents
    res_a = await search_tool.execute({"query": "Project Beta budget"}, context={"user_id": user_a.id})
    assert not any("Beta" in c.content for c in res_a.context_candidates), "User A must NOT retrieve User B's content"
    assert not any(c.metadata.get("document_id") == doc_b.document_id for c in res_a.context_candidates)

    # User B searches for User A's secret - must NOT retrieve any of User A's content or documents
    res_b = await search_tool.execute({"query": "Project Alpha secret passkey"}, context={"user_id": user_b.id})
    assert not any("Alpha" in c.content for c in res_b.context_candidates), "User B must NOT retrieve User A's content"
    assert not any(c.metadata.get("document_id") == doc_a.document_id for c in res_b.context_candidates)

    # User A tries to get Document B by ID - must return 0 candidates because User A is not the owner
    res_get_b = await get_tool.execute({"document_id": doc_b.document_id}, context={"user_id": user_a.id})
    assert len(res_get_b.context_candidates) == 0, "User A cannot fetch User B's document by ID"

    # User B tries to get Document A by ID - must return 0 candidates because User B is not the owner
    res_get_a = await get_tool.execute({"document_id": doc_a.document_id}, context={"user_id": user_b.id})
    assert len(res_get_a.context_candidates) == 0, "User B cannot fetch User A's document by ID"

    # User A searches for their own document - succeeds
    res_own_a = await search_tool.execute({"query": "Project Alpha secret passkey"}, context={"user_id": user_a.id})
    assert len(res_own_a.context_candidates) > 0
    assert "12345" in res_own_a.context_candidates[0].content
    assert res_own_a.context_candidates[0].metadata["document_id"] == doc_a.document_id

    # User B searches for their own document - succeeds
    res_own_b = await search_tool.execute({"query": "Project Beta budget dollars"}, context={"user_id": user_b.id})
    assert len(res_own_b.context_candidates) > 0
    assert "99999" in res_own_b.context_candidates[0].content
    assert res_own_b.context_candidates[0].metadata["document_id"] == doc_b.document_id

# ---------------------------------------------------------------------------
# Requirement 8 & 10: Cross-document retrieval & Groundedness (August 18 vs August 20)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_document_retrieval(seeded_admin):
    from app.main import app
    rag_service = app.state.rag_service

    from app.core.rag.schemas import RetrievalQuery
    query = RetrievalQuery(
        query="Compare Pump P204 inspection findings from August 18 with maintenance on August 20",
        top_k=4,
        owner_id=seeded_admin.id
    )

    results = await rag_service.search_documents(query)
    filenames = {r.filename for r in results}
    assert "Pump_P204_Inspection_Report.txt" in filenames, "Must retrieve August 18 Inspection report"
    assert "Pump_P204_Maintenance_Report.txt" in filenames, "Must retrieve August 20 Maintenance report"

# ---------------------------------------------------------------------------
# Requirement 9: No hallucination when RAG returns no relevant candidates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_hallucination_on_empty_rag(seeded_admin):
    from app.main import app
    harness: AgentHarness = app.state.agent_harness
    agent = harness.registry.get("general_agent")
    session = RuntimeSession(
        session_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        agent_id="general_agent",
        agent_version="1.0",
        user_id=seeded_admin.id
    )

    unrelated_query = "What is the coolant temperature of Submarine Nuclear Reactor NR-99?"
    decision = await harness.execute(session, unrelated_query)

    ans_lower = decision.final_answer.lower()
    negatives = ["not", "does not contain", "no information", "don't have", "unmentioned", "unavailable", "cannot find", "no context"]
    assert any(neg in ans_lower for neg in negatives), f"Model fabricated knowledge instead of stating lack of context: {decision.final_answer}"

# ---------------------------------------------------------------------------
# Requirement 10: Verify no hardcoded Pump P204 facts in code
# ---------------------------------------------------------------------------
def test_no_hardcoded_pump_facts():
    import glob
    app_dir = Path(__file__).resolve().parent.parent / "app"
    forbidden_terms = ["faint abnormal bearing noise", "mechanical seal remains a monitoring item", "coupling alignment was inspected and adjusted"]
    for py_file in glob.glob(str(app_dir / "**" / "*.py"), recursive=True):
        if "scripts" in py_file:
            continue
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read().lower()
            for term in forbidden_terms:
                assert term not in content, f"Hardcoded fact '{term}' found in {py_file}!"
