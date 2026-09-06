from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class DocumentMetadata(BaseModel):
    document_id: str
    owner_id: Optional[str] = None
    filename: str
    file_type: str
    mime_type: Optional[str] = None
    file_size: int
    checksum: str
    access_scope: str = "PRIVATE"
    status: str
    created_at: datetime
    updated_at: datetime

class ParsedDocument(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_version_id: str
    content: str
    chunk_index: int
    page_number: Optional[int] = None
    section: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
class IngestionResult(BaseModel):
    document_id: str
    document_version_id: str
    status: str
    chunks_processed: int
    message: str

class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    document_version_id: str
    content: str
    score: float
    page_number: Optional[int] = None
    section: Optional[str] = None
    filename: str
    
class RetrievalQuery(BaseModel):
    query: str
    top_k: int = 10
    owner_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    min_score: float = 0.0
