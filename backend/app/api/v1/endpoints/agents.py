import uuid
from typing import Dict, Any, List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.core.config import settings
from app.dependencies import get_current_user
from app.db.models import User
from app.db.uow import UnitOfWork, get_uow
from app.core.errors import MRPLAPIException
from app.services.conversation import ConversationService
from app.services.summary import ConversationSummaryService
from app.services.semantic_memory import MemoryService
from app.services.memory_extraction import MemoryExtractionService
from app.core.context_engine.schemas import ContextCandidate
from app.core.agent.registry import AgentNotFoundError, AgentDisabledError
from app.core.runtime.schemas import RuntimeSession
from app.core.runtime.errors import AgentExecutionError

router = APIRouter()

class AgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    version: str
    status: str # "ready", "running", "disabled", "error", "unavailable"
    is_enabled: bool = True
    type: str = "specialist"
    capabilities: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    model: str = ""
    provider: str = ""
    context_policy: Dict[str, Any] = Field(default_factory=dict)

class AgentActivityItem(BaseModel):
    id: str
    timestamp: str
    agent: str
    agent_id: str
    task: str
    status: str
    duration_ms: Optional[int] = None
    correlation_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

@router.get("", response_model=List[AgentResponse])
async def list_agents(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    registry = request.app.state.agent_registry
    state_mgr = getattr(request.app.state, "agent_state_manager", None)
    if not state_mgr:
        from app.core.runtime.state_manager import get_agent_state_manager
        state_mgr = get_agent_state_manager()

    agents = registry.list_all()
    response_items = []
    for agent in agents:
        is_enabled = bool(agent.status == "enabled")
        live_status = state_mgr.get_status(agent.agent_id, is_enabled=is_enabled)

        agent_type = "general" if agent.agent_id == "general_agent" else (
            "specialist" if agent.agent_id in ("document_agent", "excel_agent") else "analysis"
        )

        caps = ["text_generation"]
        if getattr(agent.context_policy, "rag", False):
            caps.append("rag_retrieval")
        if "create_workbook" in (agent.tool_permissions.allowed or []):
            caps.append("excel_operations")

        response_items.append(AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            status=live_status,
            is_enabled=is_enabled,
            type=agent_type,
            capabilities=caps,
            tools=list(agent.tool_permissions.allowed or []),
            model=settings.DEFAULT_CHAT_MODEL,
            provider=settings.EMBEDDING_PROVIDER,
            context_policy={
                "rag": getattr(agent.context_policy, "rag", False),
                "recent_messages_count": getattr(agent.context_policy, "recent_messages_count", 10)
            }
        ))

    # Add active Task Router orchestrator component
    response_items.append(AgentResponse(
        agent_id="task_router",
        name="Task Router",
        description="Deterministic query classifier and task orchestrator that routes requests to specialist agents.",
        version="1.0",
        status="ready",
        is_enabled=True,
        type="orchestrator",
        capabilities=["intent_classification", "excel_detection", "query_routing"],
        tools=["route_agent", "should_route_to_excel_agent"],
        model="Deterministic Rule Engine",
        provider="system",
        context_policy={"rag": False}
    ))

    return response_items

@router.get("/activity", response_model=List[AgentActivityItem])
async def list_agent_activity(
    request: Request,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    obs_service = getattr(request.app.state, "observability_service", None)
    if not obs_service:
        from app.core.observability.service import get_observability_service
        obs_service = get_observability_service()

    is_admin = bool(str(current_user.role) == "ADMIN")
    target_user_id = None if is_admin else str(current_user.id)

    events = await obs_service.get_events(
        user_id=target_user_id,
        is_admin=is_admin,
        limit=max(limit * 3, 40)
    )

    activity_items = []
    agent_display_names = {
        "excel_agent": "Excel Agent",
        "document_agent": "Document Agent",
        "general_agent": "General Agent",
        "task_router": "Task Router",
        "analysis_agent": "Analysis Agent",
    }

    for evt in events:
        c = (evt.component or "").lower()
        et = (evt.event_type or "").lower()
        if c in ("agent", "tools", "router", "file_export") or et.startswith(("agent.", "tool.", "router.", "file.")):
            meta = evt.metadata_ or {}
            agent_id = meta.get("agent_id") or meta.get("target_agent") or meta.get("selected_agent") or ""
            if not agent_id:
                tool_name = meta.get("tool", "")
                if "workbook" in tool_name or tool_name in ("aggregate_data", "filter_rows", "detect_duplicates", "detect_missing_values"):
                    agent_id = "excel_agent"
                elif tool_name in ("search_documents", "get_document"):
                    agent_id = "document_agent"
                elif c == "router" or et.startswith("router."):
                    agent_id = "task_router"
                elif c == "agent":
                    agent_id = "general_agent"
                else:
                    agent_id = "general_agent"

            agent_name = agent_display_names.get(agent_id, agent_id.replace("_", " ").title())

            tool_name = meta.get("tool", "")
            if et == "router.task_routed":
                target = meta.get("target_agent", "specialist")
                task = f"Task routing -> {agent_display_names.get(target, target)}"
            elif tool_name in ("create_workbook", "save_workbook", "write_cells"):
                task = "Spreadsheet generation"
            elif tool_name in ("read_workbook", "inspect_sheet", "read_range"):
                task = "Spreadsheet data inspection"
            elif tool_name in ("aggregate_data", "filter_rows", "detect_duplicates", "detect_missing_values"):
                task = "Excel data calculation & analysis"
            elif tool_name in ("search_documents", "get_document"):
                task = "RAG document retrieval"
            elif et == "file.generated":
                task = f"Exported file ({meta.get('filename', 'document')})"
            elif et.startswith("agent.run"):
                task = "Model response generation"
            elif et.startswith("chat."):
                task = "User chat interaction"
            else:
                task = tool_name or et

            st = (evt.status or "completed").lower()
            if st in ("success", "completed"):
                clean_status = "completed"
            elif st in ("started", "running"):
                clean_status = "running"
            elif st in ("failed", "error"):
                clean_status = "error"
            elif st in ("denied", "warn"):
                clean_status = "denied"
            else:
                clean_status = st

            ts_str = evt.timestamp.isoformat() if hasattr(evt.timestamp, "isoformat") else str(evt.timestamp)
            activity_items.append(AgentActivityItem(
                id=evt.id,
                timestamp=ts_str,
                agent=agent_name,
                agent_id=agent_id,
                task=task,
                status=clean_status,
                duration_ms=evt.duration_ms,
                correlation_id=evt.correlation_id or evt.request_id,
                details=meta
            ))
            if len(activity_items) >= limit:
                break

    return activity_items

class AgentRunRequest(BaseModel):
    message: str
    conversation_id: str
    file_id: Optional[str] = None
    file_type: Optional[str] = None
    filename: Optional[str] = None

class AgentRunResponse(BaseModel):
    session_id: str
    final_answer: str
    events: list
    generated_file: Optional[Dict[str, Any]] = None

async def _export_generated_file_if_requested(
    message: str,
    final_text: str,
    user_id: str,
    conversation_id: str,
    session_events: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
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
        if not req["requested"] or not final_text:
            return None

        file_mgr = GeneratedFileManager()
        fmt = req["format"]
        if fmt == "docx":
            filename = derive_filename(message, ext=".docx")
            docx_bytes = export_to_docx(final_text)
            return await file_mgr.save_file(user_id, conversation_id, filename, docx_bytes, file_type="docx")
        elif fmt == "pdf":
            filename = derive_filename(message, ext=".pdf")
            pdf_bytes = export_to_pdf(final_text)
            return await file_mgr.save_file(user_id, conversation_id, filename, pdf_bytes, file_type="pdf")
        elif fmt == "markdown":
            filename = derive_filename(message, ext=".md")
            return await file_mgr.save_markdown_file(user_id, conversation_id, filename, final_text)
        elif fmt == "xlsx":
            from app.core.excel.writers import create_workbook, save_workbook
            from app.core.excel.table_parser import extract_tabular_data
            filename = derive_filename(message, ext=".xlsx")
            headers, rows = extract_tabular_data(final_text, session_events=session_events, user_input=message)
            created = create_workbook(sheet_name="Data", headers=headers, rows=rows)
            return await save_workbook(created["staging_file_id"], filename, user_id, conversation_id)
    except Exception as e:
        logger.error(f"Error in file export: {e}")
    return None

@router.post("/{agent_id}/run", response_model=AgentRunResponse)
async def run_agent(
    request: Request,
    agent_id: str, 
    run_req: AgentRunRequest,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    registry = request.app.state.agent_registry
    harness = request.app.state.agent_harness
    
    obs_service = getattr(request.app.state, "observability_service", None)
    req_id = request.headers.get("X-Request-ID")
    corr_id = request.headers.get("X-Correlation-ID") or req_id

    try:
        from app.core.runtime.task_router import TaskRouter
        target_agent_id = TaskRouter.route_agent(
            selected_agent_id=agent_id,
            message=run_req.message,
            active_file_type=run_req.file_type,
            active_file_name=run_req.filename,
            observability_service=obs_service,
            user_id=current_user.id,
            request_id=req_id,
            correlation_id=corr_id
        )
        agent = registry.get(target_agent_id)
        if agent.status != "enabled":
            raise AgentDisabledError()

        if obs_service:
            from app.core.observability.schemas import TelemetryEventCreate
            await obs_service.emit_event(TelemetryEventCreate(
                event_type="chat.request",
                component="agent",
                severity="INFO",
                user_id=current_user.id,
                request_id=req_id,
                correlation_id=corr_id,
                session_id=run_req.conversation_id,
                status="success",
                metadata={
                    "agent_id": agent.agent_id,
                    "target_agent": target_agent_id,
                    "conversation_id": run_req.conversation_id,
                    "has_file": bool(run_req.file_id)
                }
            ))
            
        async with uow:
            conv_service = ConversationService(uow)
            
            recent_db_messages = await conv_service.get_recent_messages(run_req.conversation_id, current_user.id, limit=10)
            
            recent_candidates = []
            for msg in recent_db_messages:
                recent_candidates.append(ContextCandidate(
                    id=msg.id,
                    type="message",
                    content=msg.content,
                    metadata={"role": msg.role, "sequence_number": msg.sequence_number},
                    priority=5
                ))
                
            oldest_seq = recent_db_messages[0].sequence_number if recent_db_messages else 0
            if oldest_seq > 1:
                summary_service = ConversationSummaryService(uow, request.app.state.model_gateway)
                summary_candidate = await summary_service.get_summary_candidate(run_req.conversation_id, current_user.id, oldest_seq)
                if summary_candidate:
                    recent_candidates.insert(0, summary_candidate)
            
            memory_service = MemoryService(uow)
            memory_candidates = await memory_service.retrieve_memories(current_user.id, run_req.message, limit=5)
            recent_candidates.extend(memory_candidates)

            # Pass active file context if supplied
            if run_req.file_id:
                recent_candidates.append(ContextCandidate(
                    id=f"file-{run_req.file_id}",
                    type="document",
                    content=json.dumps({
                        "file_id": run_req.file_id,
                        "filename": run_req.filename or "active_file.xlsx",
                        "instruction": "Active spreadsheet file for deterministic tool execution"
                    }),
                    metadata={"file_id": run_req.file_id, "filename": run_req.filename or "active_file.xlsx"},
                    priority=8
                ))
            
            # Check conversation title - auto-title on first message
            conv = await conv_service.get_conversation(run_req.conversation_id, current_user.id)
            current_title = (conv.title or "").strip()
            if not current_title or current_title.lower() in ("new conversation", "new document", "new chat"):
                from app.services.title_generator import generate_title
                new_title = await generate_title(run_req.message, getattr(request.app.state, "model_gateway", None))
                if new_title:
                    await conv_service.update_conversation_title(conv.id, current_user.id, new_title)

            await conv_service.add_message(run_req.conversation_id, current_user.id, {
                "role": "user",
                "content": run_req.message,
                "agent_id": agent.agent_id
            })
            await uow.commit()
            
        session_id = str(uuid.uuid4())
        session = RuntimeSession(
            session_id=session_id,
            conversation_id=run_req.conversation_id,
            agent_id=agent.agent_id,
            agent_version=agent.version,
            user_id=current_user.id
        )
        
        state_mgr = getattr(request.app.state, "agent_state_manager", None)
        if state_mgr:
            state_mgr.start_execution(agent.agent_id, session_id)
        if obs_service:
            try:
                from app.core.observability.schemas import TelemetryEventCreate, EVENT_AGENT_RUN_STARTED
                await obs_service.emit_event(TelemetryEventCreate(
                    event_type=EVENT_AGENT_RUN_STARTED,
                    component="agent",
                    agent_id=agent.agent_id,
                    user_id=current_user.id,
                    correlation_id=session_id,
                    session_id=run_req.conversation_id,
                    status="running"
                ))
            except Exception:
                pass

        try:
            decision = await harness.execute(session, run_req.message, recent_candidates)
            if state_mgr:
                state_mgr.complete_execution(agent.agent_id, session_id, success=True)
            if obs_service:
                try:
                    from app.core.observability.schemas import TelemetryEventCreate, EVENT_AGENT_RUN_COMPLETED
                    await obs_service.emit_event(TelemetryEventCreate(
                        event_type=EVENT_AGENT_RUN_COMPLETED,
                        component="agent",
                        agent_id=agent.agent_id,
                        user_id=current_user.id,
                        correlation_id=session_id,
                        session_id=run_req.conversation_id,
                        status="success"
                    ))
                except Exception:
                    pass
        except Exception as exec_err:
            if state_mgr:
                state_mgr.complete_execution(agent.agent_id, session_id, success=False)
            if obs_service:
                try:
                    from app.core.observability.schemas import TelemetryEventCreate, EVENT_AGENT_RUN_FAILED
                    await obs_service.emit_event(TelemetryEventCreate(
                        event_type=EVENT_AGENT_RUN_FAILED,
                        component="agent",
                        agent_id=agent.agent_id,
                        user_id=current_user.id,
                        correlation_id=session_id,
                        session_id=run_req.conversation_id,
                        status="failure",
                        error_type=type(exec_err).__name__
                    ))
                except Exception:
                    pass
            raise exec_err
        
        file_metadata = None
        for e in session.events:
            if e.type == "tool_completed" and isinstance(e.data, dict):
                res = e.data.get("result")
                if isinstance(res, dict) and res.get("file_id") and (str(res.get("filename", "")).endswith(".xlsx") or res.get("file_type") == "xlsx"):
                    file_metadata = {
                        "file_id": res["file_id"],
                        "filename": res["filename"],
                        "file_type": "xlsx",
                        "mime_type": res.get("mime_type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                        "size_bytes": res.get("size_bytes", 0),
                        "download_url": res.get("download_url", f"/api/v1/files/download/{res['file_id']}")
                    }
                    break

        if not file_metadata and decision.final_answer:
            file_metadata = await _export_generated_file_if_requested(
                message=run_req.message,
                final_text=decision.final_answer,
                user_id=current_user.id,
                conversation_id=run_req.conversation_id,
                session_events=[e.model_dump() for e in session.events]
            )

        if file_metadata:
            session.add_event("file_generated", {"file": file_metadata})

        async with uow:
            conv_service = ConversationService(uow)
            msg_payload = {
                "role": "assistant",
                "content": decision.final_answer or "",
                "agent_id": agent.agent_id
            }
            if file_metadata:
                msg_payload["metadata_"] = {"generated_file": file_metadata}
            await conv_service.add_message(run_req.conversation_id, current_user.id, msg_payload)
            await uow.commit()
            
            # Track 6E: Extract durable memories from the user message.
            # Failure must not affect the response.
            try:
                from app.core.model_gateway.schemas import Message as GenMessage
                user_msgs = [GenMessage(role="user", content=run_req.message)]
                extraction_service = MemoryExtractionService(uow, request.app.state.model_gateway)
                await extraction_service.extract_from_messages(current_user.id, user_msgs)
            except Exception as e:
                pass
        
        return AgentRunResponse(
            session_id=session_id,
            final_answer=decision.final_answer or "",
            events=[e.model_dump() for e in session.events],
            generated_file=file_metadata
        )
    except (HTTPException, MRPLAPIException):
        raise
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except AgentDisabledError:
        raise HTTPException(status_code=400, detail="Agent is disabled")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{agent_id}/stream")
async def stream_agent(
    request: Request,
    agent_id: str,
    run_req: AgentRunRequest,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow, use_cache=False)
):
    registry = request.app.state.agent_registry
    harness = request.app.state.agent_harness
    generation_manager = getattr(request.app.state, "generation_manager", None)
    obs_service = getattr(request.app.state, "observability_service", None)
    req_id = request.headers.get("X-Request-ID")
    corr_id = request.headers.get("X-Correlation-ID") or req_id

    try:
        from app.core.runtime.task_router import TaskRouter
        target_agent_id = TaskRouter.route_agent(
            selected_agent_id=agent_id,
            message=run_req.message,
            active_file_type=run_req.file_type,
            active_file_name=run_req.filename,
            observability_service=obs_service,
            user_id=current_user.id,
            request_id=req_id,
            correlation_id=corr_id
        )
        agent = registry.get(target_agent_id)
        if agent.status != "enabled":
            raise AgentDisabledError()

        if obs_service:
            from app.core.observability.schemas import TelemetryEventCreate
            await obs_service.emit_event(TelemetryEventCreate(
                event_type="chat.request",
                component="agent",
                severity="INFO",
                user_id=current_user.id,
                request_id=req_id,
                correlation_id=corr_id,
                session_id=run_req.conversation_id,
                status="success",
                metadata={
                    "agent_id": agent.agent_id,
                    "target_agent": target_agent_id,
                    "conversation_id": run_req.conversation_id,
                    "has_file": bool(run_req.file_id)
                }
            ))
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except AgentDisabledError:
        raise HTTPException(status_code=400, detail="Agent is disabled")
            
    async with uow:
        conv_service = ConversationService(uow)
        
        recent_db_messages = await conv_service.get_recent_messages(run_req.conversation_id, current_user.id, limit=10)
        
        recent_candidates = []
        for msg in recent_db_messages:
            recent_candidates.append(ContextCandidate(
                id=msg.id,
                type="message",
                content=msg.content,
                metadata={"role": msg.role, "sequence_number": msg.sequence_number},
                priority=5
            ))
            
        oldest_seq = recent_db_messages[0].sequence_number if recent_db_messages else 0
        if oldest_seq > 1:
            summary_service = ConversationSummaryService(uow, request.app.state.model_gateway)
            summary_candidate = await summary_service.get_summary_candidate(run_req.conversation_id, current_user.id, oldest_seq)
            if summary_candidate:
                recent_candidates.insert(0, summary_candidate)
            
        memory_service = MemoryService(uow)
        memory_candidates = await memory_service.retrieve_memories(current_user.id, run_req.message, limit=5)
        recent_candidates.extend(memory_candidates)

        # Pass active file context if supplied
        if run_req.file_id:
            recent_candidates.append(ContextCandidate(
                id=f"file-{run_req.file_id}",
                type="document",
                content=json.dumps({
                    "file_id": run_req.file_id,
                    "filename": run_req.filename or "active_file.xlsx",
                    "instruction": "Active spreadsheet file for deterministic tool execution"
                }),
                metadata={"file_id": run_req.file_id, "filename": run_req.filename or "active_file.xlsx"},
                priority=8
            ))

        # Check conversation title - auto-title on first message
        conv = await conv_service.get_conversation(run_req.conversation_id, current_user.id)
        current_title = (conv.title or "").strip()
        title_to_emit = None
        if not current_title or current_title.lower() in ("new conversation", "new document", "new chat"):
            from app.services.title_generator import generate_title
            new_title = await generate_title(run_req.message, getattr(request.app.state, "model_gateway", None))
            if new_title:
                await conv_service.update_conversation_title(conv.id, current_user.id, new_title)
                title_to_emit = new_title

        await conv_service.add_message(run_req.conversation_id, current_user.id, {
            "role": "user",
            "content": run_req.message,
            "agent_id": agent.agent_id
        })
        await uow.commit()

    if generation_manager:
        record = await generation_manager.start_generation(
            agent=agent,
            harness=harness,
            conversation_id=run_req.conversation_id,
            user_id=current_user.id,
            message=run_req.message,
            recent_candidates=recent_candidates,
            initial_title=title_to_emit
        )

        async def event_generator():
            try:
                async for event in generation_manager.subscribe_stream(record):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                error_event = {"type": "error", "error": str(e)}
                yield f"data: {json.dumps(error_event)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Fallback if generation_manager is not initialized (e.g. in some isolated test fixtures)
    session_id = str(uuid.uuid4())
    session = RuntimeSession(
        session_id=session_id,
        conversation_id=run_req.conversation_id,
        agent_id=agent.agent_id,
        agent_version=agent.version,
        user_id=current_user.id
    )
    
    async def direct_event_generator():
        try:
            initial_event = {"type": "session_created", "session_id": session_id}
            yield f"data: {json.dumps(initial_event)}\n\n"
            if title_to_emit:
                yield f"data: {json.dumps({'type': 'title_updated', 'title': title_to_emit, 'conversation_id': run_req.conversation_id})}\n\n"
            
            final_answer = ""
            async for event in harness.stream_execute(session, run_req.message, recent_candidates):
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "completed":
                    final_answer = event.get("final_answer", "")
                    
            if final_answer:
                file_metadata = await _export_generated_file_if_requested(
                    message=run_req.message,
                    final_text=final_answer,
                    user_id=current_user.id,
                    conversation_id=run_req.conversation_id,
                    session_events=[e.model_dump() for e in session.events]
                )
                if file_metadata:
                    yield f"data: {json.dumps({'type': 'file_generated', 'file': file_metadata})}\n\n"

                from app.db.database import AsyncSessionLocal
                new_uow = UnitOfWork(session_factory=AsyncSessionLocal)
                async with new_uow:
                    new_conv_service = ConversationService(new_uow)
                    msg_payload = {
                        "role": "assistant",
                        "content": final_answer,
                        "agent_id": agent.agent_id
                    }
                    if file_metadata:
                        msg_payload["metadata_"] = {"generated_file": file_metadata}
                    await new_conv_service.add_message(run_req.conversation_id, current_user.id, msg_payload)
                    
        except Exception as e:
            error_event = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"
            
    return StreamingResponse(direct_event_generator(), media_type="text/event-stream")

@router.get("/generations/active")
async def get_active_generation(
    request: Request,
    conversation_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    generation_manager = getattr(request.app.state, "generation_manager", None)
    if not generation_manager:
        return {"active": False, "generation": None}
        
    record = await generation_manager.get_active_generation(current_user.id, conversation_id)
    if not record:
        return {"active": False, "generation": None}
        
    return {
        "active": True,
        "generation": record.to_dict(),
        "events": record.events_history
    }

@router.get("/generations/{generation_id}/stream")
async def subscribe_generation_stream(
    request: Request,
    generation_id: str,
    current_user: User = Depends(get_current_user)
):
    generation_manager = getattr(request.app.state, "generation_manager", None)
    if not generation_manager:
        raise HTTPException(status_code=404, detail="Generation manager not available")
        
    record = await generation_manager.get_generation(generation_id, current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found or access denied")
        
    async def event_generator():
        try:
            async for event in generation_manager.subscribe_stream(record):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            error_event = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/generations/{generation_id}/stop")
async def stop_generation(
    request: Request,
    generation_id: str,
    current_user: User = Depends(get_current_user)
):
    generation_manager = getattr(request.app.state, "generation_manager", None)
    if not generation_manager:
        raise HTTPException(status_code=404, detail="Generation manager not available")
        
    success = await generation_manager.cancel_generation(generation_id, current_user.id)
    if not success:
        record = await generation_manager.get_generation(generation_id, current_user.id)
        if not record:
            raise HTTPException(status_code=404, detail="Generation not found or access denied")
        return {"status": record.status, "message": f"Generation is already {record.status}"}
        
    return {"status": "cancelled", "message": "Generation successfully stopped"}
