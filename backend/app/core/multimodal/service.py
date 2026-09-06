import hashlib
import asyncio
import logging
from typing import Optional, List
from app.db.uow import UnitOfWork
from app.db.models import Attachment
from app.core.multimodal.schemas import ProcessingError, MediaValidationError, MAX_PROCESSING_SECONDS
from app.core.multimodal.validators import validate_image
from app.core.multimodal.storage import LocalStorageProvider

logger = logging.getLogger(__name__)

class MultimodalService:
    def __init__(self, uow: UnitOfWork, storage: LocalStorageProvider = None, ocr_provider = None, observability_service = None):
        self.uow = uow
        self.storage = storage or LocalStorageProvider()
        self.observability_service = observability_service
        if ocr_provider is not None:
            self.ocr_provider = ocr_provider
        else:
            from app.core.multimodal.ocr import TesseractOCRProvider
            self.ocr_provider = TesseractOCRProvider()

    async def upload_attachment(self, owner_id: str, filename: str, content: bytes) -> Attachment:
        # 1. Validation
        try:
            media_type, width, height = validate_image(content)
        except MediaValidationError as e:
            # Audit event for rejection could be recorded here
            raise e

        checksum = hashlib.sha256(content).hexdigest()
        size_bytes = len(content)

        # 2. Persistence (Metadata)
        attachment = Attachment(
            owner_id=owner_id,
            filename=filename,
            media_type=media_type,
            size_bytes=size_bytes,
            checksum=checksum,
            storage_path="", # populated later
            width=width,
            height=height,
            processing_status="PENDING"
        )
        
        async with self.uow as uow:
            uow.attachments.add(attachment)
            await uow.commit()

        # 3. Processing (Storage) - bounded by timeout
        try:
            async with asyncio.timeout(MAX_PROCESSING_SECONDS):
                path = await self.storage.save_file(attachment.id, content)
                
            async with self.uow as uow:
                db_attachment = await uow.attachments.get_by_id(attachment.id)
                db_attachment.storage_path = path
                db_attachment.processing_status = "READY"
                await uow.commit()
                await self._emit_attachment_telemetry(owner_id, "success", len(content))
                return db_attachment
                
        except TimeoutError:
            async with self.uow as uow:
                db_attachment = await uow.attachments.get_by_id(attachment.id)
                db_attachment.processing_status = "FAILED"
                await uow.commit()
            await self._emit_attachment_telemetry(owner_id, "timeout", len(content), error_type="ProcessingTimeout")
            raise ProcessingError("Processing timed out")
        except Exception as e:
            async with self.uow as uow:
                db_attachment = await uow.attachments.get_by_id(attachment.id)
                db_attachment.processing_status = "FAILED"
                await uow.commit()
            logger.error(f"Attachment processing failed: {e}")
            await self._emit_attachment_telemetry(owner_id, "failed", len(content), error_type=type(e).__name__)
            raise ProcessingError(f"Failed to process attachment: {str(e)}")

    async def _emit_attachment_telemetry(self, owner_id: str, status: str, size_bytes: int, error_type: str = None) -> None:
        if not self.observability_service:
            return
        try:
            from app.core.observability.schemas import TelemetryEventCreate
            severity = "ERROR" if status in ("failed", "timeout") else "INFO"
            event = TelemetryEventCreate(
                event_type="multimodal.attachment",
                component="multimodal",
                severity=severity,
                user_id=owner_id or None,
                status=status,
                error_type=error_type,
                metadata={"size_bytes": size_bytes}
            )
            await self.observability_service.emit_event(event)
        except Exception:
            pass

    async def get_attachment(self, owner_id: str, attachment_id: str) -> Attachment:
        async with self.uow as uow:
            attachment = await uow.attachments.get_by_id(attachment_id)
            if not attachment or attachment.owner_id != owner_id:
                return None
            return attachment

    async def list_attachments(self, owner_id: str) -> List[Attachment]:
        async with self.uow as uow:
            return await uow.attachments.list_for_owner(owner_id)

    async def delete_attachment(self, owner_id: str, attachment_id: str) -> bool:
        async with self.uow as uow:
            attachment = await uow.attachments.get_by_id(attachment_id)
            if not attachment or attachment.owner_id != owner_id:
                return False
            
            # Delete file
            self.storage.delete_file(attachment_id)
            
            # Delete metadata
            await uow.attachments.delete(attachment.id)
            await uow.commit()
            return True

    async def get_attachment_content(self, owner_id: str, attachment_id: str) -> Optional[bytes]:
        attachment = await self.get_attachment(owner_id, attachment_id)
        if not attachment or attachment.processing_status != "READY":
            return None
        return await self.storage.read_file(attachment.id)

    async def get_attachment_content_system(self, attachment_id: str) -> Optional[bytes]:
        async with self.uow as uow:
            attachment = await uow.attachments.get_by_id(attachment_id)
        if not attachment or attachment.processing_status != "READY":
            return None
        return await self.storage.read_file(attachment.id)

    async def extract_text_system(self, attachment_id: str) -> Optional[str]:
        async with self.uow as uow:
            att = await uow.attachments.get_by_id(attachment_id)
        if not att or not att.storage_path:
            return None
        result = self.ocr_provider.extract_text(att.storage_path)
        # Emit OCR telemetry
        try:
            if self.observability_service:
                from app.core.observability.schemas import TelemetryEventCreate
                event = TelemetryEventCreate(
                    event_type="multimodal.ocr",
                    component="multimodal",
                    severity="INFO",
                    user_id=att.owner_id or None,
                    status="success" if result else "empty",
                    metadata={"attachment_id": attachment_id, "has_text": bool(result)}
                )
                await self.observability_service.emit_event(event)
        except Exception:
            pass
        return result
