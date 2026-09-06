from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.errors import MRPLAPIException, mrpl_exception_handler
from app.db.database import engine, Base
from app.api.v1.endpoints import auth, conversations, messages, generation, agents, knowledge, workflows, attachments, observability
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
    # Initialize Model Gateway
    gateway = ModelGateway()
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
        vector_store=vector_store
    )
    app.state.rag_service = rag_service
    
    # Initialize Tool Registry
    tool_registry = ToolRegistry()
    tool_registry.register(SearchDocumentsTool(rag_service))
    tool_registry.register(GetDocumentTool(rag_service))
    
    local_tool_executor = LocalToolExecutor(tool_registry)
    authorized_tool_executor = AuthorizedToolExecutor(local_tool_executor)

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
    
    app.state.agent_registry = registry
    
    # Initialize Harness with AuthorizedToolExecutor
    context_engine = ContextEngine()
    app.state.agent_harness = AgentHarness(registry, context_engine, gateway, authorized_tool_executor)

    # Initialize DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Create first superuser
    from app.db.database import AsyncSessionLocal
    uow = UnitOfWork(session_factory=AsyncSessionLocal)
    async with uow:
        auth_service = AuthService(uow)
        existing = await uow.users.get_by_username(settings.FIRST_SUPERUSER)
        if not existing:
            await auth_service.create_user({
                "username": settings.FIRST_SUPERUSER,
                "password": settings.FIRST_SUPERUSER_PASSWORD,
                "role": "ADMIN"
            })
            await uow.commit()

    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(MRPLAPIException, mrpl_exception_handler)

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

# Abstraction for Background Tasks
@app.post(f"{settings.API_V1_STR}/test_background_task")
async def test_background_task(background_tasks: BackgroundTasks):
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

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(conversations.router, prefix=f"{settings.API_V1_STR}/conversations", tags=["conversations"])
app.include_router(messages.router, prefix=f"{settings.API_V1_STR}/conversations/{{conversation_id}}/messages", tags=["messages"])
app.include_router(generation.router, prefix=f"{settings.API_V1_STR}/generate", tags=["generation"])
app.include_router(agents.router, prefix=f"{settings.API_V1_STR}/agents", tags=["agents"])
app.include_router(knowledge.router, prefix=f"{settings.API_V1_STR}/knowledge", tags=["knowledge"])
app.include_router(workflows.router, prefix=f"{settings.API_V1_STR}/workflows", tags=["workflows"])
app.include_router(attachments.router, prefix=f"{settings.API_V1_STR}/attachments", tags=["attachments"])
app.include_router(observability.router, prefix=f"{settings.API_V1_STR}/observability", tags=["observability"])
