from typing import Generic, TypeVar, Type, Optional, List, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, update, func, or_

ModelType = TypeVar("ModelType")

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: Any) -> Optional[ModelType]:
        result = await self.session.execute(select(self.model).filter(self.model.id == id))
        return result.scalars().first()

    def add(self, obj: ModelType):
        self.session.add(obj)

    async def create(self, obj_in: dict) -> ModelType:
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        # Flush to get the ID, but don't commit (UnitOfWork handles commit)
        await self.session.flush()
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: dict) -> ModelType:
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def delete(self, id: Any) -> bool:
        result = await self.session.execute(delete(self.model).where(self.model.id == id))
        await self.session.flush()
        return result.rowcount > 0

from app.db.models import User, Conversation, Message, AuditEvent, ConversationSummary, Memory

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(select(self.model).filter(self.model.username == username))
        return result.scalars().first()

    async def get_by_email(self, email: str) -> Optional[User]:
        if not email:
            return None
        result = await self.session.execute(select(self.model).filter(self.model.email == email))
        return result.scalars().first()

    async def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None
    ) -> Tuple[List[User], int]:
        stmt = select(self.model)
        count_stmt = select(func.count(self.model.id))

        if role:
            stmt = stmt.filter(self.model.role == role.upper())
            count_stmt = count_stmt.filter(self.model.role == role.upper())
        if is_active is not None:
            stmt = stmt.filter(self.model.is_active == is_active)
            count_stmt = count_stmt.filter(self.model.is_active == is_active)
        if search and search.strip():
            term = f"%{search.strip()}%"
            filter_search = or_(
                self.model.username.ilike(term),
                self.model.email.ilike(term),
                self.model.display_name.ilike(term)
            )
            stmt = stmt.filter(filter_search)
            count_stmt = count_stmt.filter(filter_search)

        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        stmt = stmt.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        items = list(res.scalars().all())

        return items, total

class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def list_for_user(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Conversation]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.user_id == user_id)
            .order_by(self.model.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

class MessageRepository(BaseRepository[Message]):
    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def list_older_messages(self, conversation_id: str, start_seq: int, end_seq: int) -> List[Message]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.conversation_id == conversation_id)
            .filter(self.model.sequence_number > start_seq)
            .filter(self.model.sequence_number <= end_seq)
            .order_by(self.model.sequence_number.asc())
        )
        return list(result.scalars().all())

    async def list_by_conversation(self, conversation_id: str, limit: int = 50, offset: int = 0) -> List[Message]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.conversation_id == conversation_id)
            .order_by(self.model.sequence_number.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_recent_by_conversation(self, conversation_id: str, limit: int = 10) -> List[Message]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.conversation_id == conversation_id)
            .order_by(self.model.sequence_number.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages
        
class AuditEventRepository(BaseRepository[AuditEvent]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditEvent, session)

class ConversationSummaryRepository(BaseRepository[ConversationSummary]):
    def __init__(self, session: AsyncSession):
        super().__init__(ConversationSummary, session)

    async def get_by_conversation_id(self, conversation_id: str) -> Optional[ConversationSummary]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.conversation_id == conversation_id)
        )
        return result.scalars().first()

class MemoryRepository(BaseRepository[Memory]):
    def __init__(self, session: AsyncSession):
        super().__init__(Memory, session)

    async def list_active_by_user(self, user_id: str, limit: int = 50) -> List[Memory]:
        """
        Retrieves active semantic memories for a user, bounded by a reasonable limit
        and ordered deterministically (newest updated first, then by id).
        """
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.user_id == user_id)
            .filter(self.model.is_active == True)
            .order_by(self.model.updated_at.desc(), self.model.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

from app.db.models import Workflow, WorkflowVersion, WorkflowRun

class WorkflowRepository(BaseRepository[Workflow]):
    def __init__(self, session: AsyncSession):
        super().__init__(Workflow, session)

    async def list_for_owner(self, owner_id: str) -> List[Workflow]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.owner_id == owner_id)
            .order_by(self.model.updated_at.desc())
        )
        return list(result.scalars().all())

class WorkflowVersionRepository(BaseRepository[WorkflowVersion]):
    def __init__(self, session: AsyncSession):
        super().__init__(WorkflowVersion, session)

    async def get_by_workflow_and_version(self, workflow_id: str, version: str) -> Optional[WorkflowVersion]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.workflow_id == workflow_id)
            .filter(self.model.version == version)
        )
        return result.scalars().first()

class WorkflowRunRepository(BaseRepository[WorkflowRun]):
    def __init__(self, session: AsyncSession):
        super().__init__(WorkflowRun, session)

    async def list_for_user(self, user_id: str) -> List[WorkflowRun]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.user_id == user_id)
            .order_by(self.model.started_at.desc())
        )
        return list(result.scalars().all())

from app.db.models import Attachment, TelemetryEvent
from datetime import datetime, timedelta, timezone

class AttachmentRepository(BaseRepository[Attachment]):
    def __init__(self, session: AsyncSession):
        super().__init__(Attachment, session)

    async def list_for_owner(self, owner_id: str) -> List[Attachment]:
        result = await self.session.execute(
            select(self.model)
            .filter(self.model.owner_id == owner_id)
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

class TelemetryEventRepository(BaseRepository[TelemetryEvent]):
    def __init__(self, session: AsyncSession):
        super().__init__(TelemetryEvent, session)

    async def query_events(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        component: Optional[str] = None,
        event_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TelemetryEvent]:
        query = select(self.model)
        
        # User isolation: non-admins can only view events where user_id matches
        if not is_admin:
            if not user_id:
                return []
            query = query.filter(self.model.user_id == user_id)
        elif user_id:
            query = query.filter(self.model.user_id == user_id)

        if component:
            query = query.filter(self.model.component == component)
        if event_type:
            query = query.filter(self.model.event_type == event_type)
        if correlation_id:
            query = query.filter(self.model.correlation_id == correlation_id)
        if status:
            query = query.filter(self.model.status == status)

        query = query.order_by(self.model.timestamp.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_for_user(
        self,
        event_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Optional[TelemetryEvent]:
        query = select(self.model).filter(self.model.id == event_id)
        if not is_admin:
            if not user_id:
                return None
            query = query.filter(self.model.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def count_events(self, user_id: Optional[str] = None, is_admin: bool = False) -> int:
        from sqlalchemy import func
        query = select(func.count(self.model.id))
        if not is_admin:
            if not user_id:
                return 0
            query = query.filter(self.model.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def cleanup_retention(self, max_age_days: int = 30, max_rows: int = 50000) -> int:
        deleted_count = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        
        # 1. Delete events older than max_age_days
        res = await self.session.execute(
            delete(self.model).where(self.model.timestamp < cutoff_date)
        )
        deleted_count += res.rowcount or 0
        
        # 2. Check total row count; if exceeds max_rows, prune oldest
        from sqlalchemy import func
        total_res = await self.session.execute(select(func.count(self.model.id)))
        total_rows = total_res.scalar() or 0
        
        if total_rows > max_rows:
            excess = total_rows - max_rows
            # Find timestamp of the Nth oldest excess record
            subq = (
                select(self.model.id)
                .order_by(self.model.timestamp.asc())
                .limit(excess)
            )
            subq_res = await self.session.execute(subq)
            excess_ids = list(subq_res.scalars().all())
            if excess_ids:
                del_res = await self.session.execute(
                    delete(self.model).where(self.model.id.in_(excess_ids))
                )
                deleted_count += del_res.rowcount or 0

        await self.session.flush()
        return deleted_count
