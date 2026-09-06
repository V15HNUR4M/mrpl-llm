from typing import AsyncGenerator, List
import asyncio
from app.core.model_gateway.schemas import (
    GenerationRequest, GenerationResponse, StreamingEvent, ModelInfo, ModelCapabilities, Usage
)
from app.core.model_gateway.provider import ModelProvider

class FakeProvider(ModelProvider):
    """
    Fake Provider used exclusively for testing purposes.
    """
    def __init__(self):
        self._delay = 0.1 # Simulate network delay

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        await asyncio.sleep(self._delay)
        return GenerationResponse(
            text=f"Fake response for: {request.messages[-1].content if request.messages else ''}",
            model=request.model,
            finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=20, total_tokens=30)
        )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]:
        await asyncio.sleep(self._delay)
        yield StreamingEvent(type="text_delta", text="Fake ")
        await asyncio.sleep(self._delay)
        yield StreamingEvent(type="text_delta", text="streaming ")
        await asyncio.sleep(self._delay)
        yield StreamingEvent(type="text_delta", text="response.")
        yield StreamingEvent(type="completed", usage=Usage(input_tokens=10, output_tokens=3, total_tokens=13))

    async def health(self) -> bool:
        return True
    
    async def get_model_info(self, model_id: str) -> ModelInfo:
        return ModelInfo(
            model_id=model_id,
            provider="fake",
            capabilities=ModelCapabilities(text_generation=True, streaming=True),
            context_window=8192
        )
    
    async def list_models(self) -> List[ModelInfo]:
        return [await self.get_model_info("fake-model")]
