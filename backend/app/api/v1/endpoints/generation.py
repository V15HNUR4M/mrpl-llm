from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

from app.core.config import settings
from app.core.model_gateway.schemas import GenerationRequest
from app.core.model_gateway.errors import ModelGatewayError
from app.core.context_engine.engine import ContextEngine
from app.core.context_engine.schemas import ContextCandidate

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    stream: bool = False

@router.post("")
async def generate(request: Request, chat_req: ChatRequest):
    """
    Development/Verification endpoint for testing Model Gateway and Context Engine.
    """
    gateway = request.app.state.model_gateway
    engine = ContextEngine()

    # 1. Prepare candidates (Simulate some context)
    candidates = [
        ContextCandidate(id="sys1", type="system", content="You are a helpful AI assistant.", priority=1),
        ContextCandidate(id="req1", type="request", content=chat_req.message, priority=1)
    ]

    # 2. Assemble context
    package = engine.assemble_context(candidates)

    # 3. Create Generation Request
    model_id = chat_req.model or settings.DEFAULT_CHAT_MODEL
    gen_req = engine.convert_to_generation_request(package, model_id, stream=chat_req.stream)

    # 4. Route to Gateway
    if chat_req.stream:
        async def event_generator():
            try:
                async for event in gateway.stream(gen_req):
                    # Server-Sent Events (SSE) format
                    yield f"data: {event.model_dump_json()}\n\n"
            except ModelGatewayError as e:
                error_event = {"type": "error", "error": str(e)}
                yield f"data: {json.dumps(error_event)}\n\n"
                
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    else:
        response = await gateway.generate(gen_req)
        return response
