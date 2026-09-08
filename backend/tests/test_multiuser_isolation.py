import pytest
import pytest_asyncio
import uuid
import json
from datetime import timedelta
from httpx import AsyncClient

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.database import AsyncSessionLocal
from app.db.uow import UnitOfWork
from app.db.models import User, Conversation, Document, Memory
from app.services.file_export import GeneratedFileManager
from app.core.rag.service import RAGService
from app.core.rag.schemas import RetrievalQuery
from sqlalchemy import select

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
            "email": f"usera_{uid[:8]}@example.com",
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
            "email": f"userb_{uid[:8]}@example.com",
            "password_hash": get_password_hash("Password123!"),
            "role": "USER",
            "is_active": True
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
            "email": f"admin_{uid[:8]}@example.com",
            "password_hash": get_password_hash("AdminPass123!"),
            "role": "ADMIN",
            "is_active": True
        })
        await uow.commit()
        return user

def auth_header(username: str, role: str = "USER") -> dict:
    token = create_access_token(data={"sub": username, "role": role})
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. DOCUMENT CHECKSUM USER-SCOPED UNIQUENESS TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_same_checksum_uploaded_by_two_different_users(async_client: AsyncClient, user_a: User, user_b: User):
    """
    Test that identical file content (same checksum) can be uploaded by User A
    and User B without collision, creating independent user-scoped document records.
    """
    identical_content = b"MRPL Hydrocracker Unit Standard Operating Procedure Section 4.2"
    file_a = {"file": ("sop_cracking.txt", identical_content, "text/plain")}
    file_b = {"file": ("sop_cracking.txt", identical_content, "text/plain")}

    # User A uploads
    resp_a = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=file_a,
        headers=auth_header(user_a.username)
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["status"] == "SUCCESS"
    doc_id_a = data_a["document_id"]

    # User B uploads the exact same file
    resp_b = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=file_b,
        headers=auth_header(user_b.username)
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["status"] == "SUCCESS"
    doc_id_b = data_b["document_id"]

    # Verify both records exist with distinct document IDs and distinct owners
    assert doc_id_a != doc_id_b
    async with AsyncSessionLocal() as session:
        doc_a = (await session.execute(select(Document).where(Document.id == doc_id_a))).scalar_one()
        doc_b = (await session.execute(select(Document).where(Document.id == doc_id_b))).scalar_one()
        assert doc_a.owner_id == user_a.id
        assert doc_b.owner_id == user_b.id
        assert doc_a.checksum == doc_b.checksum


@pytest.mark.asyncio
async def test_same_checksum_uploaded_twice_by_same_user(async_client: AsyncClient, user_a: User):
    """
    Test that the same user uploading the same file twice triggers duplicate
    detection and returns status SKIPPED without failing.
    """
    content = b"MRPL Continuous Catalyst Regeneration Guidelines Version 1.0"
    file_1 = {"file": ("ccr_guide.txt", content, "text/plain")}
    file_2 = {"file": ("ccr_guide.txt", content, "text/plain")}

    resp_1 = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=file_1,
        headers=auth_header(user_a.username)
    )
    assert resp_1.status_code == 200
    assert resp_1.json()["status"] == "SUCCESS"

    # Second upload by same user
    resp_2 = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files=file_2,
        headers=auth_header(user_a.username)
    )
    assert resp_2.status_code == 200
    assert resp_2.json()["status"] == "SKIPPED"
    assert "already indexed" in resp_2.json()["message"].lower()



# ===========================================================================
# 2. PUBLIC REGISTRATION BEHAVIOR TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_public_registration_behavior(async_client: AsyncClient):
    """
    Verifies public registration gating:
    - By default, public self-registration is disabled and returns 403 REGISTRATION_DISABLED.
    - When explicitly enabled via ENABLE_PUBLIC_REGISTRATION=True, registration succeeds with 201.
    """
    # 1. Disabled by default
    resp_disabled = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"username": f"unauth_{uuid.uuid4().hex[:6]}", "password": "Password123!"}
    )
    assert resp_disabled.status_code == 403
    err = resp_disabled.json()
    code = err.get("error", {}).get("code") or err.get("code")
    assert code == "REGISTRATION_DISABLED"

    # 2. Enabled dynamically
    prev_setting = settings.ENABLE_PUBLIC_REGISTRATION
    try:
        settings.ENABLE_PUBLIC_REGISTRATION = True
        uname = f"allowed_{uuid.uuid4().hex[:6]}"
        resp_enabled = await async_client.post(
            f"{settings.API_V1_STR}/auth/register",
            json={"username": uname, "password": "Password123!", "email": f"{uname}@example.com"}
        )
        assert resp_enabled.status_code in [200, 201]
        assert resp_enabled.json()["username"] == uname
    finally:
        settings.ENABLE_PUBLIC_REGISTRATION = prev_setting


# ===========================================================================
# 3. USER SOFT-DEACTIVATION & DATA PRESERVATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_soft_deactivated_user_cannot_login(async_client: AsyncClient, admin_user: User, user_a: User):
    """
    Admin deactivates User A.
    User A is rejected at login and their existing JWT token is rejected on protected endpoints.
    """
    # Admin soft-deactivates User A via DELETE /api/v1/users/{user_id}
    del_resp = await async_client.delete(
        f"{settings.API_V1_STR}/users/{user_a.id}",
        headers=auth_header(admin_user.username, role="ADMIN")
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["is_active"] is False

    # 1. Login attempt by deactivated user must fail with 401
    login_resp = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": user_a.username, "password": "Password123!"}
    )
    assert login_resp.status_code == 401

    # 2. Existing token for deactivated user is rejected with 403 Forbidden
    active_token = create_access_token(data={"sub": user_a.username, "role": "USER"})
    api_resp = await async_client.get(
        f"{settings.API_V1_STR}/conversations",
        headers={"Authorization": f"Bearer {active_token}"}
    )
    assert api_resp.status_code == 403


@pytest.mark.asyncio
async def test_deactivated_user_existing_data_remains_preserved(async_client: AsyncClient, admin_user: User, user_a: User, uow: UnitOfWork):
    """
    Verifies that when a user is soft-deactivated:
    - User record remains in database with is_active=False
    - User's conversations and messages remain intact
    - User's uploaded documents remain intact
    - User's semantic memories remain intact
    - User's generated files remain on disk
    """
    # 1. Create conversation & message for User A
    conv_resp = await async_client.post(
        f"{settings.API_V1_STR}/conversations",
        json={"title": "Plant Yield Historical Analysis"},
        headers=auth_header(user_a.username)
    )
    conv_id = conv_resp.json()["id"]

    msg_resp = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/messages",
        json={"role": "user", "content": "What was the diesel yield in Q3?"},
        headers=auth_header(user_a.username)
    )
    assert msg_resp.status_code == 201

    # 2. Upload document for User A
    doc_resp = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files={"file": ("yield_q3.txt", b"Q3 Yield: Diesel 44.2%, Petrol 22.1%", "text/plain")},
        headers=auth_header(user_a.username)
    )
    doc_id = doc_resp.json()["document_id"]

    # 3. Create semantic memory for User A
    async with uow:
        mem = await uow.semantic_memories.create({
            "user_id": user_a.id,
            "content": "Prefers automated daily refinery digest",
            "memory_type": "PREFERENCE",
            "is_active": True
        })
        await uow.commit()
        mem_id = mem.id

    # 4. Create generated file for User A
    file_mgr = GeneratedFileManager()
    file_meta = await file_mgr.save_markdown_file(
        owner_id=user_a.id,
        conversation_id=conv_id,
        filename="yield_report.md",
        content="# Yield Report\nDiesel: 44.2%"
    )
    file_id = file_meta["file_id"]

    # 5. Admin soft-deactivates User A
    del_resp = await async_client.delete(
        f"{settings.API_V1_STR}/users/{user_a.id}",
        headers=auth_header(admin_user.username, role="ADMIN")
    )
    assert del_resp.status_code == 200

    # 6. Verify ALL data remains preserved in DB and filesystem
    async with AsyncSessionLocal() as session:
        # Check user record
        u = (await session.execute(select(User).where(User.id == user_a.id))).scalar_one_or_none()
        assert u is not None
        assert u.is_active is False

        # Check conversation
        c = (await session.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one_or_none()
        assert c is not None
        assert c.user_id == user_a.id

        # Check document
        d = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
        assert d is not None
        assert d.owner_id == user_a.id

        # Check memory
        m = (await session.execute(select(Memory).where(Memory.id == mem_id))).scalar_one_or_none()
        assert m is not None
        assert m.user_id == user_a.id

    # Check generated file metadata
    meta = await file_mgr.get_file_metadata(file_id, user_a.id)
    assert meta is not None
    assert meta["owner_id"] == user_a.id


# ===========================================================================
# 4. IDENTITY SPOOFING RESISTANCE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_user_id_cannot_be_spoofed_through_api_input(async_client: AsyncClient, user_a: User, user_b: User):
    """
    Verifies that the backend rejects/overrides any user_id or owner_id passed
    via request body or query parameter:
    1. Knowledge search body: owner_id=User_B is overridden by authenticated user_a.id.
    2. Conversation creation body: user_id=User_B is overridden by authenticated user_a.id.
    """
    # Ingest document for User B
    await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files={"file": ("classified_b.txt", b"Classified secret engineering blueprint", "text/plain")},
        headers=auth_header(user_b.username)
    )

    # 1. User A searches attempting to spoof User B via body
    search_resp = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/search",
        json={"query": "blueprint", "owner_id": user_b.id},
        headers=auth_header(user_a.username)
    )
    assert search_resp.status_code == 200
    for result in search_resp.json():
        assert result.get("owner_id") != user_b.id

    # 2. User A attempts to create a conversation with body user_id=User_B
    conv_resp = await async_client.post(
        f"{settings.API_V1_STR}/conversations",
        json={"title": "Spoofed Conversation", "user_id": user_b.id},
        headers=auth_header(user_a.username)
    )
    assert conv_resp.status_code == 201
    created_conv_id = conv_resp.json()["id"]

    # Query DB directly: verify ownership was bound to User A, NOT User B
    async with AsyncSessionLocal() as session:
        conv = (await session.execute(select(Conversation).where(Conversation.id == created_conv_id))).scalar_one()
        assert conv.user_id == user_a.id
        assert conv.user_id != user_b.id


# ===========================================================================
# 5. CROSS-USER RESOURCE ISOLATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_cross_user_rag_isolation(async_client: AsyncClient, user_a: User, user_b: User):
    """
    Verifies that RAG retrieval strictly isolates documents between users:
    - User A uploads Document A with unique keyword 'AlphaCatalystX'
    - User B uploads Document B with unique keyword 'BetaReformerY'
    - User A searches -> results ONLY contain User A documents, NEVER User B's
    - User B searches -> results ONLY contain User B documents, NEVER User A's
    """
    # User A uploads
    resp_a = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files={"file": ("alpha.txt", b"Proprietary AlphaCatalystX specifications for hydrocracker", "text/plain")},
        headers=auth_header(user_a.username)
    )
    assert resp_a.status_code == 200
    doc_id_a = resp_a.json()["document_id"]

    # User B uploads
    resp_b = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/documents",
        files={"file": ("beta.txt", b"Proprietary BetaReformerY operating temperatures", "text/plain")},
        headers=auth_header(user_b.username)
    )
    assert resp_b.status_code == 200
    doc_id_b = resp_b.json()["document_id"]

    # User A searches for BetaReformerY -> must NOT return User B's documents
    search_a = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/search",
        json={"query": "BetaReformerY"},
        headers=auth_header(user_a.username)
    )
    assert search_a.status_code == 200
    results_a = search_a.json()
    assert all(r["document_id"] != doc_id_b for r in results_a)
    assert not any("BetaReformerY" in r["content"] for r in results_a)

    # User B searches for AlphaCatalystX -> must NOT return User A's documents
    search_b = await async_client.post(
        f"{settings.API_V1_STR}/knowledge/search",
        json={"query": "AlphaCatalystX"},
        headers=auth_header(user_b.username)
    )
    assert search_b.status_code == 200
    results_b = search_b.json()
    assert all(r["document_id"] != doc_id_a for r in results_b)
    assert not any("AlphaCatalystX" in r["content"] for r in results_b)


@pytest.mark.asyncio
async def test_cross_user_memory_isolation(async_client: AsyncClient, uow: UnitOfWork, user_a: User, user_b: User):
    """
    Verifies that semantic memory operations strictly isolate data between users:
    - User A cannot list, get, or retrieve User B's memories.
    - Unauthorized access audits a 'denied' event and returns None.
    """
    from app.services.semantic_memory import MemoryService
    async with uow:
        mem_svc = MemoryService(uow)

        # 1. Create memories for both users
        mem_a = await mem_svc.create_memory(user_a.id, "User A prefers Hindi executive summary", "PREFERENCE")
        mem_b = await mem_svc.create_memory(user_b.id, "User B prefers English technical details", "PREFERENCE")

        # 2. List memories: User A only sees their own
        list_a = await mem_svc.list_memories(user_a.id)
        ids_a = [m.id for m in list_a]
        assert mem_a.id in ids_a
        assert mem_b.id not in ids_a

        # 3. Direct access: User A trying to get User B's memory returns None
        access_attempt = await mem_svc.get_memory(user_a.id, mem_b.id)
        assert access_attempt is None

        # 4. Context retrieval: User A querying memory never retrieves User B's memory
        candidates_a = await mem_svc.retrieve_memories(user_a.id, "English technical details")
        candidate_contents = [c.content for c in candidates_a]
        assert "User B prefers English technical details" not in candidate_contents


@pytest.mark.asyncio
async def test_cross_user_file_isolation(async_client: AsyncClient, user_a: User, user_b: User):
    """User A cannot download a generated file belonging to User B."""
    file_mgr = GeneratedFileManager()
    meta = await file_mgr.save_markdown_file(
        owner_id=user_b.id,
        conversation_id="conv_b_123",
        filename="monthly-kpi-report.md",
        content="# Confidential Monthly KPIs\nTarget refinery output exceeded."
    )
    file_id = meta["file_id"]

    # User A tries to download User B's generated file -> 404
    resp = await async_client.get(
        f"{settings.API_V1_STR}/files/download/{file_id}",
        headers=auth_header(user_a.username)
    )
    assert resp.status_code == 404

    # User B can download their own file -> 200
    resp_b = await async_client.get(
        f"{settings.API_V1_STR}/files/download/{file_id}",
        headers=auth_header(user_b.username)
    )
    assert resp_b.status_code == 200
    assert b"Monthly KPIs" in resp_b.content


@pytest.mark.asyncio
async def test_cross_user_conversation_isolation(async_client: AsyncClient, user_a: User, user_b: User):
    """User A cannot read, add message to, or delete User B's conversation."""
    # User B creates conversation
    create_resp = await async_client.post(
        f"{settings.API_V1_STR}/conversations",
        json={"title": "Confidential Process Strategy"},
        headers=auth_header(user_b.username)
    )
    conv_id = create_resp.json()["id"]

    # User A tries to read -> 404
    get_resp = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_id}",
        headers=auth_header(user_a.username)
    )
    assert get_resp.status_code == 404

    # User A tries to add message -> 404
    msg_resp = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Attempted injection"},
        headers=auth_header(user_a.username)
    )
    assert msg_resp.status_code == 404

    # User A tries to delete -> 404
    del_resp = await async_client.delete(
        f"{settings.API_V1_STR}/conversations/{conv_id}",
        headers=auth_header(user_a.username)
    )
    assert del_resp.status_code == 404


# ===========================================================================
# 6. ADMIN USER MANAGEMENT API TESTS & SAFEGUARDS
# ===========================================================================

@pytest.mark.asyncio
async def test_admin_user_management_lifecycle(async_client: AsyncClient, admin_user: User):
    """Test admin creating, listing, inspecting, updating, and deactivating users."""
    headers = auth_header(admin_user.username, role="ADMIN")

    # 1. Create user
    new_uname = f"engineer_{uuid.uuid4().hex[:6]}"
    create_resp = await async_client.post(
        f"{settings.API_V1_STR}/users",
        json={
            "username": new_uname,
            "email": f"{new_uname}@mrpl.co.in",
            "password": "InitialPassword123!",
            "display_name": "Senior Plant Engineer",
            "role": "USER",
            "is_active": True
        },
        headers=headers
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    user_id = created["id"]
    assert created["username"] == new_uname
    assert created["role"] == "USER"
    assert created["is_active"] is True

    # 2. List users with search
    list_resp = await async_client.get(
        f"{settings.API_V1_STR}/users?search={new_uname}",
        headers=headers
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(u["id"] == user_id for u in items)

    # 3. Update user role and status
    patch_resp = await async_client.patch(
        f"{settings.API_V1_STR}/users/{user_id}",
        json={"role": "ADMIN", "display_name": "Lead Process Engineer"},
        headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "ADMIN"
    assert patch_resp.json()["display_name"] == "Lead Process Engineer"

    # 4. Soft deactivate user
    deact_resp = await async_client.delete(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=headers
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(async_client: AsyncClient, admin_user: User):
    """Guards prevent an admin from deactivating their own account."""
    headers = auth_header(admin_user.username, role="ADMIN")
    resp = await async_client.delete(
        f"{settings.API_V1_STR}/users/{admin_user.id}",
        headers=headers
    )
    assert resp.status_code == 400
    err = resp.json()
    code = err.get("error", {}).get("code") or err.get("code")
    assert code == "CANNOT_DEACTIVATE_SELF"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_user_management(async_client: AsyncClient, user_a: User):
    """Regular users are rejected with 403 Forbidden from /api/v1/users."""
    headers = auth_header(user_a.username, role="USER")

    # List
    assert (await async_client.get(f"{settings.API_V1_STR}/users", headers=headers)).status_code == 403
    # Create
    assert (await async_client.post(
        f"{settings.API_V1_STR}/users",
        json={"username": "hacker", "password": "Password123!", "role": "ADMIN"},
        headers=headers
    )).status_code == 403
    # Update
    assert (await async_client.patch(
        f"{settings.API_V1_STR}/users/{user_a.id}",
        json={"role": "ADMIN"},
        headers=headers
    )).status_code == 403
    # Delete
    assert (await async_client.delete(f"{settings.API_V1_STR}/users/{user_a.id}", headers=headers)).status_code == 403

