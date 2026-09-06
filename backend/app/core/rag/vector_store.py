from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.rag.schemas import DocumentChunk, RetrievalResult
from app.core.rag.errors import VectorStoreError

class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, chunks: List[DocumentChunk], embeddings: List[List[float]]):
        pass

    @abstractmethod
    async def delete_by_document(self, document_version_id: str):
        pass
        
    @abstractmethod
    async def delete_by_document_id(self, document_id: str):
        pass

    @abstractmethod
    async def similarity_search(self, query_embedding: List[float], top_k: int, filters: Dict[str, Any]) -> List[RetrievalResult]:
        pass

class ChromaVectorStore(VectorStore):
    def __init__(self, collection_name: str = "mrpl_knowledge"):
        os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
        # We use a persistent client in the configured path
        self.client = chromadb.PersistentClient(path=settings.VECTOR_DB_PATH, settings=ChromaSettings(anonymized_telemetry=False))
        # Ensure collection exists
        self.collection = self.client.get_or_create_collection(name=collection_name)

    async def upsert(self, chunks: List[DocumentChunk], embeddings: List[List[float]]):
        if not chunks:
            return
            
        if len(chunks) != len(embeddings):
            raise VectorStoreError(f"Mismatched chunks ({len(chunks)}) and embeddings ({len(embeddings)})")

        ids = [chunk.chunk_id for chunk in chunks]
        texts = [chunk.content for chunk in chunks]
        
        # Build metadata list, ensuring all values are strings, ints, or floats for Chroma
        metadatas = []
        for chunk in chunks:
            meta = {
                "document_id": chunk.document_id,
                "document_version_id": chunk.document_version_id,
                "chunk_index": chunk.chunk_index,
            }
            if chunk.page_number is not None:
                meta["page_number"] = chunk.page_number
            if chunk.section:
                meta["section"] = chunk.section
                
            # Add other primitive metadata
            for k, v in chunk.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
            
            metadatas.append(meta)

        try:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to upsert to Chroma: {str(e)}")

    async def delete_by_document(self, document_version_id: str):
        try:
            self.collection.delete(
                where={"document_version_id": document_version_id}
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to delete document version {document_version_id}: {str(e)}")

    async def delete_by_document_id(self, document_id: str):
        try:
            self.collection.delete(
                where={"document_id": document_id}
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to delete document {document_id}: {str(e)}")

    async def similarity_search(self, query_embedding: List[float], top_k: int, filters: Dict[str, Any]) -> List[RetrievalResult]:
        try:
            # Format filters for chroma
            where = {}
            if filters:
                if len(filters) == 1:
                    where = filters
                else:
                    where = {"$and": [{k: v} for k, v in filters.items()]}

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where if where else None,
                include=["documents", "metadatas", "distances"]
            )
            
            retrieval_results = []
            if not results["ids"] or not results["ids"][0]:
                return retrieval_results
                
            for i in range(len(results["ids"][0])):
                chunk_id = results["ids"][0][i]
                content = results["documents"][0][i]
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if "distances" in results and results["distances"] else 0.0
                
                # Convert distance to a similarity score (assuming cosine distance or similar, where lower is better)
                # In Chroma default L2, distance is higher for dissimilar. We'll just invert or use raw distance.
                # Let's map it roughly to a score where higher is better for Context Engine ranking.
                # Assuming L2 distance, max distance depends on embedding space. We'll use 1 / (1 + distance)
                score = 1.0 / (1.0 + distance)

                retrieval_results.append(RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=metadata.get("document_id", ""),
                    document_version_id=metadata.get("document_version_id", ""),
                    content=content,
                    score=score,
                    page_number=metadata.get("page_number"),
                    section=metadata.get("section"),
                    filename=metadata.get("filename", "Unknown")
                ))

            return retrieval_results
        except Exception as e:
            raise VectorStoreError(f"Similarity search failed: {str(e)}")
