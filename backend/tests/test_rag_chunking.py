import pytest
from app.core.rag.chunking import TextChunker
from app.core.rag.schemas import ParsedDocument

def test_chunking():
    chunker = TextChunker(chunk_size=10, chunk_overlap=2)
    
    # 25 characters
    doc = ParsedDocument(content="This is a test document. ")
    
    chunks = chunker.chunk(doc, "doc_1", "ver_1")
    
    assert len(chunks) > 0
    assert chunks[0].document_id == "doc_1"
    assert chunks[0].document_version_id == "ver_1"
    
    # Test deterministic ID
    assert chunks[0].chunk_id == "ver_1-chunk-0"
    assert chunks[1].chunk_id == "ver_1-chunk-1"

def test_chunk_no_empty_chunks():
    chunker = TextChunker(chunk_size=10, chunk_overlap=0)
    doc = ParsedDocument(content="   \n  \n")
    chunks = chunker.chunk(doc, "doc_1", "ver_1")
    assert len(chunks) == 0
