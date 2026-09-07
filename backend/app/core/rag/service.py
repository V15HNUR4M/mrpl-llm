import os
import hashlib
from typing import List, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Document, DocumentVersion, DocumentChunk as DBDocumentChunk

from app.core.rag.schemas import (
    DocumentMetadata, ParsedDocument, DocumentChunk, 
    IngestionResult, RetrievalQuery, RetrievalResult
)
from app.core.rag.errors import RAGError, FileValidationError, DocumentNotFoundError
from app.core.rag.parser import ParserRegistry
from app.core.rag.chunking import TextChunker
from app.core.rag.embeddings import EmbeddingProvider
from app.core.rag.vector_store import VectorStore

class RAGService:
    def __init__(
        self,
        parser_registry: ParserRegistry,
        chunker: TextChunker,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        observability_service=None
    ):
        self.parser_registry = parser_registry
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.observability_service = observability_service

    def _calculate_checksum(self, file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    def _validate_file(self, file_bytes: bytes, filename: str):
        if len(file_bytes) == 0:
            raise FileValidationError("File is empty")
        if len(file_bytes) > settings.MAX_UPLOAD_SIZE:
            raise FileValidationError(f"File exceeds maximum allowed size ({settings.MAX_UPLOAD_SIZE} bytes)")
        
        # Prevent path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise FileValidationError("Invalid filename")

    async def ingest_document(
        self, 
        file_bytes: bytes, 
        filename: str, 
        mime_type: str, 
        owner_id: Optional[str] = None,
        access_scope: str = "PRIVATE"
    ) -> IngestionResult:
        self._validate_file(file_bytes, filename)
        
        # Get file type (extension)
        file_type = ""
        if "." in filename:
            file_type = filename.rsplit(".", 1)[-1].lower()

        checksum = self._calculate_checksum(file_bytes)

        # 1. Idempotency Check
        async with AsyncSessionLocal() as session:
            stmt = select(Document).where(
                Document.filename == filename,
                Document.owner_id == owner_id
            )
            result = await session.execute(stmt)
            existing_doc = result.scalars().first()

            if existing_doc and existing_doc.checksum == checksum and existing_doc.status == "INDEXED":
                return IngestionResult(
                    document_id=existing_doc.id,
                    document_version_id="", # We skip this for idempotent returns where not strictly needed or fetch it
                    status="SKIPPED",
                    chunks_processed=0,
                    message="Document with identical content already indexed."
                )
            
            # 2. Extract and Parse
            parser = self.parser_registry.get_parser(mime_type, file_type)
            metadata = {"filename": filename, "access_scope": access_scope}
            if owner_id:
                metadata["owner_id"] = owner_id
            parsed_doc = parser.parse(file_bytes, metadata=metadata)

            # Create Database entries
            if not existing_doc:
                doc = Document(
                    owner_id=owner_id,
                    filename=filename,
                    file_type=file_type,
                    mime_type=mime_type,
                    file_size=len(file_bytes),
                    checksum=checksum,
                    access_scope=access_scope,
                    status="PROCESSING"
                )
                session.add(doc)
                await session.commit()
                await session.refresh(doc)
                new_version_number = 1

                # Persist raw file for local tool resolution
                try:
                    from pathlib import Path
                    from app.core.config import settings
                    upload_path = Path(settings.UPLOAD_DIR).resolve()
                    upload_path.mkdir(parents=True, exist_ok=True)
                    ext = f".{file_type}" if file_type else ""
                    (upload_path / f"{doc.id}{ext}").write_bytes(file_bytes)
                except Exception as e:
                    logger.warning(f"Failed to persist raw upload {doc.id}: {e}")
            else:
                doc = existing_doc
                doc.status = "PROCESSING"
                doc.updated_at = datetime.utcnow()
                await session.commit()
                try:
                    from pathlib import Path
                    from app.core.config import settings
                    upload_path = Path(settings.UPLOAD_DIR).resolve()
                    upload_path.mkdir(parents=True, exist_ok=True)
                    ext = f".{file_type}" if file_type else ""
                    (upload_path / f"{doc.id}{ext}").write_bytes(file_bytes)
                except Exception:
                    pass
                
                # Fetch highest version number
                from sqlalchemy import func
                version_stmt = select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == doc.id)
                version_res = await session.execute(version_stmt)
                max_version = version_res.scalar() or 0
                new_version_number = max_version + 1

            doc_version = DocumentVersion(
                document_id=doc.id,
                version_number=new_version_number,
                checksum=checksum,
                is_current=False # Kept False until indexing finishes
            )
            session.add(doc_version)
            await session.commit()
            await session.refresh(doc_version)
            
            try:
                # 3. Chunking
                chunks = self.chunker.chunk(parsed_doc, document_id=doc.id, document_version_id=doc_version.id)
                
                # 4. Embeddings
                texts_to_embed = [c.content for c in chunks]
                embeddings = await self.embedding_provider.embed_batch(texts_to_embed)

                # 5. Vector Store Upsert
                # Inject document_version_id into metadata for all chunks
                for c in chunks:
                    c.metadata["document_version_id"] = doc_version.id
                    
                await self.vector_store.upsert(chunks, embeddings)

                # 6. Database finalizing
                for c in chunks:
                    db_chunk = DBDocumentChunk(
                        id=c.chunk_id,
                        document_version_id=doc_version.id,
                        chunk_index=c.chunk_index,
                        page_number=c.page_number,
                        section=c.section
                    )
                    session.add(db_chunk)
                
                # Mark old versions as not current, new version as current
                from sqlalchemy import update
                await session.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.document_id == doc.id)
                    .where(DocumentVersion.id != doc_version.id)
                    .values(is_current=False)
                )
                
                doc_version.is_current = True
                doc.status = "INDEXED"
                doc.checksum = checksum
                await session.commit()
                
                # 7. Cleanup old vectors asynchronously or fire-and-forget (we await it here to ensure test passing)
                # We could delete by old version IDs or delete all chunks of this doc that don't match this version,
                # but chroma might only support simple filters. If we added document_version_id to Chroma metadata,
                # we could ideally delete by that. But chroma delete_by_document_id deletes ALL vectors for the doc.
                # Since we just added the new vectors, if we call delete_by_document_id we delete the NEW vectors too!
                # Wait, if Chroma doesn't support deleting by version, we have to keep them and filter on search!
                # Or we can write `delete_by_document_version_id` if Chroma supports it? Yes, we can!
                # Since VectorStore is abstract, we will assume it supports it or we filter on search.
                # For now, we will let search_documents filter by `document_version_id`.

                return IngestionResult(
                    document_id=doc.id,
                    document_version_id=doc_version.id,
                    status="SUCCESS",
                    chunks_processed=len(chunks),
                    message="Document successfully ingested and indexed."
                )
            except Exception as e:
                # Rollback status
                doc.status = "FAILED"
                await session.commit()
                raise RAGError(f"Ingestion failed: {str(e)}")

    async def search_documents(self, query: RetrievalQuery) -> List[RetrievalResult]:
        import time
        t0 = time.time()
        # 1. Embed query
        query_embedding = await self.embedding_provider.embed_text(query.query)

        # 2. Construct filters
        filters = {}
        if query.owner_id:
            filters["owner_id"] = query.owner_id
        
        # We will fetch active version IDs if document_ids are specified to pass to Chroma directly if possible
        active_version_ids = []
        async with AsyncSessionLocal() as session:
            if query.document_ids:
                stmt = select(DocumentVersion.id).join(Document, Document.id == DocumentVersion.document_id).where(
                    DocumentVersion.document_id.in_(query.document_ids),
                    DocumentVersion.is_current == True
                )
                if query.owner_id:
                    stmt = stmt.where(Document.owner_id == query.owner_id)
                res = await session.execute(stmt)
                active_version_ids = [row[0] for row in res.all()]
                
                # If document_ids were explicitly specified and none belong to owner, return empty
                if not active_version_ids:
                    return []

                if len(query.document_ids) == 1 and active_version_ids:
                    filters["document_version_id"] = active_version_ids[0]

        # 3. Search Vector Store (fetch more to account for stale versions filtering)
        results = await self.vector_store.similarity_search(
            query_embedding=query_embedding,
            top_k=query.top_k * 5, # Fetch extra for post-filtering
            filters=filters
        )

        # 4. Filter by score
        filtered_results = [r for r in results if r.score >= query.min_score]
        
        # 5. Authoritative Active-Version Filter
        # Do not rely solely on vector deletion; verify against SQLite
        valid_results = []
        async with AsyncSessionLocal() as session:
            # Gather unique version IDs from results
            version_ids_in_results = list(set([r.document_version_id for r in filtered_results if r.document_version_id]))
            
            active_versions_map = {}
            if version_ids_in_results:
                stmt = select(DocumentVersion.id).join(Document, Document.id == DocumentVersion.document_id).where(
                    DocumentVersion.id.in_(version_ids_in_results),
                    DocumentVersion.is_current == True
                )
                if query.owner_id:
                    stmt = stmt.where(Document.owner_id == query.owner_id)
                res = await session.execute(stmt)
                active_versions_map = {row[0]: True for row in res.all()}
                
            for r in filtered_results:
                vid = r.document_version_id
                if vid and vid in active_versions_map:
                    valid_results.append(r)
                elif not vid and not query.owner_id:
                    # Fallback for unowned legacy chunks inserted before versioning was added
                    valid_results.append(r)

        results_to_return = valid_results[:query.top_k]

        # Emit RAG telemetry
        try:
            if self.observability_service:
                from app.core.observability.schemas import TelemetryEventCreate
                dur = int((time.time() - t0) * 1000)
                event = TelemetryEventCreate(
                    event_type="rag.query",
                    component="rag",
                    severity="INFO",
                    user_id=query.owner_id or None,
                    duration_ms=dur,
                    status="success",
                    metadata={
                        "result_count": len(results_to_return),
                        "empty_result": len(results_to_return) == 0,
                        "top_k": query.top_k
                    }
                )
                await self.observability_service.emit_event(event)
        except Exception:
            pass

        return results_to_return

    async def delete_document(self, document_id: str, owner_id: Optional[str] = None):
        async with AsyncSessionLocal() as session:
            stmt = select(Document).where(Document.id == document_id)
            result = await session.execute(stmt)
            doc = result.scalars().first()

            if not doc:
                raise DocumentNotFoundError(f"Document {document_id} not found")

            if owner_id and doc.owner_id != owner_id:
                raise DocumentNotFoundError(f"Document {document_id} not found") # Or AuthorizationError

            # 1. Delete from Vector Store first (so we don't leave stale searchable vectors if DB delete succeeds but vector fails)
            await self.vector_store.delete_by_document_id(document_id)

            # 2. Delete from relational DB
            await session.delete(doc)
            await session.commit()

    async def list_documents(self, owner_id: str) -> List[dict]:
        async with AsyncSessionLocal() as session:
            stmt = select(Document).where(
                Document.owner_id == owner_id,
                Document.access_scope != "EVALUATION"
            ).order_by(Document.created_at.desc())
            result = await session.execute(stmt)
            docs = result.scalars().all()
            
            return [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "status": d.status,
                    "file_type": d.file_type,
                    "file_size": d.file_size,
                    "created_at": d.created_at.isoformat(),
                    "updated_at": d.updated_at.isoformat()
                }
                for d in docs
            ]

    async def get_document_chunks(self, document_id: str, owner_id: str) -> List[RetrievalResult]:
        async with AsyncSessionLocal() as session:
            stmt = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
            res = await session.execute(stmt)
            doc = res.scalars().first()
            if not doc:
                return []

            v_stmt = select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_current == True
            )
            v_res = await session.execute(v_stmt)
            version = v_res.scalars().first()
            if not version:
                return []

        if hasattr(self.vector_store, "get_by_document_version"):
            return await self.vector_store.get_by_document_version(version.id, doc.filename)
        return []
