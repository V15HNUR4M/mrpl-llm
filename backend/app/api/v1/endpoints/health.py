import os
import tempfile
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine

router = APIRouter()

async def perform_liveness_check() -> Dict[str, Any]:
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }

async def check_database_readiness() -> Tuple[bool, Dict[str, Any]]:
    """Validates SQLite connectivity using SELECT 1."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            if val == 1:
                return True, {"status": "ok"}
            return False, {"status": "error", "detail": f"Unexpected scalar: {val}"}
    except Exception as e:
        return False, {"status": "error", "detail": str(e)}

async def check_vector_store_readiness(app: Any) -> Tuple[bool, Dict[str, Any]]:
    """Performs real lightweight Chroma collection metadata/count check."""
    try:
        rag_service = getattr(app.state, "rag_service", None)
        if rag_service and hasattr(rag_service, "vector_store"):
            vector_store = rag_service.vector_store
            if hasattr(vector_store, "collection"):
                count = vector_store.collection.count()
                return True, {
                    "status": "ok",
                    "collection": getattr(vector_store.collection, "name", "mrpl_knowledge"),
                    "count": count
                }
            return True, {"status": "ok", "detail": "vector_store active"}
        return True, {"status": "uninitialized"}
    except Exception as e:
        return False, {"status": "error", "detail": str(e)}

async def check_ollama_readiness() -> Tuple[bool, Dict[str, Any]]:
    """Validates reachability of Ollama and presence of required chat and embedding models."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                available_models = [m.get("name", "") for m in data.get("models", [])]
                
                chat_model = settings.DEFAULT_CHAT_MODEL
                embedding_model = settings.DEFAULT_EMBEDDING_MODEL
                
                missing_models = []
                if not any(chat_model in m or m.startswith(chat_model) for m in available_models):
                    missing_models.append(chat_model)
                    
                if settings.EMBEDDING_PROVIDER == "ollama":
                    if not any(embedding_model in m or m.startswith(embedding_model) for m in available_models):
                        missing_models.append(embedding_model)

                if missing_models:
                    return False, {
                        "status": "degraded",
                        "detail": f"Missing required model(s): {', '.join(missing_models)}",
                        "available_models": available_models,
                        "missing_models": missing_models
                    }
                return True, {
                    "status": "ok",
                    "chat_model": chat_model,
                    "embedding_model": embedding_model,
                    "available_models": available_models
                }
            return False, {
                "status": "unavailable",
                "detail": f"Ollama returned HTTP {resp.status_code}"
            }
    except Exception as e:
        return False, {
            "status": "unavailable",
            "detail": f"Cannot reach Ollama at {settings.OLLAMA_BASE_URL}: {str(e)}"
        }

async def check_storage_readiness() -> Tuple[bool, Dict[str, Any]]:
    """Validates writability of all storage paths."""
    storage_status = {}
    all_writable = True
    paths_to_verify = [
        ("uploads", settings.UPLOAD_DIR),
        ("attachments", settings.ATTACHMENT_DIR),
        ("vector_db", settings.VECTOR_DB_PATH),
    ]
    for label, path in paths_to_verify:
        try:
            os.makedirs(path, exist_ok=True)
            test_file = os.path.join(path, f".healthcheck_{os.getpid()}.tmp")
            with open(test_file, "w") as f:
                f.write("ok")
            if os.path.exists(test_file):
                os.remove(test_file)
            storage_status[label] = "writable"
        except Exception as e:
            storage_status[label] = f"error: {str(e)}"
            all_writable = False
    return all_writable, storage_status

async def perform_readiness_check(request: Request) -> Tuple[int, Dict[str, Any]]:
    components: Dict[str, Any] = {}
    is_ready = True

    # 1. Database
    db_ok, db_status = await check_database_readiness()
    components["database"] = db_status
    if not db_ok:
        is_ready = False

    # 2. Chroma Vector Store
    vs_ok, vs_status = await check_vector_store_readiness(request.app)
    components["vector_store"] = vs_status
    if not vs_ok:
        is_ready = False

    # 3. Ollama & Models
    ol_ok, ol_status = await check_ollama_readiness()
    components["ollama"] = ol_status
    if not ol_ok:
        is_ready = False

    # 4. Storage paths
    st_ok, st_status = await check_storage_readiness()
    components["storage"] = st_status
    if not st_ok:
        is_ready = False

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.ENVIRONMENT,
        "components": components
    }
    return status_code, payload

@router.get("/live", summary="Process Liveness Probe")
async def liveness():
    """Liveness probe: verifies the FastAPI application process is alive and responsive."""
    return await perform_liveness_check()

@router.get("/ready", summary="Dependency Readiness Probe")
async def readiness(request: Request, response: Response):
    """Readiness probe: validates database, vector store, Ollama reachability, and model availability."""
    code, payload = await perform_readiness_check(request)
    response.status_code = code
    return payload
