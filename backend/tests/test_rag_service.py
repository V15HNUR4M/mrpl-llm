import pytest
from app.core.rag.service import RAGService
from app.core.rag.parser import ParserRegistry
from app.core.rag.chunking import TextChunker
from app.core.rag.embeddings import FakeEmbeddingProvider
from app.core.rag.vector_store import ChromaVectorStore
from app.core.rag.schemas import RetrievalQuery
from app.db.database import AsyncSessionLocal, Base, engine
from app.db.models import User
import uuid

@pytest.fixture
def rag_service():
    # Note: testing Chroma locally requires no interference, but for simple unit test it's fine
    # For full isolation, test in an integration setting or with mocked vector store
    return RAGService(
        parser_registry=ParserRegistry(),
        chunker=TextChunker(chunk_size=100, chunk_overlap=10),
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=ChromaVectorStore(collection_name="test_collection")
    )

@pytest.mark.asyncio
async def test_rag_ingestion_and_retrieval(rag_service):
    # Setup db for test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    owner_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        user = User(id=owner_id, username="test_user_rag", email="test@rag.com", password_hash="hash")
        session.add(user)
        await session.commit()

    # and a persistent Chroma DB.
    
    # Ingest
    content = b"The quick brown fox jumps over the lazy dog. The dog is lazy."
    filename = "test_doc.txt"
    
    result = await rag_service.ingest_document(
        file_bytes=content,
        filename=filename,
        mime_type="text/plain",
        owner_id=owner_id
    )
    
    assert result.status == "SUCCESS"
    assert result.chunks_processed > 0
    doc_id = result.document_id
    
    # Search
    query = RetrievalQuery(
        query="brown fox",
        top_k=2,
        owner_id=owner_id
    )
    
    results = await rag_service.search_documents(query)
    assert len(results) > 0
    assert results[0].document_id == doc_id
    
    # Search with wrong owner (Document Isolation)
    query_isolated = RetrievalQuery(
        query="brown fox",
        top_k=2,
        owner_id="wrong_user"
    )
    
    isolated_results = await rag_service.search_documents(query_isolated)
    assert len(isolated_results) == 0
    
    # Cleanup
    await rag_service.delete_document(doc_id, owner_id)
