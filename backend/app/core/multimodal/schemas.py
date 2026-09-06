from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Limits Configuration
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_PIXELS = 16_000_000
MAX_IMAGES_PER_REQUEST = 3
MAX_TOTAL_IMAGE_BYTES = 15 * 1024 * 1024 # 15 MB
MAX_OCR_TEXT_BYTES = 10 * 1024 # 10 KB
MAX_PROCESSING_SECONDS = 15

# Allowed standard mime types
ALLOWED_MIME_TYPES = {
    "image/jpeg": ["jpg", "jpeg"],
    "image/png": ["png"],
    "image/webp": ["webp"]
}

class AttachmentResponse(BaseModel):
    id: str
    owner_id: str
    filename: str
    media_type: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    processing_status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ProcessingError(Exception):
    pass

class MediaValidationError(Exception):
    pass
