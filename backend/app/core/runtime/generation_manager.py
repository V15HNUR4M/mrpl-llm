import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, AsyncGenerator
from collections import OrderedDict

from app.db.uow import UnitOfWork
from app.db.database import AsyncSessionLocal
from app.services.conversation import ConversationService
from app.core.runtime.schemas import RuntimeSession

logger = logging.getLogger("mrpl.generation")

class GenerationRecord:
    def __init__(
        self,
        generation_id: str,
        conversation_id: str,
        user_id: str,
        agent_id: str,
    ):
        self.generation_id = generation_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.agent_id = agent_id
        self.message_id: Optional[str] = None
        self.status: str = "running"  # running, completed, failed, cancelled
        self.partial_content: str = ""
        self.started_at: datetime = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.events_history: List[Dict[str, Any]] = []
        self._subscribers: Set[asyncio.Queue] = set()
        self._task: Optional[asyncio.Task] = None
        self._is_cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "message_id": self.message_id,
            "status": self.status,
            "partial_content": self.partial_content,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    def add_event(self, event: Dict[str, Any]):
        self.events_history.append(event)
        
        # Update state
        if event.get("type") == "text_delta":
            self.partial_content += event.get("text", "")
            
        # Dispatch to any active SSE subscribers
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except Exception as e:
                logger.debug(f"Failed to deliver event to subscriber: {e}")

    def add_subscriber(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def remove_subscriber(self, queue: asyncio.Queue):
        self._subscribers.discard(queue)


class GenerationManager:
    """
    Decoupled application-level generation manager.
    Runs generation tasks asynchronously and independently of the SSE HTTP connection.
    Ensures message persistence occurs even if the client disconnects.
    """
    def __init__(self, max_history: int = 100, state_manager=None, obs_service=None):
        self._generations: OrderedDict[str, GenerationRecord] = OrderedDict()
        self._max_history = max_history
        self._lock = asyncio.Lock()
        self._state_manager = state_manager
        self._obs_service = obs_service

    async def start_generation(
        self,
        agent,
        harness,
        conversation_id: str,
        user_id: str,
        message: str,
        recent_candidates: list,
        initial_title: Optional[str] = None
    ) -> GenerationRecord:
        generation_id = str(uuid.uuid4())
        record = GenerationRecord(
            generation_id=generation_id,
            conversation_id=conversation_id,
            user_id=user_id,
            agent_id=agent.agent_id
        )

        # Track live Running state
        if self._state_manager:
            self._state_manager.start_execution(agent.agent_id, generation_id)
        if self._obs_service:
            try:
                from app.core.observability.schemas import TelemetryEventCreate, EVENT_AGENT_RUN_STARTED
                asyncio.create_task(self._obs_service.emit_event(TelemetryEventCreate(
                    event_type=EVENT_AGENT_RUN_STARTED,
                    component="agent",
                    agent_id=agent.agent_id,
                    user_id=user_id,
                    session_id=conversation_id,
                    correlation_id=generation_id,
                    status="running",
                    metadata={"message_preview": message[:100], "agent_id": agent.agent_id}
                )))
            except Exception:
                pass

        if initial_title:
            record.add_event({
                "type": "title_updated",
                "title": initial_title,
                "conversation_id": conversation_id
            })

        async with self._lock:
            # Enforce history limit
            if len(self._generations) >= self._max_history:
                # Evict oldest completed/cancelled generation
                for gid, rec in list(self._generations.items()):
                    if rec.status in ("completed", "failed", "cancelled"):
                        del self._generations[gid]
                        break
            self._generations[generation_id] = record

        # Launch independent background task on current event loop
        task = asyncio.create_task(
            self._execute_generation_loop(
                record=record,
                agent=agent,
                harness=harness,
                message=message,
                recent_candidates=recent_candidates
            )
        )
        record._task = task
        return record

    async def _execute_generation_loop(
        self,
        record: GenerationRecord,
        agent,
        harness,
        message: str,
        recent_candidates: list
    ):
        session = RuntimeSession(
            session_id=record.generation_id,
            conversation_id=record.conversation_id,
            agent_id=agent.agent_id,
            agent_version=agent.version,
            user_id=record.user_id
        )

        final_answer = ""
        file_metadata = None
        try:
            record.add_event({"type": "session_created", "session_id": record.generation_id})

            async for event in harness.stream_execute(session, message, recent_candidates):
                if record._is_cancelled:
                    break
                if event.get("type") == "completed":
                    final_answer = event.get("final_answer", "")
                    continue
                record.add_event(event)

                # Check for tool-generated files (e.g. SaveWorkbookTool)
                if event.get("type") == "tool_completed":
                    tool_res = event.get("result")
                    if isinstance(tool_res, dict) and tool_res.get("file_id") and (tool_res.get("filename", "").endswith(".xlsx") or tool_res.get("file_type") == "xlsx"):
                        file_metadata = {
                            "file_id": tool_res["file_id"],
                            "filename": tool_res["filename"],
                            "file_type": "xlsx",
                            "mime_type": tool_res.get("mime_type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                            "size_bytes": tool_res.get("size_bytes", 0)
                        }
                        record.add_event({
                            "type": "file_generated",
                            "file": file_metadata
                        })

            if record._is_cancelled:
                record.status = "cancelled"
                record.completed_at = datetime.now(timezone.utc)
                record.add_event({"type": "error", "error": "Generation cancelled by user"})
                return

            final_text = final_answer or record.partial_content
            if final_text:
                if not file_metadata:
                    try:
                        from app.services.file_export import (
                            detect_file_generation_request,
                            derive_filename,
                            GeneratedFileManager,
                            export_to_markdown,
                            export_to_docx,
                            export_to_pdf,
                        )
                        req = detect_file_generation_request(message)
                        if req["requested"]:
                            file_mgr = GeneratedFileManager()
                            fmt = req["format"]
                            if fmt == "docx":
                                filename = derive_filename(message, ext=".docx")
                                docx_bytes = export_to_docx(final_text)
                                saved_info = await file_mgr.save_file(
                                    owner_id=record.user_id,
                                    conversation_id=record.conversation_id,
                                    filename=filename,
                                    content_bytes=docx_bytes,
                                    file_type="docx"
                                )
                                file_metadata = saved_info
                            elif fmt == "pdf":
                                filename = derive_filename(message, ext=".pdf")
                                pdf_bytes = export_to_pdf(final_text)
                                saved_info = await file_mgr.save_file(
                                    owner_id=record.user_id,
                                    conversation_id=record.conversation_id,
                                    filename=filename,
                                    content_bytes=pdf_bytes,
                                    file_type="pdf"
                                )
                                file_metadata = saved_info
                            elif fmt == "markdown":
                                filename = derive_filename(message, ext=".md")
                                saved_info = await file_mgr.save_markdown_file(
                                    owner_id=record.user_id,
                                    conversation_id=record.conversation_id,
                                    filename=filename,
                                    content=final_text
                                )
                                file_metadata = saved_info
                            elif fmt == "xlsx":
                                from app.core.excel.writers import create_workbook, save_workbook
                                from app.core.excel.table_parser import extract_tabular_data
                                filename = derive_filename(message, ext=".xlsx")
                                headers, rows = extract_tabular_data(final_text, session_events=record.events, user_input=message)
                                created = create_workbook(sheet_name="Data", headers=headers, rows=rows)
                                saved_info = await save_workbook(
                                    file_id=created["staging_file_id"],
                                    output_filename=filename,
                                    owner_id=record.user_id,
                                    conversation_id=record.conversation_id
                                )
                                file_metadata = saved_info

                            if file_metadata:
                                record.add_event({
                                    "type": "file_generated",
                                    "file": file_metadata
                                })
                    except Exception as e:
                        logger.error(f"Multi-format file export error: {e}")

                # Authoritative SQLite persistence - MUST succeed even if client disconnected
                new_uow = UnitOfWork(session_factory=AsyncSessionLocal)
                async with new_uow:
                    new_conv_service = ConversationService(new_uow)
                    msg_payload = {
                        "role": "assistant",
                        "content": final_text,
                        "agent_id": agent.agent_id
                    }
                    if file_metadata:
                        msg_payload["metadata_"] = {"generated_file": file_metadata}
                    saved = await new_conv_service.add_message(
                        record.conversation_id,
                        record.user_id,
                        msg_payload
                    )
                    if saved:
                        record.message_id = saved.id
                
            record.add_event({
                "type": "completed",
                "final_answer": final_text
            })
            record.status = "completed"
            record.completed_at = datetime.now(timezone.utc)

            # Mark state manager completed (Ready)
            if self._state_manager:
                self._state_manager.complete_execution(agent.agent_id, record.generation_id, success=True)
            if self._obs_service:
                try:
                    dur_ms = int((record.completed_at - record.started_at).total_seconds() * 1000) if record.started_at else None
                    from app.core.observability.schemas import TelemetryEventCreate, EVENT_AGENT_RUN_COMPLETED
                    asyncio.create_task(self._obs_service.emit_event(TelemetryEventCreate(
                        event_type=EVENT_AGENT_RUN_COMPLETED,
                        component="agent",
                        agent_id=agent.agent_id,
                        user_id=record.user_id,
                        session_id=record.conversation_id,
                        correlation_id=record.generation_id,
                        status="success",
                        duration_ms=dur_ms,
                        metadata={"agent_id": agent.agent_id, "final_answer_length": len(final_text)}
                    )))
                except Exception:
                    pass

        except asyncio.CancelledError:
            record.status = "cancelled"
            record.completed_at = datetime.now(timezone.utc)
            record.add_event({"type": "error", "error": "Generation cancelled by user"})
            logger.info(f"Generation {record.generation_id} cancelled")
            if self._state_manager:
                self._state_manager.complete_execution(agent.agent_id, record.generation_id, success=True)

        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            record.completed_at = datetime.now(timezone.utc)
            record.add_event({"type": "error", "error": str(e)})
            logger.error(f"Generation {record.generation_id} failed: {e}", exc_info=True)

            # Mark state manager failed (Error)
            if self._state_manager:
                self._state_manager.complete_execution(agent.agent_id, record.generation_id, success=False)
            if self._obs_service:
                try:
                    dur_ms = int((record.completed_at - record.started_at).total_seconds() * 1000) if record.started_at else None
                    from app.core.observability.schemas import TelemetryEventCreate, EVENT_AGENT_RUN_FAILED
                    asyncio.create_task(self._obs_service.emit_event(TelemetryEventCreate(
                        event_type=EVENT_AGENT_RUN_FAILED,
                        component="agent",
                        agent_id=agent.agent_id,
                        user_id=record.user_id,
                        session_id=record.conversation_id,
                        correlation_id=record.generation_id,
                        status="failure",
                        duration_ms=dur_ms,
                        error_type=type(e).__name__,
                        metadata={"agent_id": agent.agent_id, "error": str(e)}
                    )))
                except Exception:
                    pass

    async def get_active_generation(
        self,
        user_id: str,
        conversation_id: Optional[str] = None
    ) -> Optional[GenerationRecord]:
        async with self._lock:
            for record in reversed(self._generations.values()):
                if record.user_id == user_id:
                    if conversation_id and record.conversation_id != conversation_id:
                        continue
                    if record.status == "running":
                        return record
            return None

    async def get_generation(self, generation_id: str, user_id: str) -> Optional[GenerationRecord]:
        async with self._lock:
            record = self._generations.get(generation_id)
            if record and record.user_id == user_id:
                return record
            return None

    async def cancel_generation(self, generation_id: str, user_id: str) -> bool:
        async with self._lock:
            record = self._generations.get(generation_id)
            if not record or record.user_id != user_id:
                return False
            if record.status != "running":
                return False
            
            record._is_cancelled = True
            if record._task and not record._task.done():
                record._task.cancel()
            record.status = "cancelled"
            record.completed_at = datetime.now(timezone.utc)
            return True

    async def subscribe_stream(self, record: GenerationRecord) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribes an SSE connection to a GenerationRecord.
        Yields all historical events first, then streams live events until completion.
        If client disconnects, generation continues in the background.
        """
        queue = record.add_subscriber()
        try:
            # Replay historical events
            seen_count = 0
            for ev in list(record.events_history):
                yield ev
                seen_count += 1

            # Stream remaining live events
            while True:
                if record.status in ("completed", "failed", "cancelled") and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield event
                    if event.get("type") in ("completed", "error"):
                        break
                except asyncio.TimeoutError:
                    if record.status in ("completed", "failed", "cancelled") and queue.empty():
                        break
                    continue
        finally:
            record.remove_subscriber(queue)
