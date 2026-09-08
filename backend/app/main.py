from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.errors import MRPLAPIException, mrpl_exception_handler
from app.db.database import engine, Base
import app.db.models  # Ensure models are registered on Base.metadata
from app.api.v1.endpoints import (
    auth, conversations, messages, generation, agents, knowledge,
    workflows, attachments, observability, evaluation, health, files, users
)
from app.services.auth import AuthService
from app.db.uow import UnitOfWork, get_uow
from app.core.model_gateway.gateway import ModelGateway
from app.providers.ollama import OllamaProvider
from app.providers.fake import FakeProvider
from app.core.agent.registry import AgentRegistry, AgentDefinition
from app.core.context_engine.engine import ContextEngine
from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor
from app.core.runtime.harness import AgentHarness

# RAG specific imports
from app.core.rag.parser import ParserRegistry
from app.core.rag.chunking import TextChunker
from app.core.rag.embeddings import FakeEmbeddingProvider, OllamaEmbeddingProvider
from app.core.rag.vector_store import ChromaVectorStore
from app.core.rag.service import RAGService
from app.core.rag.tools import SearchDocumentsTool, GetDocumentTool
from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.observability.service import get_observability_service
    obs_service = get_observability_service()
    app.state.observability_service = obs_service

    # Initialize Model Gateway
    gateway = ModelGateway(observability_service=obs_service)
    gateway.register_provider("ollama", OllamaProvider(base_url=settings.OLLAMA_BASE_URL))
    gateway.register_provider("fake", FakeProvider())
    gateway.register_model_route(settings.DEFAULT_CHAT_MODEL, "ollama")
    gateway.register_model_route("fake-model", "fake")
    app.state.model_gateway = gateway
    
    # Initialize RAG Layer
    parser_registry = ParserRegistry()
    chunker = TextChunker(chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
    
    # Use configured embedding provider - no silent fallbacks in runtime
    if settings.EMBEDDING_PROVIDER == "ollama":
        embedding_provider = OllamaEmbeddingProvider(
            model=settings.DEFAULT_EMBEDDING_MODEL,
            base_url=settings.OLLAMA_BASE_URL
        )
    elif settings.EMBEDDING_PROVIDER == "fake":
        embedding_provider = FakeEmbeddingProvider()
    else:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}")

    vector_store = ChromaVectorStore()
    
    rag_service = RAGService(
        parser_registry=parser_registry,
        chunker=chunker,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        observability_service=obs_service
    )
    app.state.rag_service = rag_service
    
    # Initialize Tool Registry
    tool_registry = ToolRegistry()
    tool_registry.register(SearchDocumentsTool(rag_service))
    tool_registry.register(GetDocumentTool(rag_service))

    # Register Excel Deterministic Tools
    from app.core.excel import (
        ReadWorkbookTool,
        InspectSheetTool,
        ReadRangeTool,
        AggregateDataTool,
        FilterRowsTool,
        DetectDuplicatesTool,
        DetectMissingValuesTool,
        CreateWorkbookTool,
        WriteCellsTool,
        AddFormulaTool,
        FormatRangeTool,
        SaveWorkbookTool,
    )
    tool_registry.register(ReadWorkbookTool())
    tool_registry.register(InspectSheetTool())
    tool_registry.register(ReadRangeTool())
    tool_registry.register(AggregateDataTool())
    tool_registry.register(FilterRowsTool())
    tool_registry.register(DetectDuplicatesTool())
    tool_registry.register(DetectMissingValuesTool())
    tool_registry.register(CreateWorkbookTool())
    tool_registry.register(WriteCellsTool())
    tool_registry.register(AddFormulaTool())
    tool_registry.register(FormatRangeTool())
    tool_registry.register(SaveWorkbookTool())
    
    local_tool_executor = LocalToolExecutor(tool_registry)
    authorized_tool_executor = AuthorizedToolExecutor(local_tool_executor, observability_service=obs_service)
    app.state.authorized_tool_executor = authorized_tool_executor

    # Initialize Agent Registry
    registry = AgentRegistry()
    registry.register(AgentDefinition(
        agent_id="general_agent",
        name="General Agent",
        description="A general purpose AI assistant with knowledge base access",
        version="1.0",
        instructions=(
            "You are a helpful assistant for the MRPL plant system. When the user asks about equipment, pumps, "
            "inspections, maintenance, or procedures, answer accurately and comprehensively using ONLY the facts present "
            "in the provided reference context. Do not fabricate or extrapolate information. If the provided reference "
            "documents do not contain the answer, state clearly that the indexed knowledge base does not contain this information."
        ),
        tool_permissions={"allowed": ["search_documents", "get_document"]},
        context_policy={"rag": True}
    ))
    registry.register(AgentDefinition(
        agent_id="analysis_agent",
        name="Analysis Agent",
        description="Analyzes data and reports",
        version="1.0",
        instructions="You analyze provided data and use tools.",
        tool_permissions={"allowed": ["search_documents", "get_document"]},
        context_policy={"rag": True}
    ))
    registry.register(AgentDefinition(
        agent_id="disabled_agent",
        name="Disabled Agent",
        description="This agent is disabled",
        version="1.0",
        instructions="You are disabled.",
        status="disabled"
    ))
    
    # Track 4: Document Agent
    registry.register(AgentDefinition(
        agent_id="document_agent",
        name="Document Agent",
        description="Knowledge base assistant",
        version="1.0",
        instructions=(
            "You are a helpful assistant that answers questions based on the provided retrieved context. "
            "Always base your responses strictly on the retrieved documents. If the reference context does not "
            "contain the answer, state clearly that the indexed knowledge base does not contain this information."
        ),
        tool_permissions={"allowed": ["search_documents", "get_document"]},
        context_policy={"rag": True}
    ))

    # Sovereign Excel Specialist Agent
    registry.register(AgentDefinition(
        agent_id="excel_agent",
        name="Excel Agent",
        description="Specialized agent for reading, analyzing, calculating, and modifying Excel spreadsheets locally",
        version="1.0",
        instructions=(
            "You are the MRPL Excel Specialist. Your workflow is: "
            "Inspect → execute deterministic tool operations → verify results → provide concise evidence-based answer. "
            "Rely strictly on deterministic tool outputs for arithmetic and aggregations; do not perform manual calculations. "
            "When a task requires creating or generating a workbook, you MUST invoke the create_workbook tool with clean headers and rows. "
            "Never claim a workbook has been created or saved unless the tool execution successfully generated and registered the file."
        ),
        tool_permissions={
            "allowed": [
                "read_workbook",
                "inspect_sheet",
                "read_range",
                "aggregate_data",
                "filter_rows",
                "detect_duplicates",
                "detect_missing_values",
                "create_workbook",
                "write_cells",
                "add_formula",
                "format_range",
                "save_workbook",
            ]
        },
        context_policy={"rag": False}
    ))
    
    app.state.agent_registry = registry
    
    # Initialize Harness with AuthorizedToolExecutor
    context_engine = ContextEngine()
    app.state.agent_harness = AgentHarness(registry, context_engine, gateway, authorized_tool_executor, observability_service=obs_service)

    # Initialize DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration for user-scoped checksum uniqueness in SQLite
        try:
            from sqlalchemy import text
            res = await conn.execute(text("SELECT sql FROM sqlite_master WHERE type='index' AND name='ix_documents_checksum'"))
            row = res.fetchone()
            if row and row[0] and "UNIQUE" in row[0].upper():
                await conn.execute(text("DROP INDEX IF EXISTS ix_documents_checksum"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_checksum ON documents (checksum)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_document_owner_checksum ON documents (owner_id, checksum)"))
        except Exception as mig_err:
            import logging
            logging.getLogger("mrpl.db").warning("Index migration check: %s", mig_err)
        
    # Create or update first superuser
    from app.db.database import AsyncSessionLocal
    uow = UnitOfWork(session_factory=AsyncSessionLocal)
    try:
        async with uow:
            auth_service = AuthService(uow)
            existing = await uow.users.get_by_username(settings.FIRST_SUPERUSER)
            if not existing:
                await auth_service.create_user_by_admin({
                    "username": settings.FIRST_SUPERUSER,
                    "password": settings.FIRST_SUPERUSER_PASSWORD,
                    "role": "ADMIN",
                    "is_active": True
                })
                await uow.commit()
            elif existing.role != "ADMIN":
                await uow.users.update(existing, {"role": "ADMIN"})
                await uow.commit()
    except Exception as e:
        import logging
        logging.getLogger("mrpl.main").error(f"Superuser bootstrap error: {e}")

    # Ensure system_eval_runner exists and clean up legacy EVAL_DOC_* documents assigned to real users
    try:
        from app.core.evaluation.corpus import get_or_create_system_eval_user, SYSTEM_EVAL_USER_ID
        await get_or_create_system_eval_user()

        from app.db.models import Document
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            stmt = select(Document).where(
                Document.filename.like("EVAL_DOC_%"),
                (Document.owner_id != SYSTEM_EVAL_USER_ID) | (Document.access_scope != "EVALUATION")
            )
            res = await session.execute(stmt)
            legacy_eval_docs = res.scalars().all()
            for ldoc in legacy_eval_docs:
                try:
                    await app.state.rag_service.vector_store.delete_by_document_id(ldoc.id)
                except Exception:
                    pass
                await session.delete(ldoc)
            if legacy_eval_docs:
                await session.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Evaluation cleanup warning: %s", e)

    # Initialize Workflow, Memory, and Multimodal services on app.state
    from app.core.workflow.engine import WorkflowEngine
    from app.services.semantic_memory import MemoryService
    from app.core.multimodal.service import MultimodalService
    app.state.uow = uow
    app.state.workflow_engine = WorkflowEngine(uow, app.state.agent_harness, authorized_tool_executor, observability_service=obs_service)
    app.state.memory_service = MemoryService(uow)
    app.state.multimodal_service = MultimodalService(uow, observability_service=obs_service)
    gateway._multimodal_service = app.state.multimodal_service
    from app.core.runtime.state_manager import get_agent_state_manager
    state_mgr = get_agent_state_manager()
    app.state.agent_state_manager = state_mgr
    from app.core.runtime.generation_manager import GenerationManager
    app.state.generation_manager = GenerationManager(state_manager=state_mgr, obs_service=obs_service)

    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_OPENAPI else None,
    redoc_url="/redoc" if settings.ENABLE_OPENAPI else None,
    openapi_url="/openapi.json" if settings.ENABLE_OPENAPI else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(MRPLAPIException, mrpl_exception_handler)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' http://localhost:* http://127.0.0.1:* ws:; "
        "frame-ancestors 'none';"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    import uuid
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    correlation_id = request.headers.get("X-Correlation-ID") or request_id
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# Abstraction for Background Tasks - Gated in production
@app.post(f"{settings.API_V1_STR}/test_background_task")
async def test_background_task(background_tasks: BackgroundTasks):
    if not settings.ENABLE_TEST_ENDPOINTS:
        raise MRPLAPIException(code="NOT_FOUND", message="Endpoint not found", status_code=404)
    from app.core.tasks import TaskQueue
    queue = TaskQueue(background_tasks)

    def background_job():
        import time
        import logging
        logging.getLogger("mrpl").info("Background task started")
        time.sleep(2)
        logging.getLogger("mrpl").info("Background task finished")
        
    queue.enqueue(background_job)
    return {"status": "Accepted for async processing"}

# Health probes (both at /health/live and /api/v1/health/live for orchestrator / client flexibility)
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(health.router, prefix=f"{settings.API_V1_STR}/health", tags=["health"])

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(conversations.router, prefix=f"{settings.API_V1_STR}/conversations", tags=["conversations"])
app.include_router(messages.router, prefix=f"{settings.API_V1_STR}/conversations/{{conversation_id}}/messages", tags=["messages"])
app.include_router(generation.router, prefix=f"{settings.API_V1_STR}/generate", tags=["generation"])
app.include_router(agents.router, prefix=f"{settings.API_V1_STR}/agents", tags=["agents"])
app.include_router(knowledge.router, prefix=f"{settings.API_V1_STR}/knowledge", tags=["knowledge"])
app.include_router(workflows.router, prefix=f"{settings.API_V1_STR}/workflows", tags=["workflows"])
app.include_router(attachments.router, prefix=f"{settings.API_V1_STR}/attachments", tags=["attachments"])
app.include_router(observability.router, prefix=f"{settings.API_V1_STR}/observability", tags=["observability"])
app.include_router(evaluation.router, prefix=f"{settings.API_V1_STR}/evaluation", tags=["evaluation"])
app.include_router(files.router, prefix=f"{settings.API_V1_STR}/files", tags=["files"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
