from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, BackgroundTasks
from typing import Dict, Any, List
from datetime import datetime

from app.core.rag.schemas import IngestionResult, RetrievalQuery, RetrievalResult
from app.core.rag.errors import RAGError, FileValidationError, DocumentNotFoundError
from app.dependencies import get_current_user
from app.db.models import User

router = APIRouter()

@router.post("/documents", response_model=IngestionResult)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a document for ingestion into the RAG system.
    """
    import os
    rag_service = request.app.state.rag_service
    
    file_bytes = await file.read()
    
    # Block path traversal safely
    safe_filename = os.path.basename(file.filename)
    
    try:
        result = await rag_service.ingest_document(
            file_bytes=file_bytes,
            filename=safe_filename,
            mime_type=file.content_type,
            owner_id=current_user.id
        )
        return result
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RAGError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/documents/{document_id}")
async def delete_document(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user)
):
    rag_service = request.app.state.rag_service
    try:
        await rag_service.delete_document(document_id, owner_id=current_user.id)
        return {"status": "SUCCESS"}
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except RAGError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search", response_model=List[RetrievalResult])
async def search_documents(
    request: Request,
    query: RetrievalQuery,
    current_user: User = Depends(get_current_user)
):
    rag_service = request.app.state.rag_service
    
    # Enforce ownership scope
    query.owner_id = current_user.id
    
    try:
        results = await rag_service.search_documents(query)
        return results
    except RAGError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents")
async def list_documents(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    rag_service = request.app.state.rag_service
    try:
        results = await rag_service.list_documents(owner_id=current_user.id)
        return results
    except RAGError as e:
        raise HTTPException(status_code=500, detail=str(e))

