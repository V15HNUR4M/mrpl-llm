import os
import re
import uuid
import json
import anyio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

MIME_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

DEFAULT_EXTENSIONS = {
    "markdown": ".md",
    "md": ".md",
    "docx": ".docx",
    "pdf": ".pdf",
    "xlsx": ".xlsx",
}


def sanitize_filename(candidate_name: str, ext: str = ".md") -> str:
    """
    Sanitizes a candidate filename:
    - Ensures lower-case alphanumeric with hyphens
    - Enforces desired extension
    - Prevents path traversal characters
    - Bounds length
    """
    cleaned = candidate_name.strip().lower()

    # Normalize desired extension
    if not ext.startswith("."):
        ext = f".{ext}"
    ext = ext.lower()

    # If candidate ends with any supported ext, strip it
    for supported_ext in [".md", ".docx", ".pdf", ".xlsx", ".markdown"]:
        if cleaned.endswith(supported_ext):
            cleaned = cleaned[:-len(supported_ext)]
            break

    # Replace whitespace and underscores with hyphens
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    # Strip non-alphanumeric and non-hyphen
    cleaned = re.sub(r"[^a-z0-9\-]", "", cleaned)
    # Collapse multiple hyphens
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")

    if not cleaned:
        cleaned = "report"

    if len(cleaned) > 50:
        cleaned = cleaned[:50].rstrip("-")

    return f"{cleaned}{ext}"


def derive_filename(user_message: str, conversation_title: Optional[str] = None, ext: str = ".md") -> str:
    """
    Derives a sensible, clean filename from prompt or conversation title.
    """
    text = user_message.strip()
    norm_ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    ext_escaped = re.escape(norm_ext)

    # Explicit named pattern: e.g. "named foo.md" or "as foo.docx"
    pattern = rf'(?:named|as|called|filename)\s+["\']?([a-zA-Z0-9_\-\.]+){ext_escaped}["\']?'
    named_match = re.search(pattern, text, re.IGNORECASE)
    if named_match:
        return sanitize_filename(named_match.group(1), ext=norm_ext)

    # Specific topics: e.g. "summarizing the infrastructure report"
    sum_match = re.search(
        r'summariz(?:ing|e)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]{3,30}?)(?:\s+(?:and|report|file|\.|$))',
        text,
        re.IGNORECASE
    )
    if sum_match:
        topic = sum_match.group(1).strip()
        return sanitize_filename(f"{topic}-summary", ext=norm_ext)

    # Specific system IDs: e.g. "SRV-DB01"
    id_match = re.search(r'\b([a-zA-Z]{2,}[-_][a-zA-Z0-9_\-]+)\b', text)
    if id_match:
        target_id = id_match.group(1).lower()
        return sanitize_filename(f"{target_id}-summary", ext=norm_ext)

    # Conversation title fallback
    if conversation_title and conversation_title.lower() not in ("new conversation", "new document", "new chat"):
        return sanitize_filename(conversation_title, ext=norm_ext)

    # General extraction
    cleaned = re.sub(
        r'\b(create|generate|export|downloadable|markdown|file|report|give|me|the|a|as|an|\.md|\.docx|\.pdf|\.xlsx|word|pdf|excel|spreadsheet)\b',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()
    words = cleaned.split()
    if words:
        slug = "-".join(words[:4])
        return sanitize_filename(f"{slug}-report", ext=norm_ext)

    return f"report{norm_ext}"


def derive_markdown_filename(user_message: str, conversation_title: Optional[str] = None) -> str:
    """Backward compatibility helper for markdown."""
    return derive_filename(user_message, conversation_title, ext=".md")


class GeneratedFileManager:
    """
    Manages locally generated files (.md, .docx, .pdf, .xlsx) in a secure, backend-controlled directory.
    Enforces path traversal protection and user ownership authorization.
    """
    def __init__(self, storage_dir: Optional[str] = None):
        if not storage_dir:
            from app.core.config import settings
            base = Path(settings.UPLOAD_DIR).resolve().parent
            storage_dir = str(base / "generated_files")

        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_safe_path(self, file_id: str, suffix: str = ".md") -> Path:
        if not re.match(r"^[a-f0-9\-]{32,36}$", file_id, re.IGNORECASE):
            raise ValueError("Invalid file ID format")

        path = (self.storage_dir / f"{file_id}{suffix}").resolve()
        if not path.is_relative_to(self.storage_dir):
            raise PermissionError("Path traversal detected")
        return path

    async def save_file(
        self,
        owner_id: str,
        conversation_id: str,
        filename: str,
        content_bytes: bytes,
        file_type: str = "md"
    ) -> Dict[str, Any]:
        """
        Saves arbitrary file bytes (.md, .docx, .pdf, .xlsx) with companion metadata.
        """
        file_id = str(uuid.uuid4())
        norm_type = file_type.lower().lstrip(".")
        ext = DEFAULT_EXTENSIONS.get(norm_type, f".{norm_type}")
        safe_filename = sanitize_filename(filename, ext=ext)

        file_path = self._get_safe_path(file_id, suffix=ext)
        meta_path = self._get_safe_path(file_id, suffix=".json")

        size_bytes = len(content_bytes)

        # Write binary content
        anyio_file = anyio.Path(file_path)
        await anyio_file.write_bytes(content_bytes)

        metadata = {
            "file_id": file_id,
            "owner_id": owner_id,
            "conversation_id": conversation_id,
            "filename": safe_filename,
            "file_type": norm_type,
            "mime_type": MIME_TYPES.get(norm_type, "application/octet-stream"),
            "size_bytes": size_bytes,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        anyio_meta = anyio.Path(meta_path)
        await anyio_meta.write_text(json.dumps(metadata), encoding="utf-8")

        logger.info(f"Saved generated file {safe_filename} ({file_id}) for user {owner_id}")

        try:
            import asyncio
            from app.core.observability.service import get_observability_service
            from app.core.observability.schemas import TelemetryEventCreate
            obs = get_observability_service()
            asyncio.create_task(obs.emit_event(TelemetryEventCreate(
                event_type="file.generated",
                component="file_export",
                severity="INFO",
                user_id=owner_id,
                session_id=conversation_id,
                status="success",
                metadata={
                    "file_id": file_id,
                    "filename": safe_filename,
                    "file_type": norm_type,
                    "size_bytes": size_bytes
                }
            )))
        except Exception:
            pass

        return metadata

    async def save_markdown_file(
        self,
        owner_id: str,
        conversation_id: str,
        filename: str,
        content: str
    ) -> Dict[str, Any]:
        """Preserves backward-compatible markdown save method."""
        return await self.save_file(
            owner_id=owner_id,
            conversation_id=conversation_id,
            filename=filename,
            content_bytes=content.encode("utf-8"),
            file_type="md"
        )

    async def get_file_metadata(self, file_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves metadata and verifies ownership.
        """
        try:
            meta_path = self._get_safe_path(file_id, suffix=".json")
            if not meta_path.exists():
                return None
            anyio_meta = anyio.Path(meta_path)
            content = await anyio_meta.read_text(encoding="utf-8")
            data = json.loads(content)
            if data.get("owner_id") != owner_id:
                return None
            return data
        except Exception:
            return None

    def get_file_path(self, file_id: str, file_type: Optional[str] = None) -> Path:
        """
        Resolves safe file path. If file_type is known, checks directly.
        Otherwise scans storage directory for file matching file_id.* (excluding .json).
        """
        if file_type:
            norm_type = file_type.lower().lstrip(".")
            ext = DEFAULT_EXTENSIONS.get(norm_type, f".{norm_type}")
            return self._get_safe_path(file_id, suffix=ext)

        # Check metadata file if present
        meta_path = self._get_safe_path(file_id, suffix=".json")
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                ft = data.get("file_type", "md")
                ext = DEFAULT_EXTENSIONS.get(ft, f".{ft}")
                return self._get_safe_path(file_id, suffix=ext)
            except Exception:
                pass

        # Fallback to .md
        return self._get_safe_path(file_id, suffix=".md")
