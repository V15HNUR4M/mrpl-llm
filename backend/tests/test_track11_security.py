import pytest
import pytest_asyncio
import uuid
from datetime import timedelta
from jose import jwt
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.core.errors import MRPLAPIException
from app.dependencies import require_admin
from app.db.database import AsyncSessionLocal
from app.db.uow import UnitOfWork
from app.db.models import User, Conversation, Attachment, Workflow, WorkflowVersion, WorkflowRun
from app.services.auth import AuthService
from app.services.conversation import ConversationService
from app.services.semantic_memory import MemoryService
from app.core.runtime.tool_executor import (
    Tool, ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor,
    AuthorizationPolicy
)
from app.core.runtime.schemas import ToolRequest, ToolResult
from app.core.runtime.mcp_adapter import MCPAdapter, MCPServerClient
from app.core.multimodal.storage import LocalStorageProvider
from app.core.multimodal.schemas import ProcessingError, MediaValidationError
from app.core.multimodal.validators import validate_image
from app.core.observability.redaction import sanitize_metadata
from app.core.rag.schemas import RetrievalQuery
from app.core.rag.service import RAGService
from app.core.rag.tools import SearchDocumentsTool, GetDocumentTool
from app.core.rag.errors import DocumentNotFoundError

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def uow():
    return UnitOfWork(session_factory=AsyncSessionLocal)

@pytest_asyncio.fixture
async def user_a(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"user_a_{uid[:8]}",
            "password_hash": get_password_hash("Password123!"),
            "role": "USER",
            "is_active": True
        })
        await uow.commit()
        return user

@pytest_asyncio.fixture
async def user_b(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"user_b_{uid[:8]}",
            "password_hash": get_password_hash("Password123!"),
            "role": "USER",
            "is_active": True
        })
        await uow.commit()
        return user

@pytest_asyncio.fixture
async def inactive_user(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"inactive_{uid[:8]}",
            "password_hash": get_password_hash("Password123!"),
            "role": "USER",
            "is_active": False
        })
        await uow.commit()
        return user

@pytest_asyncio.fixture
async def admin_user(uow: UnitOfWork):
    uid = str(uuid.uuid4())
    async with uow:
        user = await uow.users.create({
            "id": uid,
            "username": f"admin_{uid[:8]}",
            "password_hash": get_password_hash("AdminPass123!"),
            "role": "ADMIN",
            "is_active": True
        })
        await uow.commit()
        return user

def make_token(username: str, role: str = "USER", expires_delta: timedelta = None) -> str:
    return create_access_token(data={"sub": username, "role": role}, expires_delta=expires_delta)


# ===========================================================================
# 1. AUTHENTICATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_auth_invalid_password(async_client: AsyncClient, user_a: User):
    resp = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": user_a.username, "password": "WrongPassword!"}
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()

@pytest.mark.asyncio
async def test_auth_nonexistent_user(async_client: AsyncClient):
    resp = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "non_existent_user_999", "password": "AnyPassword123!"}
    )
    assert resp.status_code == 401
    # Generic error: does not leak whether user exists
    err = resp.json()
    code = err.get("error", {}).get("code") or err.get("code")
    assert code == "AUTH_INVALID_CREDENTIALS"

@pytest.mark.asyncio
async def test_auth_disabled_user_login(async_client: AsyncClient, inactive_user: User):
    resp = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": inactive_user.username, "password": "Password123!"}
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()

@pytest.mark.asyncio
async def test_auth_expired_jwt(async_client: AsyncClient, user_a: User):
    expired_token = make_token(user_a.username, expires_delta=timedelta(seconds=-60))
    resp = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_malformed_jwt(async_client: AsyncClient):
    resp = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": "Bearer malformed.token.signature"}
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_tampered_jwt_signature(async_client: AsyncClient, user_a: User):
    tampered_token = jwt.encode({"sub": user_a.username}, "wrong-secret-key", algorithm="HS256")
    resp = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_protected_endpoint_without_header(async_client: AsyncClient):
    resp = await async_client.get(f"{settings.API_V1_STR}/auth/me")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_protected_conversations_without_auth(async_client: AsyncClient):
    resp = await async_client.get(f"{settings.API_V1_STR}/conversations")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_disabled_user_token_rejected_on_access(async_client: AsyncClient, inactive_user: User):
    token = make_token(inactive_user.username)
    resp = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_auth_passwords_never_returned_in_api(async_client: AsyncClient, user_a: User):
    token = make_token(user_a.username)
    resp = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "password" not in data
    assert "password_hash" not in data


# ===========================================================================
# 2. AUTHORIZATION & RBAC TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_admin_endpoint_denied_for_normal_user(async_client: AsyncClient, user_a: User):
    token = make_token(user_a.username, role="USER")
    resp = await async_client.post(
        f"{settings.API_V1_STR}/observability/cleanup?max_age_days=30&max_rows=1000",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_admin_endpoint_allowed_for_admin_user(async_client: AsyncClient, admin_user: User):
    token = make_token(admin_user.username, role="ADMIN")
    resp = await async_client.post(
        f"{settings.API_V1_STR}/observability/cleanup?max_age_days=30&max_rows=1000",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "success"

@pytest.mark.asyncio
async def test_require_admin_dependency_unit(user_a: User, admin_user: User):
    with pytest.raises(MRPLAPIException) as exc_info:
        await require_admin(current_user=user_a)
    assert exc_info.value.status_code == 403

    passed_admin = await require_admin(current_user=admin_user)
    assert passed_admin.id == admin_user.id

@pytest.mark.asyncio
async def test_registration_creates_standard_user(async_client: AsyncClient):
    uname = f"newuser_{uuid.uuid4().hex[:6]}"
    resp = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"username": uname, "password": "SecurePassword123!", "email": f"{uname}@example.com"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "USER"


# ===========================================================================
# 3. RESOURCE OWNERSHIP / USER ISOLATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_cross_user_conversation_read_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    # User A creates a conversation
    async with uow:
        conv_service = ConversationService(uow)
        conv = await conv_service.create_conversation(user_a.id, "User A Secret Chat")
        conv_id = conv.id
        await uow.commit()

    # User B tries to read User A's conversation
    token_b = make_token(user_b.username)
    resp = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cross_user_message_list_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        conv_service = ConversationService(uow)
        conv = await conv_service.create_conversation(user_a.id, "User A Messages")
        conv_id = conv.id
        await conv_service.add_message(conv_id, user_a.id, {"role": "user", "content": "Confidential A"})
        await uow.commit()

    token_b = make_token(user_b.username)
    resp = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cross_user_message_create_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        conv_service = ConversationService(uow)
        conv = await conv_service.create_conversation(user_a.id, "User A Only")
        conv_id = conv.id
        await uow.commit()

    token_b = make_token(user_b.username)
    resp = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Impersonation attempt"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cross_user_attachment_read_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    att_id = str(uuid.uuid4())
    async with uow:
        att = Attachment(
            id=att_id,
            owner_id=user_a.id,
            filename="user_a.png",
            media_type="image/png",
            size_bytes=100,
            checksum="abc",
            storage_path="",
            processing_status="READY"
        )
        uow.attachments.add(att)
        await uow.commit()

    token_b = make_token(user_b.username)
    resp = await async_client.get(
        f"{settings.API_V1_STR}/attachments/{att_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cross_user_attachment_delete_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    att_id = str(uuid.uuid4())
    async with uow:
        att = Attachment(
            id=att_id,
            owner_id=user_a.id,
            filename="user_a.png",
            media_type="image/png",
            size_bytes=100,
            checksum="abc",
            storage_path="",
            processing_status="READY"
        )
        uow.attachments.add(att)
        await uow.commit()

    token_b = make_token(user_b.username)
    resp = await async_client.delete(
        f"{settings.API_V1_STR}/attachments/{att_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cross_user_workflow_read_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    wf_id = str(uuid.uuid4())
    async with uow:
        wf = Workflow(id=wf_id, owner_id=user_a.id, name="Secret WF", description="Private")
        uow.workflows.add(wf)
        await uow.commit()

    token_b = make_token(user_b.username)
    resp = await async_client.get(
        f"{settings.API_V1_STR}/workflows/{wf_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cross_user_workflow_run_denied(async_client: AsyncClient, user_a: User, user_b: User, uow: UnitOfWork):
    wf_id = str(uuid.uuid4())
    async with uow:
        wf = Workflow(id=wf_id, owner_id=user_a.id, name="Secret WF", description="Private")
        uow.workflows.add(wf)
        await uow.commit()

    token_b = make_token(user_b.username)
    resp = await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/run",
        json={},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404


# ===========================================================================
# 4. RAG SECURITY TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_cross_user_rag_search_isolated(async_client: AsyncClient, user_a: User, user_b: User):
    token_a = make_token(user_a.username)
    token_b = make_token(user_b.username)

    # Ingest document for user A
    content = b"Confidential Sovereign Plant Operations Document Alpha"
    files = {"file": ("secret_ops_alpha.txt", content, "text/plain")}
    resp = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=files,
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200

    # User B searches: must return 0 results
    search_resp = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/search",
        json={"query": "Sovereign Plant Operations Alpha", "top_k": 5},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert search_resp.status_code == 200
    assert len(search_resp.json()) == 0

@pytest.mark.asyncio
async def test_cross_user_document_delete_denied(async_client: AsyncClient, user_a: User, user_b: User):
    token_a = make_token(user_a.username)
    token_b = make_token(user_b.username)

    files = {"file": ("user_a_doc.txt", b"Content for user A", "text/plain")}
    resp = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=files,
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200
    doc_id = resp.json()["document_id"]

    # User B tries to delete User A's document
    del_resp = await async_client.delete(
        f"{settings.API_V1_STR}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert del_resp.status_code == 404

    # Cleanup with user A
    cleanup = await async_client.delete(
        f"{settings.API_V1_STR}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert cleanup.status_code == 200

@pytest.mark.asyncio
async def test_deleted_document_unsearchable(async_client: AsyncClient, user_a: User):
    token_a = make_token(user_a.username)

    files = {"file": ("temporary_doc.txt", b"UniqueTerm999 Temporary Ingestion", "text/plain")}
    resp = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=files,
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200
    doc_id = resp.json()["document_id"]

    # Verify searchable
    search_1 = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/search",
        json={"query": "UniqueTerm999", "top_k": 5},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert len(search_1.json()) > 0

    # Delete
    del_resp = await async_client.delete(
        f"{settings.API_V1_STR}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert del_resp.status_code == 200

    # Search again: must return 0 results
    search_2 = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/search",
        json={"query": "UniqueTerm999", "top_k": 5},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert len(search_2.json()) == 0

@pytest.mark.asyncio
async def test_get_document_tool_owner_isolation(user_a: User, user_b: User):
    rag_service = app.state.rag_service
    tool = GetDocumentTool(rag_service)

    # Ingest doc for user A
    ingest_res = await rag_service.ingest_document(
        file_bytes=b"Document Alpha Data",
        filename="alpha_tool_test.txt",
        mime_type="text/plain",
        owner_id=user_a.id
    )

    # User B calls tool with user A's doc_id: returns 0 chunks
    res_b = await tool.execute({"document_id": ingest_res.document_id}, context={"user_id": user_b.id})
    assert len(res_b.context_candidates) == 0

    # User A calls tool: returns candidates
    res_a = await tool.execute({"document_id": ingest_res.document_id}, context={"user_id": user_a.id})
    assert len(res_a.context_candidates) > 0

    # Cleanup
    await rag_service.delete_document(ingest_res.document_id, owner_id=user_a.id)

@pytest.mark.asyncio
async def test_search_documents_tool_unauthenticated_denied():
    rag_service = app.state.rag_service
    tool = SearchDocumentsTool(rag_service)
    with pytest.raises(ValueError, match="Unauthorized"):
        await tool.execute({"query": "plant"}, context={})


# ===========================================================================
# 5. MEMORY SECURITY TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_cross_user_memory_read_denied(user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        mem_service = MemoryService(uow)
        mem_a = await mem_service.create_memory(user_a.id, "User A Secret Fact")

        # User B attempts to read User A's memory
        mem = await mem_service.get_memory(user_b.id, mem_a.id)
        assert mem is None

@pytest.mark.asyncio
async def test_cross_user_memory_update_denied(user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        mem_service = MemoryService(uow)
        mem_a = await mem_service.create_memory(user_a.id, "Original A Fact")

        updated = await mem_service.update_memory(user_b.id, mem_a.id, {"content": "Tampered"})
        assert updated is None

        # Verify original remains intact
        orig = await mem_service.get_memory(user_a.id, mem_a.id)
        assert orig.content == "Original A Fact"

@pytest.mark.asyncio
async def test_cross_user_memory_deactivate_denied(user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        mem_service = MemoryService(uow)
        mem_a = await mem_service.create_memory(user_a.id, "Important Fact")

        success = await mem_service.deactivate_memory(user_b.id, mem_a.id)
        assert success is False

        mem = await mem_service.get_memory(user_a.id, mem_a.id)
        assert mem.is_active is True

@pytest.mark.asyncio
async def test_cross_user_memory_retrieval_isolated(user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        mem_service = MemoryService(uow)
        await mem_service.create_memory(user_a.id, "User A Refinery KeywordSecret987")

        candidates_b = await mem_service.retrieve_memories(user_b.id, "KeywordSecret987")
        assert len(candidates_b) == 0

        candidates_a = await mem_service.retrieve_memories(user_a.id, "KeywordSecret987")
        assert len(candidates_a) == 1

@pytest.mark.asyncio
async def test_memory_update_prevents_user_id_reassignment(user_a: User, user_b: User, uow: UnitOfWork):
    async with uow:
        mem_service = MemoryService(uow)
        mem_a = await mem_service.create_memory(user_a.id, "Fact Owned by A")

        await mem_service.update_memory(user_a.id, mem_a.id, {"content": "Updated", "user_id": user_b.id})
        mem = await mem_service.get_memory(user_a.id, mem_a.id)
        assert mem.user_id == user_a.id


# ===========================================================================
# 6. TOOL & MCP SECURITY TESTS
# ===========================================================================

class DummyAdminTool(Tool):
    @property
    def name(self) -> str:
        return "admin_system_tool"
    @property
    def description(self) -> str:
        return "Admin only tool"
    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.ADMIN
    @property
    def input_schema(self):
        return {"type": "object"}
    async def execute(self, arguments, context):
        return ToolResult(output="admin_executed", status="success")

class DummyAuthTool(Tool):
    @property
    def name(self) -> str:
        return "auth_required_tool"
    @property
    def description(self) -> str:
        return "Auth only tool"
    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED
    @property
    def input_schema(self):
        return {"type": "object"}
    async def execute(self, arguments, context):
        return ToolResult(output="auth_executed", status="success")

@pytest.mark.asyncio
async def test_unauthorized_tool_denied_by_policy():
    reg = ToolRegistry()
    reg.register(DummyAuthTool())
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local)

    # Missing user_id in context
    req = ToolRequest(call_id="c1", tool="auth_required_tool", arguments={})
    res = await authorized.execute(req, context={})
    assert res.status == "error"
    assert "requires authentication" in res.output

@pytest.mark.asyncio
async def test_admin_tool_denied_for_normal_user():
    reg = ToolRegistry()
    reg.register(DummyAdminTool())
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local)

    req = ToolRequest(call_id="c2", tool="admin_system_tool", arguments={})
    res = await authorized.execute(req, context={"user_id": "user123", "role": "USER"})
    assert res.status == "error"
    assert "requires administrative privileges" in res.output

@pytest.mark.asyncio
async def test_admin_tool_allowed_for_admin_user():
    reg = ToolRegistry()
    reg.register(DummyAdminTool())
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local)

    req = ToolRequest(call_id="c3", tool="admin_system_tool", arguments={})
    res = await authorized.execute(req, context={"user_id": "admin123", "role": "ADMIN"})
    assert res.status == "success"
    assert res.output == "admin_executed"

@pytest.mark.asyncio
async def test_tool_denial_emits_audit_log(uow: UnitOfWork, user_a: User):
    reg = ToolRegistry()
    reg.register(DummyAdminTool())
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local, uow=uow)

    req = ToolRequest(call_id="c4", tool="admin_system_tool", arguments={})
    await authorized.execute(req, context={"user_id": user_a.id, "role": "USER"})

    async with uow:
        from app.db.models import AuditEvent
        from sqlalchemy.future import select
        res = await uow.audit.session.execute(
            select(AuditEvent).where(AuditEvent.user_id == user_a.id, AuditEvent.action == "tool_execution_denied")
        )
        audit_records = res.scalars().all()
        assert len(audit_records) >= 1

@pytest.mark.asyncio
async def test_disabled_tool_denied():
    reg = ToolRegistry()
    reg.register(DummyAuthTool())
    reg.disable("auth_required_tool")
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local)

    req = ToolRequest(call_id="c5", tool="auth_required_tool", arguments={})
    res = await authorized.execute(req, context={"user_id": "user123"})
    assert res.status == "error"
    assert "disabled" in res.output

@pytest.mark.asyncio
async def test_unregistered_tool_rejected():
    reg = ToolRegistry()
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local)

    req = ToolRequest(call_id="c6", tool="unknown_nonexistent_tool", arguments={})
    res = await authorized.execute(req, context={"user_id": "user123"})
    assert res.status == "error"
    assert "Unknown tool" in res.output

@pytest.mark.asyncio
async def test_mcp_adapter_inherits_authorization_policy():
    mcp_client = MCPServerClient("http://127.0.0.1:9999")
    mcp_tool = MCPAdapter(
        tool_name="mcp_admin_tool",
        tool_description="MCP Tool with ADMIN policy",
        tool_schema={"type": "object"},
        mcp_client=mcp_client,
        authorization_policy=AuthorizationPolicy.ADMIN
    )
    reg = ToolRegistry()
    reg.register(mcp_tool)
    local = LocalToolExecutor(reg)
    authorized = AuthorizedToolExecutor(local)

    req = ToolRequest(call_id="c7", tool="mcp_admin_tool", arguments={})
    res = await authorized.execute(req, context={"user_id": "user123", "role": "USER"})
    assert res.status == "error"
    assert "requires administrative privileges" in res.output


# ===========================================================================
# 7. MULTIMODAL & ATTACHMENT SECURITY TESTS
# ===========================================================================

def test_attachment_path_traversal_dot_dot_rejected():
    storage = LocalStorageProvider()
    with pytest.raises(ProcessingError, match="Invalid attachment ID"):
        storage._get_safe_path("../etc/passwd")

def test_attachment_path_traversal_backslash_rejected():
    storage = LocalStorageProvider()
    with pytest.raises(ProcessingError, match="Invalid attachment ID"):
        storage._get_safe_path("..\\windows\\system32")

def test_attachment_slash_in_id_rejected():
    storage = LocalStorageProvider()
    with pytest.raises(ProcessingError, match="Invalid attachment ID"):
        storage._get_safe_path("subfolder/file.png")

def test_validate_image_unsupported_format_rejected():
    with pytest.raises(MediaValidationError, match=r"Unsupported.*(signature|format)"):
        validate_image(b"MZ\x90\x00\x03\x00\x00\x00EXE_CONTENT")

def test_validate_image_corrupt_data_rejected():
    with pytest.raises(MediaValidationError):
        validate_image(b"\x89PNG\r\n\x1a\nCorruptPayloadWithoutProperChunks")

def test_validate_image_oversized_rejected():
    # Large empty payload exceeding byte limit
    oversized = b"\x00" * (15 * 1024 * 1024)
    with pytest.raises(MediaValidationError):
        validate_image(oversized)


# ===========================================================================
# 8. SECRETS & LOGGING PRIVACY TESTS
# ===========================================================================

def test_redaction_omits_passwords():
    raw_meta = {"user_id": "u1", "password": "supersecretpassword", "login_status": "ok"}
    sanitized = sanitize_metadata(raw_meta)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["user_id"] == "u1"

def test_redaction_omits_jwts_and_tokens():
    raw_meta = {"access_token": "eyJhbGciOi...", "secret_token": "tok123"}
    sanitized = sanitize_metadata(raw_meta)
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["secret_token"] == "[REDACTED]"

def test_redaction_omits_api_keys_and_cookies():
    raw_meta = {"api_key": "api_secret_999", "cookie": "sessionid=xyz"}
    sanitized = sanitize_metadata(raw_meta)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["cookie"] == "[REDACTED]"

def test_redaction_omits_raw_prompts_and_responses():
    raw_meta = {"prompt": "What is the secret formula?", "response": "The formula is 42"}
    sanitized = sanitize_metadata(raw_meta)
    assert sanitized["prompt"] == "[PROMPT_OMITTED]"
    assert sanitized["prompt_length"] == len("What is the secret formula?")
    assert sanitized["response"] == "[RESPONSE_OMITTED]"
    assert sanitized["response_length"] == len("The formula is 42")

def test_redaction_omits_base64_and_binary():
    raw_meta = {"images": ["image_bytes"], "base64": "data:image/png;base64,iVBORw0KGgo...", "raw_bytes": b"\x00\x01"}
    sanitized = sanitize_metadata(raw_meta)
    assert sanitized["images"] == "[BINARY_OMITTED]"
    assert sanitized["base64"] == "[BINARY_OMITTED]"
    assert sanitized["raw_bytes"] == "[BINARY_OMITTED]"


# ===========================================================================
# 9. HTTP SECURITY HEADERS & CORS TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_security_headers_present_on_api_response(async_client: AsyncClient):
    resp = await async_client.get(f"{settings.API_V1_STR}/observability/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "no-store" in resp.headers.get("Cache-Control", "")

@pytest.mark.asyncio
async def test_cors_disallows_unauthorized_origin(async_client: AsyncClient):
    resp = await async_client.options(
        f"{settings.API_V1_STR}/observability/health",
        headers={
            "Origin": "http://evil-attacker-site.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    # Origin is not in configured origins, so Access-Control-Allow-Origin must not be evil site
    allowed = resp.headers.get("access-control-allow-origin")
    assert allowed != "http://evil-attacker-site.com"

@pytest.mark.asyncio
async def test_cors_allows_configured_local_origin(async_client: AsyncClient):
    resp = await async_client.options(
        f"{settings.API_V1_STR}/observability/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
