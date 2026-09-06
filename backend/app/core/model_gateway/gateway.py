from typing import Dict, AsyncGenerator
from app.core.model_gateway.schemas import GenerationRequest, GenerationResponse, StreamingEvent, ModelInfo
from app.core.model_gateway.provider import ModelProvider
from app.core.model_gateway.errors import ModelNotFoundError

class ModelGateway:
    """
    The main entry point for model inference. 
    Routes requests to the appropriate provider adapter.
    """
    def __init__(self, multimodal_service=None, observability_service=None):
        self._providers: Dict[str, ModelProvider] = {}
        # Mapping of model_id to provider_id (simplistic routing for now)
        self._model_routes: Dict[str, str] = {}
        self._multimodal_service = multimodal_service
        self._observability_service = observability_service

    def register_provider(self, provider_id: str, provider: ModelProvider):
        self._providers[provider_id] = provider
        
    def register_model_route(self, model_id: str, provider_id: str):
        if provider_id not in self._providers:
            raise ValueError(f"Provider '{provider_id}' is not registered.")
        self._model_routes[model_id] = provider_id

    def _get_provider_for_model(self, model_id: str) -> ModelProvider:
        # Default to ollama if not explicitly routed (for Track 2 simplicity)
        provider_id = self._model_routes.get(model_id, "ollama")
        provider = self._providers.get(provider_id)
        if not provider:
            raise ModelNotFoundError(model_id)
        return provider

    async def _prepare_multimodal_request(self, request: GenerationRequest, provider: ModelProvider) -> GenerationRequest:
        info = await provider.get_model_info(request.model)
        has_images = any(msg.images for msg in request.messages)
        
        if has_images and not info.capabilities.vision:
            if not self._multimodal_service:
                from app.core.multimodal.schemas import ProcessingError
                raise ProcessingError("Model does not support vision and OCR fallback is unavailable")
            
            for msg in request.messages:
                if msg.images:
                    extracted_texts = []
                    for img in msg.images:
                        text = await self._multimodal_service.extract_text_system(img.attachment_id)
                        if text:
                            extracted_texts.append(f"[OCR Extracted Text]:\n{text}")
                    if extracted_texts:
                        msg.content = msg.content + "\n\n" + "\n\n".join(extracted_texts)
                    msg.images = None # Remove images so provider doesn't fail
        
        return request

    async def _emit_telemetry(self, event_type: str, request: GenerationRequest, status: str = "success", duration_ms: int = None, error_type: str = None, metadata: dict = None, severity: str = "INFO"):
        if not self._observability_service:
            return
        try:
            from app.core.observability.schemas import TelemetryEventCreate
            meta = metadata or {}
            meta["model"] = request.model
            meta["has_images"] = any(bool(msg.images) for msg in request.messages)
            
            # Extract request / correlation / user context if present in request.metadata
            req_meta = getattr(request, "metadata", {}) or {}
            user_id = req_meta.get("user_id")
            request_id = req_meta.get("request_id")
            correlation_id = req_meta.get("correlation_id")
            session_id = req_meta.get("session_id")
            
            event = TelemetryEventCreate(
                event_type=event_type,
                component="model_gateway",
                severity=severity,
                user_id=user_id,
                request_id=request_id,
                correlation_id=correlation_id,
                session_id=session_id,
                duration_ms=duration_ms,
                status=status,
                error_type=error_type,
                metadata=meta
            )
            await self._observability_service.emit_event(event)
        except Exception:
            # Observability failure MUST NOT break the caller
            pass

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        import time
        t0 = time.time()
        await self._emit_telemetry("model.generation.started", request, status="started")
        
        try:
            provider = self._get_provider_for_model(request.model)
            request = await self._prepare_multimodal_request(request, provider)
            response = await provider.generate(request)
            
            duration_ms = int((time.time() - t0) * 1000)
            token_meta = {}
            if hasattr(response, "usage") and response.usage:
                token_meta["input_tokens"] = getattr(response.usage, "input_tokens", 0)
                token_meta["output_tokens"] = getattr(response.usage, "output_tokens", 0)
                token_meta["total_tokens"] = getattr(response.usage, "total_tokens", 0)

            await self._emit_telemetry(
                "model.generation.completed", 
                request, 
                status="success", 
                duration_ms=duration_ms,
                metadata=token_meta
            )
            return response
            
        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            await self._emit_telemetry(
                "model.generation.failed", 
                request, 
                status="failed", 
                duration_ms=duration_ms,
                error_type=type(e).__name__,
                severity="ERROR"
            )
            raise e

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]:
        import time
        t0 = time.time()
        await self._emit_telemetry("model.stream.started", request, status="started")
        
        try:
            provider = self._get_provider_for_model(request.model)
            request = await self._prepare_multimodal_request(request, provider)
            async for event in provider.stream(request):
                yield event
                
            duration_ms = int((time.time() - t0) * 1000)
            await self._emit_telemetry("model.stream.completed", request, status="success", duration_ms=duration_ms)
            
        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            await self._emit_telemetry(
                "model.stream.failed", 
                request, 
                status="failed", 
                duration_ms=duration_ms,
                error_type=type(e).__name__,
                severity="ERROR"
            )
            raise e

    async def get_model_info(self, model_id: str) -> ModelInfo:
        provider = self._get_provider_for_model(model_id)
        return await provider.get_model_info(model_id)
