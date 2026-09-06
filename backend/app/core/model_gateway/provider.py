from abc import ABC, abstractmethod
from typing import AsyncGenerator, List
from app.core.model_gateway.schemas import GenerationRequest, GenerationResponse, StreamingEvent, ModelInfo

class ModelProvider(ABC):
    """
    Abstract base class for all AI model providers.
    Providers should implement these methods to interact with their specific APIs.
    """

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Execute a blocking text generation request."""
        pass

    @abstractmethod
    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamingEvent, None]:
        """Execute a streaming text generation request."""
        pass

    @abstractmethod
    async def health(self) -> bool:
        """Check if the provider is available and healthy."""
        pass
    
    @abstractmethod
    async def get_model_info(self, model_id: str) -> ModelInfo:
        """Get metadata and capabilities for a specific model."""
        pass
    
    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """List all models supported and currently available by this provider."""
        pass
