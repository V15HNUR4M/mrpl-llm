"""
Explicit migration script: Re-indexes mrpl_knowledge Chroma collection
from FakeEmbeddingProvider (384 dimensions) to Ollama nomic-embed-text (768 dimensions).
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy.future import select
from sqlalchemy import delete
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Document, DocumentVersion, DocumentChunk
from app.core.rag.embeddings import OllamaEmbeddingProvider
from app.core.rag.chunking import TextChunker
from app.core.rag.parser import ParserRegistry
from app.core.rag.vector_store import ChromaVectorStore
from app.core.rag.service import RAGService

ADMIN_USER_ID = "31373201-e001-4fc1-9e2f-41330ddfabc9"

async def reindex():
    print("=" * 60)
    print("STARTING EXPLICIT RE-INDEX MIGRATION (384 -> 768 dims)")
    print("=" * 60)

    # 1. Verify Ollama & nomic-embed-text
    print(f"Connecting to Ollama at {settings.OLLAMA_BASE_URL} with model {settings.DEFAULT_EMBEDDING_MODEL}...")
    embedder = OllamaEmbeddingProvider(
        model=settings.DEFAULT_EMBEDDING_MODEL,
        base_url=settings.OLLAMA_BASE_URL
    )
    test_vec = await embedder.embed_text("test connection")
    dim = len(test_vec)
    print(f"Verified Ollama embeddings working! Dimension: {dim}")
    if dim != 768:
        raise RuntimeError(f"Expected 768 dimensions from nomic-embed-text, got {dim}")

    # 2. Recreate Chroma Collection
    chroma_path = settings.VECTOR_DB_PATH
    print(f"Chroma DB path: {chroma_path}")
    os.makedirs(chroma_path, exist_ok=True)
    chroma_client = chromadb.PersistentClient(
        path=chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False)
    )

    existing_collections = [c.name for c in chroma_client.list_collections()]
    if "mrpl_knowledge" in existing_collections:
        print("Deleting old Chroma collection 'mrpl_knowledge'...")
        chroma_client.delete_collection("mrpl_knowledge")

    print("Creating fresh Chroma collection 'mrpl_knowledge'...")
    chroma_client.create_collection("mrpl_knowledge")

    # 3. Clean up existing Document records in SQLite for the reports
    target_files = [
        "Pump_P204_Inspection_Report.txt",
        "Pump_P204_Maintenance_Report.txt"
    ]

    async with AsyncSessionLocal() as session:
        print("Cleaning up old Document records in SQLite...")
        for fname in target_files:
            stmt = select(Document).where(Document.filename == fname, Document.owner_id == ADMIN_USER_ID)
            res = await session.execute(stmt)
            docs = res.scalars().all()
            for doc in docs:
                v_stmt = select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id)
                v_res = await session.execute(v_stmt)
                v_ids = [r[0] for r in v_res.all()]
                if v_ids:
                    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(v_ids)))
                    await session.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(v_ids)))
                await session.delete(doc)
        await session.commit()
        print("Cleaned up old SQLite records.")

    # 4. Ingest documents into fresh Chroma store with Ollama embeddings
    parser_registry = ParserRegistry()
    chunker = TextChunker(chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
    vector_store = ChromaVectorStore(collection_name="mrpl_knowledge")
    rag_service = RAGService(
        parser_registry=parser_registry,
        chunker=chunker,
        embedding_provider=embedder,
        vector_store=vector_store
    )

    uploads_dir = Path(backend_dir) / "data" / "uploads"
    for fname in target_files:
        fpath = uploads_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Source file not found: {fpath}")

        print(f"\nIngesting {fname} for admin ({ADMIN_USER_ID})...")
        with open(fpath, "rb") as f:
            file_bytes = f.read()

        result = await rag_service.ingest_document(
            file_bytes=file_bytes,
            filename=fname,
            mime_type="text/plain",
            owner_id=ADMIN_USER_ID
        )
        print(f"Result for {fname}: status={result.status}, chunks={result.chunks_processed}, doc_id={result.document_id}")

    # 5. Verify indexed collection
    coll = chroma_client.get_collection("mrpl_knowledge")
    count = coll.count()
    print(f"\nChroma 'mrpl_knowledge' total vectors: {count}")
    
    sample = coll.get(limit=1, include=["embeddings", "metadatas", "documents"])
    if sample["embeddings"] is not None and len(sample["embeddings"]) > 0:
        actual_dim = len(sample["embeddings"][0])
        print(f"Sample embedding vector dimension in Chroma: {actual_dim}")
        assert actual_dim == 768, f"Expected dimension 768, got {actual_dim}"
    else:
        # Check by querying
        q_vec = await embedder.embed_text("test")
        assert len(q_vec) == 768
        res = coll.query(query_embeddings=[q_vec], n_results=1)
        print(f"Verified query against Chroma succeeded, returned {len(res['ids'][0])} results.")

    # 6. Test retrieval for Pump P204
    from app.core.rag.schemas import RetrievalQuery
    test_query = RetrievalQuery(
        query="According to the Pump P204 inspection report, what abnormalities were identified?",
        top_k=3,
        owner_id=ADMIN_USER_ID
    )
    search_results = await rag_service.search_documents(test_query)
    print(f"\nVerification Retrieval test returned {len(search_results)} candidates:")
    for r in search_results:
        print(f" - [{r.filename}] (score: {r.score:.4f}): {r.content[:120]}...")

    print("\nRE-INDEX MIGRATION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(reindex())
