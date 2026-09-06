import json
import httpx
from typing import AsyncGenerator, List, Any
import asyncio

from app.core.model_gateway.schemas import (
    GenerationRequest, GenerationResponse, StreamingEvent, ModelInfo, ModelCapabilities, Usage
)
from app.core.model_gateway.provider import ModelProvider
from app.core.model_gateway.errors import ProviderConnectionError, ProviderTimeoutError
from app.core.config import settings

class OllamaProvider(ModelProvider):
    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, timeout: float = 60.0, multimodal_service=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.multimodal_service = multimodal_service

    async def _request(self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException:
            raise ProviderTimeoutError("ollama")
        except httpx.RequestError as e:
            raise ProviderConnectionError("ollama", str(e))
        except httpx.HTTPStatusError as e:
            raise ProviderConnectionError("ollama", f"HTTP Error {e.response.status_code}: {e.response.text}")

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload = await self._build_payload(request)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request(client, "POST", "/api/chat", json=payload)
            data = response.json()
            
            return GenerationResponse(
                text=data.get("message", {}).get("content", ""),
                model=data.get("model", request.model),
                finish_reason=data.get("done_reason", "stop"),
                usage=Usage(
                    input_tokens=data.get("prompt_eval_count", 0),
                    output_tokens=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                )
            )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]:
        payload = await self._build_payload(request)
        payload["stream"] = True

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("done"):
                                yield StreamingEvent(
                                    type="completed",
                                    usage=Usage(
                                        input_tokens=data.get("prompt_eval_count", 0),
                                        output_tokens=data.get("eval_count", 0),
                                        total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                                    )
                                )
                            else:
                                chunk = data.get("message", {}).get("content", "")
                                if chunk:
                                    yield StreamingEvent(type="text_delta", text=chunk)
                        except json.JSONDecodeError:
                            continue
            except asyncio.CancelledError:
                # Handle client disconnect cancellation gracefully
                yield StreamingEvent(type="error", error="Stream cancelled by client")
                raise
            except httpx.TimeoutException:
                yield StreamingEvent(type="error", error="Provider timeout")
                raise ProviderTimeoutError("ollama")
            except Exception as e:
                yield StreamingEvent(type="error", error=str(e))
                raise ProviderConnectionError("ollama", str(e))

    async def _build_payload(self, request: GenerationRequest) -> dict:
        import base64
        messages = []
        for msg in request.messages:
            m = {"role": msg.role, "content": msg.content}
            if getattr(msg, "images", None) and self.multimodal_service:
                m["images"] = []
                for img in msg.images:
                    # Retrieve bytes, encode to base64 string
                    bytes_data = await self.multimodal_service.get_attachment_content_system(img.attachment_id)
                    if bytes_data:
                        b64 = base64.b64encode(bytes_data).decode("utf-8")
                        m["images"].append(b64)
            messages.append(m)

        options = {"temperature": request.temperature}
        if request.max_tokens:
            options["num_predict"] = request.max_tokens

        return {
            "model": request.model,
            "messages": messages,
            "options": options,
            "stream": request.stream
        }

    async def health(self) -> bool:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                await self._request(client, "GET", "/")
                return True
            except (ProviderConnectionError, ProviderTimeoutError):
                return False

    async def get_model_info(self, model_id: str) -> ModelInfo:
        # Optimistic assumption for local models unless we query /api/tags
        # We can dynamically assume models like 'llava' or 'llama3.2-vision' have vision
        vision_capable = "vision" in model_id.lower() or "llava" in model_id.lower() or "minig" in model_id.lower()
        return ModelInfo(
            model_id=model_id,
            provider="ollama",
            capabilities=ModelCapabilities(text_generation=True, streaming=True, vision=vision_capable),
            context_window=8192
        )

    async def list_models(self) -> List[ModelInfo]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await self._request(client, "GET", "/api/tags")
                data = response.json()
                models = []
                for m in data.get("models", []):
                    name = m["name"]
                    vision_capable = "vision" in name.lower() or "llava" in name.lower() or "minig" in name.lower()
                    models.append(ModelInfo(
                        model_id=name,
                        provider="ollama",
                        capabilities=ModelCapabilities(text_generation=True, streaming=True, vision=vision_capable)
                    ))
                return models
            except Exception:
                return []
