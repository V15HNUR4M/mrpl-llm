from abc import ABC, abstractmethod
from typing import List
import httpx
import random

from app.core.config import settings
from app.core.rag.errors import EmbeddingError

class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass

class FakeEmbeddingProvider(EmbeddingProvider):
    """Used for testing without a real LLM"""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        
    async def embed_text(self, text: str) -> List[float]:
        return [random.uniform(-1.0, 1.0) for _ in range(self.dimension)]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed_text(t) for t in texts]

class OllamaEmbeddingProvider(EmbeddingProvider):
    """Uses Ollama's /api/embeddings endpoint for local embeddings"""
    def __init__(self, model: str = settings.DEFAULT_EMBEDDING_MODEL, base_url: str = settings.OLLAMA_BASE_URL, timeout: float = 60.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed_text(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("embedding", [])
        except Exception as e:
            raise EmbeddingError(f"Ollama embedding failed: {str(e)}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Ollama /api/embeddings does not natively support batching in all versions
        # A true batch endpoint might be /api/embed in newer versions, but we'll run them concurrently for reliability
        import asyncio
        tasks = [self.embed_text(text) for text in texts]
        return await asyncio.gather(*tasks)
