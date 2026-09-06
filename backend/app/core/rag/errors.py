class RAGError(Exception):
    """Base class for RAG errors."""
    pass

class UnsupportedFormatError(RAGError):
    pass

class FileValidationError(RAGError):
    pass

class ParsingError(RAGError):
    pass

class ChunkingError(RAGError):
    pass

class EmbeddingError(RAGError):
    pass

class VectorStoreError(RAGError):
    pass

class DocumentNotFoundError(RAGError):
    pass
