import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport

from app.main import app, lifespan
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.uow import UnitOfWork
from app.services.conversation import ConversationService
from app.core.runtime.tool_executor import (
    Tool, ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor,
    AuthorizationPolicy
)
from app.core.runtime.schemas import ToolRequest, ToolResult

class LiveAdminTool(Tool):
    @property
    def name(self) -> str:
        return "live_admin_tool"
    @property
    def description(self) -> str:
        return "Admin only live tool"
    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.ADMIN
    @property
    def input_schema(self):
        return {"type": "object"}
    async def execute(self, arguments, context):
        return ToolResult(output="live_admin_success", status="success")

async def run_live_verification():
    async with lifespan(app):
        transport = ASGITransport(app=app)
        results = {}

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register User A and User B
            u_a_name = f"user_a_{uuid.uuid4().hex[:6]}"
            u_b_name = f"user_b_{uuid.uuid4().hex[:6]}"
            
            await client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"username": u_a_name, "password": "Password123!", "email": f"{u_a_name}@example.com"}
            )
            await client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"username": u_b_name, "password": "Password123!", "email": f"{u_b_name}@example.com"}
            )

            # 1. User A login
            login_a = await client.post(
                f"{settings.API_V1_STR}/auth/login",
                data={"username": u_a_name, "password": "Password123!"}
            )
            token_a = login_a.json()["access_token"]
            results["1_user_a_login"] = {"status": login_a.status_code, "has_token": bool(token_a)}

            # 2. User B login
            login_b = await client.post(
                f"{settings.API_V1_STR}/auth/login",
                data={"username": u_b_name, "password": "Password123!"}
            )
            token_b = login_b.json()["access_token"]
            results["2_user_b_login"] = {"status": login_b.status_code, "has_token": bool(token_b)}

            # Create Conversation for User A
            c_a = await client.post(
                f"{settings.API_V1_STR}/conversations",
                json={"title": "User A Private Conversation"},
                headers={"Authorization": f"Bearer {token_a}"}
            )
            conv_a_id = c_a.json()["id"]

            # 3. User A accesses own resource -> PASS
            read_own = await client.get(
                f"{settings.API_V1_STR}/conversations/{conv_a_id}",
                headers={"Authorization": f"Bearer {token_a}"}
            )
            results["3_user_a_accesses_own_resource"] = {"status": read_own.status_code, "title": read_own.json().get("title")}

            # 4. User A accesses User B resource -> DENIED (User B creates conv, User A tries to read)
            c_b = await client.post(
                f"{settings.API_V1_STR}/conversations",
                json={"title": "User B Private Conversation"},
                headers={"Authorization": f"Bearer {token_b}"}
            )
            conv_b_id = c_b.json()["id"]
            a_access_b = await client.get(
                f"{settings.API_V1_STR}/conversations/{conv_b_id}",
                headers={"Authorization": f"Bearer {token_a}"}
            )
            results["4_user_a_accesses_user_b_resource"] = {"status": a_access_b.status_code, "detail": a_access_b.json()}

            # 5. User B accesses User A resource -> DENIED
            b_access_a = await client.get(
                f"{settings.API_V1_STR}/conversations/{conv_a_id}",
                headers={"Authorization": f"Bearer {token_b}"}
            )
            results["5_user_b_accesses_user_a_resource"] = {"status": b_access_a.status_code, "detail": b_access_a.json()}

            # 6. Normal user accesses admin endpoint -> DENIED (403)
            user_admin_ep = await client.post(
                f"{settings.API_V1_STR}/observability/cleanup?max_age_days=30&max_rows=100",
                headers={"Authorization": f"Bearer {token_a}"}
            )
            results["6_normal_user_accesses_admin_endpoint"] = {"status": user_admin_ep.status_code}

            # 7. Admin accesses authorized admin endpoint -> PASS (200)
            login_admin = await client.post(
                f"{settings.API_V1_STR}/auth/login",
                data={"username": settings.FIRST_SUPERUSER, "password": settings.FIRST_SUPERUSER_PASSWORD}
            )
            token_admin = login_admin.json()["access_token"]
            admin_ep = await client.post(
                f"{settings.API_V1_STR}/observability/cleanup?max_age_days=30&max_rows=100",
                headers={"Authorization": f"Bearer {token_admin}"}
            )
            results["7_admin_accesses_admin_endpoint"] = {"status": admin_ep.status_code, "body": admin_ep.json()}

            # 8. Unauthorized tool execution -> DENIED
            reg = ToolRegistry()
            reg.register(LiveAdminTool())
            auth_exec = AuthorizedToolExecutor(LocalToolExecutor(reg))
            tool_denied = await auth_exec.execute(
                ToolRequest(call_id="live-1", tool="live_admin_tool", arguments={}),
                context={"user_id": "user_a", "role": "USER"}
            )
            results["8_unauthorized_tool_execution"] = {"status": tool_denied.status, "output": tool_denied.output}

            # 9. Authorized tool execution -> PASS
            tool_allowed = await auth_exec.execute(
                ToolRequest(call_id="live-2", tool="live_admin_tool", arguments={}),
                context={"user_id": "admin_u", "role": "ADMIN"}
            )
            results["9_authorized_tool_execution"] = {"status": tool_allowed.status, "output": tool_allowed.output}

            # 10. Cross-user RAG retrieval -> DENIED (0 chunks for user B)
            unique_run_id = uuid.uuid4().hex[:8]
            file_bytes = f"Live RAG Secret Plant File for User A Only {unique_run_id}".encode()
            ingest_resp = await client.post(
                f"{settings.API_V1_STR}/knowledge/documents",
                files={"file": (f"live_rag_a_{unique_run_id}.txt", file_bytes, "text/plain")},
                headers={"Authorization": f"Bearer {token_a}"}
            )
            doc_a_id = ingest_resp.json()["document_id"]
            
            search_b = await client.post(
                f"{settings.API_V1_STR}/knowledge/search",
                json={"query": "Live RAG Secret Plant", "top_k": 5},
                headers={"Authorization": f"Bearer {token_b}"}
            )
            results["10_cross_user_rag_retrieval"] = {
                "status": search_b.status_code,
                "results_count_for_user_b": len(search_b.json())
            }

            # 11. Cross-user attachment access -> DENIED (404)
            from app.db.models import Attachment
            att_id = str(uuid.uuid4())
            uow = UnitOfWork(session_factory=AsyncSessionLocal)
            async with uow:
                u_a_db = await uow.users.get_by_username(u_a_name)
                att = Attachment(
                    id=att_id,
                    owner_id=u_a_db.id,
                    filename="live_attachment_a.png",
                    media_type="image/png",
                    size_bytes=50,
                    checksum="xyz",
                    storage_path="",
                    processing_status="READY"
                )
                uow.attachments.add(att)
                await uow.commit()

            b_access_att = await client.get(
                f"{settings.API_V1_STR}/attachments/{att_id}",
                headers={"Authorization": f"Bearer {token_b}"}
            )
            results["11_cross_user_attachment_access"] = {"status": b_access_att.status_code}

            # 12. Cross-user workflow access -> DENIED (404)
            from app.db.models import Workflow
            wf_id = str(uuid.uuid4())
            async with uow:
                wf = Workflow(id=wf_id, owner_id=u_a_db.id, name="User A Live Workflow", description="Private")
                uow.workflows.add(wf)
                await uow.commit()

            b_access_wf = await client.get(
                f"{settings.API_V1_STR}/workflows/{wf_id}",
                headers={"Authorization": f"Bearer {token_b}"}
            )
            results["12_cross_user_workflow_access"] = {"status": b_access_wf.status_code}

        print("=== LIVE SECURITY VERIFICATION RESULTS ===")
        for k, v in results.items():
            print(f"{k}: {v}")

if __name__ == "__main__":
    asyncio.run(run_live_verification())
