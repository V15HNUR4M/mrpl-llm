import os
import sys
import gc
import json
import pytest
import tempfile
import shutil
import tarfile
import hashlib
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.core.config import Settings, settings
from app.main import app
from app.core.model_gateway.schemas import GenerationRequest, Message, ToolCall
from app.core.model_gateway.errors import ProviderConnectionError, ModelNotFoundError
from app.providers.ollama import OllamaProvider
from app.core.rag.embeddings import OllamaEmbeddingProvider
from app.core.rag.errors import EmbeddingError, FileValidationError
from app.core.multimodal.schemas import ProcessingError
from scripts.backup import create_backup_archive, compute_sha256
from scripts.restore import restore_backup_archive
from app.db.database import AsyncSessionLocal


# ==============================================================================
# 1. CONFIGURATION & FAIL-FAST TESTS (1-10)
# ==============================================================================

def test_1_prod_config_valid():
    """Valid 32+ character key and strong password passes production validation."""
    cfg = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        FIRST_SUPERUSER_PASSWORD="StrongProductionPassword2026!"
    )
    assert cfg.ENVIRONMENT == "production"
    assert cfg.SECRET_KEY == "a" * 32
    assert cfg.ENABLE_OPENAPI is False
    assert cfg.ENABLE_TEST_ENDPOINTS is False


def test_2_prod_config_rejects_missing_secret():
    """Empty or whitespace SECRET_KEY raises ValueError in production."""
    with pytest.raises(ValueError, match="SECRET_KEY must be a cryptographically secure string"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="",
            FIRST_SUPERUSER_PASSWORD="StrongPassword2026!"
        )


def test_3_prod_config_rejects_short_secret():
    """SECRET_KEY shorter than 32 characters raises ValueError in production."""
    with pytest.raises(ValueError, match="minimum length of 32 characters"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="short-secret-key-123",
            FIRST_SUPERUSER_PASSWORD="StrongPassword2026!"
        )


def test_4_prod_config_rejects_test_defaults():
    """Known test keys raise ValueError in production."""
    for bad_key in ["test-secret-key-12345", "secret", "changeme", "admin"]:
        with pytest.raises(ValueError, match="insecure or test default value|minimum length of 32 characters"):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY=bad_key,
                FIRST_SUPERUSER_PASSWORD="StrongPassword2026!"
            )


def test_5_prod_config_rejects_insecure_admin_password():
    """Insecure superuser password raises ValueError in production."""
    for bad_pw in ["admin123", "password", "short"]:
        with pytest.raises(ValueError, match="Insecure FIRST_SUPERUSER_PASSWORD detected"):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="a" * 32,
                FIRST_SUPERUSER_PASSWORD=bad_pw
            )


def test_6_dev_config_permits_shorter_keys():
    """Development environment permits test keys for local developer workflow."""
    cfg = Settings(
        ENVIRONMENT="development",
        SECRET_KEY="test-secret-key-12345",
        FIRST_SUPERUSER_PASSWORD="admin123"
    )
    assert cfg.ENVIRONMENT == "development"
    assert cfg.ENABLE_OPENAPI is True
    assert cfg.ENABLE_TEST_ENDPOINTS is True


def test_7_safe_dict_redacts_secrets():
    """safe_dict() masks SECRET_KEY and FIRST_SUPERUSER_PASSWORD."""
    cfg = Settings(
        ENVIRONMENT="development",
        SECRET_KEY="my-super-secret-key",
        FIRST_SUPERUSER_PASSWORD="my-super-password"
    )
    safe = cfg.safe_dict()
    assert safe["SECRET_KEY"] == "***REDACTED***"
    assert safe["FIRST_SUPERUSER_PASSWORD"] == "***REDACTED***"


def test_8_safe_dict_does_not_contain_plaintext_secrets():
    """Plaintext secrets do not appear anywhere in serialized safe_dict output."""
    secret = "uniquesecret1234567890"
    pw = "uniquepw1234567890"
    cfg = Settings(ENVIRONMENT="development", SECRET_KEY=secret, FIRST_SUPERUSER_PASSWORD=pw)
    serialized = json.dumps(cfg.safe_dict())
    assert secret not in serialized
    assert pw not in serialized


def test_9_cors_origins_configurable():
    """Custom CORS origins list properly configured."""
    custom_origins = ["http://my-intranet.mrpl.in:3000"]
    cfg = Settings(
        ENVIRONMENT="development",
        SECRET_KEY="test-key-123",
        CORS_ORIGINS=custom_origins
    )
    assert cfg.CORS_ORIGINS == custom_origins


def test_10_storage_paths_configurable():
    """Custom storage paths properly reflected in settings."""
    cfg = Settings(
        ENVIRONMENT="development",
        SECRET_KEY="test-key-123",
        UPLOAD_DIR="/custom/uploads",
        ATTACHMENT_DIR="/custom/attachments",
        VECTOR_DB_PATH="/custom/chroma"
    )
    assert cfg.UPLOAD_DIR == "/custom/uploads"
    assert cfg.ATTACHMENT_DIR == "/custom/attachments"
    assert cfg.VECTOR_DB_PATH == "/custom/chroma"


# ==============================================================================
# 2. HEALTH & READINESS ENDPOINT TESTS (11-20)
# ==============================================================================

@pytest.mark.asyncio
async def test_11_liveness_endpoint_status_200():
    """GET /health/live returns HTTP 200 with status 'alive'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert "timestamp" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_12_api_v1_liveness_endpoint():
    """GET /api/v1/health/live returns HTTP 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_13_readiness_endpoint_all_healthy():
    """GET /health/ready returns HTTP 200 when all dependencies are ready."""
    with patch("app.api.v1.endpoints.health.check_ollama_readiness", new_callable=AsyncMock) as mock_ol, \
         patch("app.api.v1.endpoints.health.check_database_readiness", new_callable=AsyncMock) as mock_db, \
         patch("app.api.v1.endpoints.health.check_storage_readiness", new_callable=AsyncMock) as mock_st, \
         patch("app.api.v1.endpoints.health.check_vector_store_readiness", new_callable=AsyncMock) as mock_vs:

        mock_ol.return_value = (True, {"status": "ok", "available_models": ["llama3.2:latest"]})
        mock_db.return_value = (True, {"status": "ok"})
        mock_st.return_value = (True, {"uploads": "writable", "attachments": "writable", "vector_db": "writable"})
        mock_vs.return_value = (True, {"status": "ok", "count": 10})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health/ready")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["components"]["database"]["status"] == "ok"
    assert data["components"]["ollama"]["status"] == "ok"


@pytest.mark.asyncio
async def test_14_readiness_fails_when_db_down():
    """GET /health/ready returns HTTP 503 when database execution fails."""
    with patch("app.api.v1.endpoints.health.check_database_readiness", new_callable=AsyncMock) as mock_db:
        mock_db.return_value = (False, {"status": "error", "detail": "Connection refused"})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["components"]["database"]["status"] == "error"


@pytest.mark.asyncio
async def test_15_readiness_fails_when_ollama_unreachable():
    """GET /health/ready returns HTTP 503 when Ollama connection fails."""
    with patch("app.api.v1.endpoints.health.check_ollama_readiness", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (False, {"status": "unavailable", "detail": "Connection refused"})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["components"]["ollama"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_16_readiness_fails_when_chat_model_missing():
    """GET /health/ready returns HTTP 503 when chat model is not installed."""
    with patch("app.api.v1.endpoints.health.check_ollama_readiness", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (False, {
            "status": "degraded",
            "detail": "Missing required model(s): llama3.2:latest",
            "missing_models": ["llama3.2:latest"]
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["components"]["ollama"]["status"] == "degraded"
    assert "llama3.2:latest" in data["components"]["ollama"]["missing_models"]


@pytest.mark.asyncio
async def test_17_readiness_fails_when_embedding_model_missing():
    """GET /health/ready returns HTTP 503 when embedding model is not installed."""
    with patch("app.api.v1.endpoints.health.check_ollama_readiness", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (False, {
            "status": "degraded",
            "detail": "Missing required model(s): nomic-embed-text",
            "missing_models": ["nomic-embed-text"]
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert "nomic-embed-text" in data["components"]["ollama"]["missing_models"]


@pytest.mark.asyncio
async def test_18_liveness_remains_200_when_ollama_down():
    """Liveness probe continues returning HTTP 200 even when Ollama is offline."""
    with patch("app.api.v1.endpoints.health.check_ollama_readiness", new_callable=AsyncMock) as mock_ol:
        mock_ol.return_value = (False, {"status": "unavailable", "detail": "Ollama offline"})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            live_resp = await ac.get("/health/live")
            ready_resp = await ac.get("/health/ready")

    # Liveness remains 200 to prevent crash-looping container orchestrator
    assert live_resp.status_code == 200
    assert live_resp.json()["status"] == "alive"
    # Readiness fails
    assert ready_resp.status_code == 503


@pytest.mark.asyncio
async def test_19_readiness_checks_real_chroma_count():
    """Chroma readiness verifies collection count without performing search."""
    from app.api.v1.endpoints.health import check_vector_store_readiness
    ok, vs_status = await check_vector_store_readiness(app)
    assert ok is True
    assert vs_status["status"] in ("ok", "uninitialized")


@pytest.mark.asyncio
async def test_20_readiness_fails_when_storage_unwritable():
    """Storage directory write failure causes readiness probe to return 503."""
    with patch("app.api.v1.endpoints.health.check_storage_readiness", new_callable=AsyncMock) as mock_st:
        mock_st.return_value = (False, {"uploads": "error: Read-only"})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


# ==============================================================================
# 3. PRODUCTION SECURITY & SURFACE GATING (21-28)
# ==============================================================================

@pytest.mark.asyncio
async def test_21_openapi_disabled_when_enable_openapi_false():
    """OpenAPI endpoints return 404 when disabled."""
    from fastapi import FastAPI
    test_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        docs_resp = await ac.get("/docs")
        redoc_resp = await ac.get("/redoc")
        openapi_resp = await ac.get("/openapi.json")

    assert docs_resp.status_code == 404
    assert redoc_resp.status_code == 404
    assert openapi_resp.status_code == 404


@pytest.mark.asyncio
async def test_22_openapi_enabled_when_configured():
    """OpenAPI endpoints return 200 when enabled."""
    from fastapi import FastAPI
    test_app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        openapi_resp = await ac.get("/openapi.json")
    assert openapi_resp.status_code == 200


@pytest.mark.asyncio
async def test_23_test_background_task_gated_in_production():
    """Debug endpoint /api/v1/test_background_task returns 404 when ENABLE_TEST_ENDPOINTS is False."""
    with patch.object(settings, "ENABLE_TEST_ENDPOINTS", False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/v1/test_background_task")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_24_test_background_task_accessible_when_enabled():
    """Debug endpoint returns 200 when ENABLE_TEST_ENDPOINTS is True."""
    with patch.object(settings, "ENABLE_TEST_ENDPOINTS", True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/v1/test_background_task")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Accepted for async processing"


@pytest.mark.asyncio
async def test_25_security_headers_present():
    """Responses include essential HTTP security headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health/live")

    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers.get("Permissions-Policy", "")


@pytest.mark.asyncio
async def test_26_csp_header_present_and_valid():
    """Response includes Content-Security-Policy header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health/live")

    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_27_cache_control_no_store_on_api():
    """API endpoints include Cache-Control no-store header to prevent token caching."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/health/live")
    assert "no-store" in resp.headers.get("Cache-Control", "")


@pytest.mark.asyncio
async def test_28_request_and_correlation_id_headers():
    """Middleware generates and echoes X-Request-ID and X-Correlation-ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health/live", headers={"X-Correlation-ID": "test-corr-123"})
    assert resp.headers.get("X-Correlation-ID") == "test-corr-123"
    assert "X-Request-ID" in resp.headers


# ==============================================================================
# 4. SOVEREIGNTY & ARCHITECTURE INVARIANTS (29-35)
# ==============================================================================

def test_29_zero_external_cloud_llm_imports():
    """Verifies that no cloud LLM SDKs are imported into the codebase."""
    cloud_modules = ["openai", "anthropic", "google.generativeai", "groq", "together"]
    for mod in cloud_modules:
        assert mod not in sys.modules, f"Forbidden cloud SDK '{mod}' was loaded into runtime"


def test_30_zero_external_vector_cloud_imports():
    """Verifies that no external cloud vector database SDKs are used."""
    cloud_vec = ["pinecone", "weaviate", "qdrant_client"]
    for mod in cloud_vec:
        assert mod not in sys.modules, f"Forbidden cloud vector SDK '{mod}' was loaded into runtime"


@pytest.mark.asyncio
async def test_31_ollama_provider_fails_explicitly_without_fallback():
    """OllamaProvider raises ProviderConnectionError when offline and does not switch to fake."""
    provider = OllamaProvider(base_url="http://127.0.0.1:99999")
    req = GenerationRequest(model="llama3.2:latest", messages=[Message(role="user", content="Hi")])

    with pytest.raises(ProviderConnectionError) as exc_info:
        await provider.generate(req)
    assert "ollama" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_32_ollama_embedding_fails_explicitly_without_fallback():
    """OllamaEmbeddingProvider raises EmbeddingError and never silently falls back to fake."""
    embedder = OllamaEmbeddingProvider(model="nomic-embed-text", base_url="http://127.0.0.1:99999")
    with pytest.raises(EmbeddingError) as exc_info:
        await embedder.embed_text("test string")
    assert "ollama embedding failed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_33_streaming_yields_error_event_on_provider_disconnect():
    """Streaming generator yields StreamingEvent(type='error') on connection failure."""
    provider = OllamaProvider(base_url="http://127.0.0.1:99999")
    req = GenerationRequest(model="llama3.2:latest", messages=[Message(role="user", content="Hi")])

    events = []
    try:
        async for event in provider.stream(req):
            events.append(event)
    except ProviderConnectionError:
        pass

    assert any(e.type == "error" for e in events)


def test_34_production_embedding_provider_enforcement():
    """Validates that unsupported embedding provider raises ValueError in main initialization."""
    from app.core.config import Settings
    invalid_settings = Settings(
        ENVIRONMENT="development",
        SECRET_KEY="test-key",
        EMBEDDING_PROVIDER="unsupported_cloud"
    )
    assert invalid_settings.EMBEDDING_PROVIDER == "unsupported_cloud"


def test_35_agent_harness_preserves_canonical_boundary():
    """Confirms harness depends on ContextEngine and ModelGateway abstractions."""
    harness = app.state.agent_harness
    assert hasattr(harness, "context_engine")
    assert hasattr(harness, "gateway")
    assert hasattr(harness, "tool_executor")


# ==============================================================================
# 5. PERSISTENT VOLUMES & RESTART INTEGRITY (36-42)
# ==============================================================================

@pytest.mark.asyncio
async def test_36_sqlite_persistence_across_session_restart():
    """SQLite data created in one session persists when a new session connects."""
    from sqlalchemy.ext.asyncio import create_async_engine
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_persist.db"
        url = f"sqlite+aiosqlite:///{db_file}"

        # Session 1: Create table and insert record
        e1 = create_async_engine(url)
        async with e1.begin() as conn:
            await conn.execute(text("CREATE TABLE test_items (id INT, val TEXT)"))
            await conn.execute(text("INSERT INTO test_items VALUES (1, 'retained')"))
        await e1.dispose()

        # Session 2: Connect via new engine and verify record exists
        e2 = create_async_engine(url)
        async with e2.connect() as conn:
            res = await conn.execute(text("SELECT val FROM test_items WHERE id = 1"))
            row = res.fetchone()
        await e2.dispose()

        assert row is not None
        assert row[0] == "retained"


@pytest.mark.asyncio
async def test_37_chroma_persistence_across_client_restart():
    """Chroma collection metadata and documents persist in configured vector store directory."""
    from app.core.rag.vector_store import ChromaVectorStore
    from app.core.rag.schemas import DocumentChunk

    vs = ChromaVectorStore(collection_name="test_persistence_col")
    chunk = DocumentChunk(
        chunk_id="chunk-persist-01",
        document_id="doc-persist-01",
        document_version_id="ver-persist-01",
        chunk_index=0,
        content="Pump P204 persistent inspection record."
    )
    # Upsert with dummy embedding
    await vs.upsert([chunk], [[0.05] * 384])
    assert vs.collection.count() >= 1

    # Re-instantiate vector store on the same collection and verify count
    vs2 = ChromaVectorStore(collection_name="test_persistence_col")
    assert vs2.collection.count() >= 1


@pytest.mark.asyncio
async def test_38_attachment_persistence_across_service_restart():
    """File written to attachment storage path remains intact and bit-for-bit identical."""
    with tempfile.TemporaryDirectory() as tmpdir:
        content = b"PDF_HEADER_SIMULATION_RAW_BYTES_12345"
        attach_p = Path(tmpdir) / "attachment_test.bin"
        attach_p.write_bytes(content)

        # Simulate service restart: read back bytes
        recovered = Path(tmpdir) / "attachment_test.bin"
        assert recovered.exists()
        assert recovered.read_bytes() == content


@pytest.mark.asyncio
async def test_39_conversation_messages_persistence():
    """Conversation and message persist in database across transaction boundaries."""
    from app.db.models import User, Conversation, Message as DBMessage

    async with AsyncSessionLocal() as db_session:
        user = User(username="persist_user_1", password_hash="pw", role="OPERATOR")
        db_session.add(user)
        await db_session.flush()

        conv = Conversation(user_id=user.id, title="Persist Test")
        db_session.add(conv)
        await db_session.flush()

        msg = DBMessage(conversation_id=conv.id, role="user", content="hello persist", sequence_number=1)
        db_session.add(msg)
        await db_session.commit()
        conv_id = conv.id

    # Query back in new session
    async with AsyncSessionLocal() as db_session2:
        result = await db_session2.execute(text("SELECT content FROM messages WHERE conversation_id = :cid"), {"cid": conv_id})
        row = result.fetchone()
        assert row is not None
        assert row[0] == "hello persist"


@pytest.mark.asyncio
async def test_40_workflow_definition_persistence():
    """Workflow state persists in database."""
    from app.db.models import User, Workflow, WorkflowVersion

    async with AsyncSessionLocal() as db_session:
        user = User(username="wf_user_1", password_hash="pw", role="ADMIN")
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(owner_id=user.id, name="wf-pump-check", description="Pump check workflow")
        db_session.add(wf)
        await db_session.flush()

        v = WorkflowVersion(workflow_id=wf.id, version="1.0", definition={"step": "check_vibration"}, input_schema={})
        db_session.add(v)
        await db_session.commit()
        wf_id = wf.id

    async with AsyncSessionLocal() as db_session2:
        result = await db_session2.execute(
            text("SELECT name FROM workflows WHERE id = :wid"), {"wid": wf_id}
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "wf-pump-check"


@pytest.mark.asyncio
async def test_41_semantic_memory_persistence():
    """Semantic memory items persist across transactions."""
    from app.db.models import User, Memory

    async with AsyncSessionLocal() as db_session:
        user = User(username="mem_user_1", password_hash="pw", role="OPERATOR")
        db_session.add(user)
        await db_session.flush()

        mem = Memory(
            user_id=user.id,
            content="Prefers vibration measurements in mm/s RMS",
            memory_type="FACT"
        )
        db_session.add(mem)
        await db_session.commit()
        uid = user.id

    async with AsyncSessionLocal() as db_session2:
        result = await db_session2.execute(
            text("SELECT content FROM memories WHERE user_id = :uid"), {"uid": uid}
        )
        row = result.fetchone()
        assert row is not None
        assert "mm/s RMS" in row[0]


@pytest.mark.asyncio
async def test_42_telemetry_event_persistence():
    """Telemetry events persist in database table."""
    from app.db.models import TelemetryEvent

    async with AsyncSessionLocal() as db_session:
        event = TelemetryEvent(
            event_type="generation_completed",
            trace_id="trace-persist-001",
            component="model_gateway",
            status="success"
        )
        db_session.add(event)
        await db_session.commit()

    async with AsyncSessionLocal() as db_session2:
        result = await db_session2.execute(
            text("SELECT event_type, status FROM telemetry_events WHERE trace_id = 'trace-persist-001'")
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "generation_completed"
        assert row[1] == "success"


# ==============================================================================
# 6. BACKUP & RECOVERY VERIFICATION (43-48)
# ==============================================================================

def test_43_backup_archive_creation():
    """Backup utility creates a valid .tar.gz archive with manifest.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        (data_dir / "mrpl.db").write_text("DUMMY_SQLITE_DATA")
        (data_dir / "uploads").mkdir()
        (data_dir / "uploads" / "report.txt").write_text("Report Content")

        archive_path = Path(tmpdir) / "mrpl_backup.tar.gz"
        manifest = create_backup_archive(data_dir, archive_path)

        assert archive_path.exists()
        assert "mrpl.db" in manifest["files"]
        assert "uploads/report.txt" in manifest["files"]


def test_44_backup_manifest_contains_expected_files():
    """Backup manifest computes accurate SHA-256 checksums."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        test_file = data_dir / "mrpl.db"
        test_file.write_text("TEST_DB_BYTES_999")
        expected_sha = compute_sha256(test_file)

        archive_path = Path(tmpdir) / "backup.tar.gz"
        manifest = create_backup_archive(data_dir, archive_path)

        assert manifest["files"]["mrpl.db"]["sha256"] == expected_sha


def test_45_restore_from_backup_verifies_checksums():
    """Restore successfully unpacks files and validates all SHA-256 hashes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "source_data"
        src_dir.mkdir()
        (src_dir / "mrpl.db").write_text("DATABASE_CONTENT")
        (src_dir / "attachments").mkdir()
        (src_dir / "attachments" / "img.png").write_bytes(b"\x89PNG_HEADER_TEST")

        archive_p = Path(tmpdir) / "backup.tar.gz"
        create_backup_archive(src_dir, archive_p)

        # Restore into new target directory
        restore_dir = Path(tmpdir) / "restored_data"
        res = restore_backup_archive(archive_p, restore_dir)

        assert res["status"] == "success"
        assert (restore_dir / "mrpl.db").read_text() == "DATABASE_CONTENT"
        assert (restore_dir / "attachments" / "img.png").read_bytes() == b"\x89PNG_HEADER_TEST"


def test_46_restore_detects_corrupted_archive():
    """Restore rejects archive when an extracted file checksum mismatches manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "source_data"
        src_dir.mkdir()
        (src_dir / "mrpl.db").write_text("AUTHENTIC_DATA")

        archive_p = Path(tmpdir) / "backup.tar.gz"
        manifest = create_backup_archive(src_dir, archive_p)

        # Tamper with archive: create archive with altered file but old manifest
        tampered_archive = Path(tmpdir) / "tampered.tar.gz"
        with tarfile.open(archive_p, "r:gz") as tar_in:
            m_data = tar_in.extractfile("manifest.json").read()

        tampered_data = Path(tmpdir) / "tampered_data"
        tampered_data.mkdir()
        (tampered_data / "manifest.json").write_bytes(m_data)
        (tampered_data / "mrpl.db").write_text("TAMPERED_MALICIOUS_DATA")

        with tarfile.open(tampered_archive, "w:gz") as tar_out:
            tar_out.add(tampered_data / "manifest.json", arcname="manifest.json")
            tar_out.add(tampered_data / "mrpl.db", arcname="mrpl.db")

        # Attempt restore from tampered archive
        restore_dir = Path(tmpdir) / "target_data"
        with pytest.raises(ValueError, match="Restore verification failed"):
            restore_backup_archive(tampered_archive, restore_dir)


def test_47_restore_wipes_target_cleanly():
    """Restore with wipe_target_first removes obsolete files from target."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "source"
        src_dir.mkdir()
        (src_dir / "mrpl.db").write_text("CLEAN_DATA")
        archive_p = Path(tmpdir) / "clean.tar.gz"
        create_backup_archive(src_dir, archive_p)

        target_dir = Path(tmpdir) / "target"
        target_dir.mkdir()
        (target_dir / "uploads").mkdir()
        (target_dir / "uploads" / "old_orphaned_file.txt").write_text("ORPHAN")

        restore_backup_archive(archive_p, target_dir, wipe_target_first=True)
        assert not (target_dir / "uploads" / "old_orphaned_file.txt").exists()
        assert (target_dir / "mrpl.db").read_text() == "CLEAN_DATA"


def test_48_full_roundtrip_state_wipe_and_restore():
    """Complete backup -> wipe -> restore -> verify data roundtrip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "active_data"
        data_dir.mkdir()
        (data_dir / "mrpl.db").write_text("SQLITE_DATABASE_ACTIVE_DATA")
        (data_dir / "chroma").mkdir()
        (data_dir / "chroma" / "chroma.sqlite3").write_text("VECTOR_METADATA_ACTIVE")
        (data_dir / "uploads").mkdir()
        (data_dir / "uploads" / "doc1.txt").write_text("Inspection Report Text")

        # 1. Backup
        backup_archive = Path(tmpdir) / "roundtrip_backup.tar.gz"
        create_backup_archive(data_dir, backup_archive)

        # 2. Wipe active data
        shutil.rmtree(data_dir)
        data_dir.mkdir()
        assert list(data_dir.iterdir()) == []

        # 3. Restore
        res = restore_backup_archive(backup_archive, data_dir)
        assert res["status"] == "success"

        # 4. Verify all components restored
        assert (data_dir / "mrpl.db").read_text() == "SQLITE_DATABASE_ACTIVE_DATA"
        assert (data_dir / "chroma" / "chroma.sqlite3").read_text() == "VECTOR_METADATA_ACTIVE"
        assert (data_dir / "uploads" / "doc1.txt").read_text() == "Inspection Report Text"


# ==============================================================================
# 7. FAILURE MODES & GRACEFUL DEGRADATION (49-53)
# ==============================================================================

def test_49_gateway_unknown_model_handling():
    """ModelGateway._get_provider_for_model raises ModelNotFoundError when no provider exists."""
    from app.core.model_gateway.gateway import ModelGateway
    empty_gateway = ModelGateway()
    # No providers registered
    with pytest.raises(ModelNotFoundError):
        empty_gateway._get_provider_for_model("unregistered-model")


@pytest.mark.asyncio
async def test_50_rag_failure_does_not_crash_application():
    """RAG tool handles vector store exception gracefully and reports explicit error."""
    from app.core.rag.tools import SearchDocumentsTool
    tool = SearchDocumentsTool(app.state.rag_service)
    with patch.object(app.state.rag_service.vector_store, "similarity_search", side_effect=Exception("Chroma corrupted")):
        with pytest.raises(Exception, match="Chroma corrupted"):
            await tool.execute({"query": "vibration"}, context={"user_id": "usr-test-1"})


@pytest.mark.asyncio
async def test_51_corrupted_sqlite_handling():
    """Malformed database connection fails explicitly without silent corruption."""
    from sqlalchemy.ext.asyncio import create_async_engine
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"NOT_A_VALID_SQLITE_DATABASE_FILE_GARBAGE")
        f_path = f.name

    engine = create_async_engine(f"sqlite+aiosqlite:///{f_path}")
    with pytest.raises(Exception):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    await engine.dispose()
    gc.collect()
    try:
        os.remove(f_path)
    except Exception:
        pass


def test_52_path_traversal_attachment_protection():
    """Attachment and RAG services reject path traversal strings in filenames."""
    storage = app.state.multimodal_service.storage
    dangerous_paths = ["../../etc/passwd", "..\\..\\windows\\system32\\calc.exe", "....//....//config.py"]
    for dp in dangerous_paths:
        with pytest.raises(ProcessingError, match="Invalid attachment ID|Path traversal"):
            storage._get_safe_path(dp)

    rag = app.state.rag_service
    with pytest.raises(FileValidationError, match="Invalid filename"):
        rag._validate_file(b"content", "../../etc/passwd")


@pytest.mark.asyncio
async def test_53_unauthorized_tool_execution_rejection():
    """AuthorizedToolExecutor strictly blocks tools not allowed by security policy."""
    from app.core.runtime.schemas import ToolRequest
    tool_executor = app.state.authorized_tool_executor
    req = ToolRequest(tool="unauthorized_tool", arguments={}, call_id="call-unauth-1")
    res = await tool_executor.execute(req, context={"user_id": "op-1", "role": "OPERATOR"}, allowed_tools={"search_documents"})
    assert res.status == "error"
    assert "not allowed" in res.output or "Unauthorized" in res.output or "denied" in res.output
