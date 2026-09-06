from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.db.uow import UnitOfWork, get_uow
from app.dependencies import get_current_user
from app.db.models import User, AuditEvent
from app.core.multimodal.service import MultimodalService
from app.core.multimodal.schemas import AttachmentResponse, MediaValidationError, ProcessingError
import json

router = APIRouter()

def get_multimodal_service(uow: UnitOfWork = Depends(get_uow)) -> MultimodalService:
    return MultimodalService(uow)

@router.post("/", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: MultimodalService = Depends(get_multimodal_service),
    uow: UnitOfWork = Depends(get_uow)
):
    content = await file.read()
    
    try:
        attachment = await service.upload_attachment(
            owner_id=current_user.id,
            filename=file.filename,
            content=content
        )
        
        async with uow as u:
            u.audit.add(AuditEvent(
                action="attachment_uploaded",
                user_id=current_user.id,
                resource_type="attachment",
                resource_id=attachment.id,
                metadata_={"filename": file.filename}
            ))
            await u.commit()
            
        return attachment
    except MediaValidationError as e:
        async with uow as u:
            u.audit.add(AuditEvent(
                action="attachment_validation_failed",
                user_id=current_user.id,
                resource_type="attachment",
                resource_id="N/A",
                metadata_={"filename": file.filename, "error": str(e)}
            ))
            await u.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except ProcessingError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[AttachmentResponse])
async def list_attachments(
    current_user: User = Depends(get_current_user),
    service: MultimodalService = Depends(get_multimodal_service)
):
    return await service.list_attachments(current_user.id)

@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    service: MultimodalService = Depends(get_multimodal_service),
    uow: UnitOfWork = Depends(get_uow)
):
    attachment = await service.get_attachment(current_user.id, attachment_id)
    if not attachment:
        async with uow as u:
            u.audit.add(AuditEvent(
                action="attachment_access_denied",
                user_id=current_user.id,
                resource_type="attachment",
                resource_id=attachment_id,
                metadata_={}
            ))
            await u.commit()
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment

@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    service: MultimodalService = Depends(get_multimodal_service),
    uow: UnitOfWork = Depends(get_uow)
):
    success = await service.delete_attachment(current_user.id, attachment_id)
    if not success:
        async with uow as u:
            u.audit.add(AuditEvent(
                action="attachment_access_denied",
                user_id=current_user.id,
                resource_type="attachment",
                resource_id=attachment_id,
                metadata_={}
            ))
            await u.commit()
        raise HTTPException(status_code=404, detail="Attachment not found")
        
    async with uow as u:
        u.audit.add(AuditEvent(
            action="attachment_deleted",
            user_id=current_user.id,
            resource_type="attachment",
            resource_id=attachment_id,
            metadata_={}
        ))
        await u.commit()
        
    return {"status": "deleted"}
