import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_generation_endpoint(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/generate",
        json={"message": "Hello MRPL", "model": "fake-model", "stream": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "fake-model"
    assert "Fake response for: Hello MRPL" in data["text"]

@pytest.mark.asyncio
async def test_streaming_endpoint(async_client: AsyncClient):
    async with async_client.stream("POST", "/api/v1/generate", json={"message": "Stream this", "model": "fake-model", "stream": True}) as response:
        assert response.status_code == 200
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                import json
                events.append(json.loads(line[6:]))
                
        assert len(events) == 4
        assert events[0]["type"] == "text_delta"
        assert events[-1]["type"] == "completed"
