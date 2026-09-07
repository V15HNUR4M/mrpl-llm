import uuid
from typing import Dict, Any, List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.uow import UnitOfWork, get_uow
from app.services.conversation import ConversationService
from app.services.summary import ConversationSummaryService
from app.services.semantic_memory import MemoryService
from app.services.memory_extraction import MemoryExtractionService
from app.core.context_engine.schemas import ContextCandidate

from app.api.v1.endpoints.auth import get_current_user
from app.schemas.user import UserResponse
from app.core.agent.registry import AgentNotFoundError, AgentDisabledError
from app.core.runtime.schemas import RuntimeSession
from app.core.runtime.errors import AgentExecutionError

router = APIRouter()

class AgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    version: str
    status: str

@router.get("", response_model=List[AgentResponse])
async def list_agents(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    registry = request.app.state.agent_registry
    agents = registry.list_all()
    return [
        AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            status=agent.status
        )
        for agent in agents
    ]

class AgentRunRequest(BaseModel):
    message: str
    conversation_id: str

class AgentRunResponse(BaseModel):
    session_id: str
    final_answer: str
    events: list

@router.post("/{agent_id}/run", response_model=AgentRunResponse)
async def run_agent(
    request: Request,
    agent_id: str, 
    run_req: AgentRunRequest,
    current_user: UserResponse = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    registry = request.app.state.agent_registry
    harness = request.app.state.agent_harness
    
    try:
        agent = registry.get(agent_id)
        if agent.status != "enabled":
            raise AgentDisabledError()
            
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
        
        decision = await harness.execute(session, run_req.message, recent_candidates)
        
        async with uow:
            conv_service = ConversationService(uow)
            await conv_service.add_message(run_req.conversation_id, current_user.id, {
                "role": "assistant",
                "content": decision.final_answer or "",
                "agent_id": agent.agent_id
            })
            await uow.commit()
            
            # Track 6E: Extract durable memories from the user message.
            # Failure must not affect the response.
            try:
                from app.core.model_gateway.schemas import Message as GenMessage
                user_msgs = [GenMessage(role="user", content=run_req.message)]
                extraction_service = MemoryExtractionService(uow, request.app.state.model_gateway)
                await extraction_service.extract_from_messages(current_user.id, user_msgs)
            except Exception:
                pass
        
        return AgentRunResponse(
            session_id=session_id,
            final_answer=decision.final_answer or "",
            events=[e.model_dump() for e in session.events]
        )
        
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except AgentDisabledError:
        raise HTTPException(status_code=400, detail="Agent is disabled")
    except AgentExecutionError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{agent_id}/stream")
async def stream_agent(
    request: Request,
    agent_id: str,
    run_req: AgentRunRequest,
    current_user: UserResponse = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow, use_cache=False)
):
    registry = request.app.state.agent_registry
    harness = request.app.state.agent_harness
    generation_manager = getattr(request.app.state, "generation_manager", None)
    
    try:
        agent = registry.get(agent_id)
        if agent.status != "enabled":
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
                recent_candidates=recent_candidates
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
                
                final_answer = ""
                async for event in harness.stream_execute(session, run_req.message, recent_candidates):
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "completed":
                        final_answer = event.get("final_answer", "")
                        
                if final_answer:
                    from app.db.database import AsyncSessionLocal
                    new_uow = UnitOfWork(session_factory=AsyncSessionLocal)
                    async with new_uow:
                        new_conv_service = ConversationService(new_uow)
                        await new_conv_service.add_message(run_req.conversation_id, current_user.id, {
                            "role": "assistant",
                            "content": final_answer,
                            "agent_id": agent.agent_id
                        })
                        
            except Exception as e:
                error_event = {"type": "error", "error": str(e)}
                yield f"data: {json.dumps(error_event)}\n\n"
                
        return StreamingResponse(direct_event_generator(), media_type="text/event-stream")
        
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")

@router.get("/generations/active")
async def get_active_generation(
    request: Request,
    conversation_id: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    generation_manager = getattr(request.app.state, "generation_manager", None)
    if not generation_manager:
        return {"active": False, "generation": None}
        
    record = await generation_manager.get_active_generation(current_user.id, conversation_id)
    if not record:
        return {"active": False, "generation": None}
        
@router.get("/generations/{generation_id}/stream")
async def subscribe_generation_stream(
    request: Request,
    generation_id: str,
    current_user: UserResponse = Depends(get_current_user)
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
    current_user: UserResponse = Depends(get_current_user)
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
