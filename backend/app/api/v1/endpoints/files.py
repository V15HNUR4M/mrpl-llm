from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.dependencies import get_current_user
from app.db.models import User
from app.services.file_export import GeneratedFileManager
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
file_manager = GeneratedFileManager()

@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Securely download a generated markdown file.
    Validates authentication, file ownership, and prevents path traversal.
    """
    try:
        metadata = await file_manager.get_file_metadata(file_id, current_user.id)
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found or access denied")

        file_type = metadata.get("file_type", "md")
        file_path = file_manager.get_file_path(file_id, file_type=file_type)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on server")

        safe_filename = metadata.get("filename", f"report.{file_type}")
        media_type = metadata.get("mime_type") or "application/octet-stream"

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=safe_filename,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"'
            }
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error serving file {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file")
