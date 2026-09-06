import os
import anyio
from pathlib import Path
from app.core.config import settings
from app.core.multimodal.schemas import ProcessingError

class LocalStorageProvider:
    def __init__(self, base_dir: str = settings.ATTACHMENT_DIR):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_safe_path(self, attachment_id: str) -> Path:
        # Prevents path traversal by ensuring the attachment_id contains no slashes
        if "/" in attachment_id or "\\" in attachment_id or ".." in attachment_id:
            raise ProcessingError("Invalid attachment ID")
        
        path = (self.base_dir / attachment_id).resolve()
        
        # Double check it hasn't escaped the base_dir
        if not path.is_relative_to(self.base_dir):
            raise ProcessingError("Path traversal detected")
            
        return path

    async def save_file(self, attachment_id: str, content: bytes) -> str:
        path = self._get_safe_path(attachment_id)
        anyio_path = anyio.Path(path)
        await anyio_path.write_bytes(content)
        return str(path)

    async def read_file(self, attachment_id: str) -> bytes:
        path = self._get_safe_path(attachment_id)
        if not path.exists():
            raise ProcessingError("Attachment file not found")
        anyio_path = anyio.Path(path)
        return await anyio_path.read_bytes()

    def delete_file(self, attachment_id: str) -> bool:
        path = self._get_safe_path(attachment_id)
        if path.exists():
            path.unlink()
            return True
        return False
