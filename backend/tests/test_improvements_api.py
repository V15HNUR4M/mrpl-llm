import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.main import app
from app.core.config import settings

@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient):
    app.state.model_gateway.register_model_route(settings.DEFAULT_CHAT_MODEL, "fake")
    await async_client.post("/api/v1/auth/register", json={"username": "improve_user", "password": "password123"})
    login_resp = await async_client.post("/api/v1/auth/login", data={"username": "improve_user", "password": "password123"})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_auto_title_generation_and_persistence(async_client: AsyncClient, auth_headers):
    # 1. Create a new conversation (defaults to "New Conversation")
    create_res = await async_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "New Conversation"}
    )
    assert create_res.status_code == 201
    conv_id = create_res.json()["id"]
    assert create_res.json()["title"] == "New Conversation"

    # 2. Run agent with first message: "What is the storage capacity of SRV-DB01?"
    run_res = await async_client.post(
        "/api/v1/agents/general_agent/run",
        headers=auth_headers,
        json={
            "conversation_id": conv_id,
            "message": "What is the storage capacity of SRV-DB01?"
        }
    )
    assert run_res.status_code == 200

    # 3. Verify conversation title is automatically updated persistently
    get_res = await async_client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert get_res.status_code == 200
    updated_title = get_res.json()["title"]
    assert updated_title == "SRV-DB01 Storage Capacity"

    # 4. Send second message: title should NOT change
    run_res2 = await async_client.post(
        "/api/v1/agents/general_agent/run",
        headers=auth_headers,
        json={
            "conversation_id": conv_id,
            "message": "Can you also check the temperature?"
        }
    )
    assert run_res2.status_code == 200
    get_res2 = await async_client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert get_res2.json()["title"] == "SRV-DB01 Storage Capacity"


@pytest.mark.asyncio
async def test_markdown_file_generation_and_download(async_client: AsyncClient, auth_headers):
    # 1. Create conversation
    create_res = await async_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "New Conversation"}
    )
    conv_id = create_res.json()["id"]

    # 2. Normal question should NOT generate a file
    norm_res = await async_client.post(
        "/api/v1/agents/general_agent/run",
        headers=auth_headers,
        json={
            "conversation_id": conv_id,
            "message": "What is SRV-DB01?"
        }
    )
    assert norm_res.status_code == 200

    msgs_res = await async_client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    items = msgs_res.json()["items"]
    last_asst_msg = [m for m in items if m["role"] == "assistant"][-1]
    msg_meta = last_asst_msg.get("metadata_") or last_asst_msg.get("metadata") or {}
    assert "generated_file" not in msg_meta

    # 3. Explicit request for a markdown file
    file_req_prompt = "Create a Markdown report summarizing the infrastructure report and give me the file."
    gen_res = await async_client.post(
        "/api/v1/agents/general_agent/run",
        headers=auth_headers,
        json={
            "conversation_id": conv_id,
            "message": file_req_prompt
        }
    )
    assert gen_res.status_code == 200

    # Verify assistant message has generated_file metadata
    msgs_res2 = await async_client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    items2 = msgs_res2.json()["items"]
    file_asst_msg = [m for m in items2 if m["role"] == "assistant"][-1]
    file_msg_meta = file_asst_msg.get("metadata_") or file_asst_msg.get("metadata") or {}
    assert "generated_file" in file_msg_meta
    file_info = file_msg_meta["generated_file"]
    file_id = file_info["file_id"]
    assert file_info["filename"].endswith(".md")
    assert "infrastructure" in file_info["filename"]

    # 4. Download file via authenticated endpoint
    dl_res = await async_client.get(f"/api/v1/files/download/{file_id}", headers=auth_headers)
    assert dl_res.status_code == 200
    assert "text/markdown" in dl_res.headers.get("content-type", "")
    assert "attachment" in dl_res.headers.get("content-disposition", "")
    assert len(dl_res.content) > 0

    # 5. Download non-existent or invalid file
    bad_res = await async_client.get("/api/v1/files/download/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert bad_res.status_code == 404

    traversal_res = await async_client.get("/api/v1/files/download/../../etc/passwd", headers=auth_headers)
    assert traversal_res.status_code in (400, 404)
