from typing import Callable, AsyncContextManager
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repository import (
    UserRepository, ConversationRepository, MessageRepository, 
    AuditEventRepository, ConversationSummaryRepository, MemoryRepository,
    WorkflowRepository, WorkflowVersionRepository, WorkflowRunRepository,
    AttachmentRepository, TelemetryEventRepository
)

class UnitOfWork:
    def __init__(self, session_factory: Callable[..., AsyncContextManager[AsyncSession]]):
        self._session_factory = session_factory
        self.session: AsyncSession = None
        
        self.users: UserRepository = None
        self.conversations: ConversationRepository = None
        self.messages: MessageRepository = None
        self.audit: AuditEventRepository = None
        self.summaries: ConversationSummaryRepository = None
        self.semantic_memories: MemoryRepository = None
        
        self.workflows: WorkflowRepository = None
        self.workflow_versions: WorkflowVersionRepository = None
        self.workflow_runs: WorkflowRunRepository = None
        
        self.attachments: AttachmentRepository = None
        self.telemetry_events: TelemetryEventRepository = None

    async def __aenter__(self):
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.conversations = ConversationRepository(self.session)
        self.messages = MessageRepository(self.session)
        self.audit = AuditEventRepository(self.session)
        self.summaries = ConversationSummaryRepository(self.session)
        self.semantic_memories = MemoryRepository(self.session)
        
        self.workflows = WorkflowRepository(self.session)
        self.workflow_versions = WorkflowVersionRepository(self.session)
        self.workflow_runs = WorkflowRunRepository(self.session)
        self.attachments = AttachmentRepository(self.session)
        self.telemetry_events = TelemetryEventRepository(self.session)
        
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        if exc_type:
            await self.rollback()
        else:
            await self.commit()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()

# Dependency provider
from app.db.database import AsyncSessionLocal

def get_uow():
    return UnitOfWork(session_factory=AsyncSessionLocal)
