import pytest
import pytest_asyncio
import httpx
from app.core.model_gateway.schemas import GenerationRequest, Message
from app.core.model_gateway.errors import ModelNotFoundError, ProviderConnectionError, ProviderTimeoutError
from app.core.model_gateway.gateway import ModelGateway
from app.providers.fake import FakeProvider
from app.providers.ollama import OllamaProvider

@pytest.fixture
def gateway():
    g = ModelGateway()
    g.register_provider("fake", FakeProvider())
    g.register_model_route("fake-model", "fake")
    return g

@pytest.mark.asyncio
async def test_gateway_routing(gateway):
    req = GenerationRequest(model="fake-model", messages=[Message(role="user", content="Hello")])
    resp = await gateway.generate(req)
    assert resp.text == "Fake response for: Hello"
    assert resp.model == "fake-model"

@pytest.mark.asyncio
async def test_gateway_model_not_found(gateway):
    req = GenerationRequest(model="unknown-model", messages=[Message(role="user", content="Hello")])
    with pytest.raises(ModelNotFoundError):
        await gateway.generate(req)

@pytest.mark.asyncio
async def test_gateway_streaming(gateway):
    req = GenerationRequest(model="fake-model", messages=[Message(role="user", content="Hello")], stream=True)
    events = []
    async for event in gateway.stream(req):
        events.append(event)
    
    assert len(events) == 4
    assert events[0].type == "text_delta"
    assert events[0].text == "Fake "
    assert events[-1].type == "completed"
    assert events[-1].usage.input_tokens == 10

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code
        self.text = "Mock Error"

    def json(self):
        return self._json_data
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Error", request=None, response=self)

class MockAsyncClient:
    async def request(self, method, url, **kwargs):
        if url == "http://localhost:11434/api/chat":
            return MockResponse({"message": {"content": "Ollama response"}, "model": "test", "done_reason": "stop"})
        if url == "http://localhost:11434/api/tags":
            return MockResponse({"models": [{"name": "qwen2.5:latest"}]})
        return MockResponse({})

    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.mark.asyncio
async def test_ollama_provider_generate(monkeypatch):
    provider = OllamaProvider(base_url="http://localhost:11434")
    
    # Mock httpx.AsyncClient to return our MockAsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockAsyncClient())
    
    req = GenerationRequest(model="test", messages=[Message(role="user", content="Hello")])
    resp = await provider.generate(req)
    
    assert resp.text == "Ollama response"
    assert resp.model == "test"

@pytest.mark.asyncio
async def test_ollama_provider_timeout(monkeypatch):
    provider = OllamaProvider(base_url="http://localhost:11434")
    
    class TimeoutClient:
        async def request(self, method, url, **kwargs):
            raise httpx.TimeoutException("Timeout")
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
            
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: TimeoutClient())
    
    req = GenerationRequest(model="test", messages=[Message(role="user", content="Hello")])
    with pytest.raises(ProviderTimeoutError):
        await provider.generate(req)
