from typing import Dict, Any, List, Optional
from app.core.rag.service import RAGService
from app.core.rag.schemas import RetrievalQuery

EVALUATION_CORPUS_DOCS: Dict[str, str] = {
    "EVAL_DOC_001_Pump_P204_Inspection.txt": (
        "Pump P204 Inspection Report: Drive End (DE) bearing vibration velocity was measured at 7.2 mm/s "
        "at 1480 RPM operating frequency. Cavitation damage and minor pitting were observed on the impeller vanes. "
        "Immediate bearing replacement and dynamic balancing recommended within 48 hours to prevent shaft seizure."
    ),
    "EVAL_DOC_002_Pump_P204_Maintenance.txt": (
        "Pump P204 Maintenance Log: Bearing assembly replacement and laser shaft alignment completed on 2026-08-20 "
        "by Lead Technician J. Sharma. The lubrication reservoir was flushed and refilled with ISO VG 46 synthetic oil. "
        "Post-maintenance trial confirmed vibration velocity dropped to 1.8 mm/s under standard load."
    ),
    "EVAL_DOC_003_Boiler_B301_Specification.txt": (
        "Boiler B301 Technical Specification: Maximum continuous rating operating pressure is 42.5 bar with superheated "
        "steam temperature of 450 C. Thermal output capacity is 120 MWth. Overpressure relief valve lift trigger is "
        "calibrated at 46.0 bar. Primary fuel is sweet natural gas."
    ),
    "EVAL_DOC_004_Compressor_C502_Operating_Manual.txt": (
        "Compressor C502 Operating Manual: Two-stage centrifugal gas compressor with design suction pressure of 3.5 bar "
        "and final discharge pressure of 18.2 bar. Lube oil header pressure must be regulated strictly between 2.2 and 2.6 bar. "
        "Surge control valve opens at 17.8 bar differential."
    ),
    "EVAL_DOC_005_Turbine_T101_Safety_Protocol.txt": (
        "Turbine T101 Safety Protocol: Emergency overspeed trip trigger is calibrated at 3300 RPM representing 110% of "
        "rated operating speed. Minimum required cooling water circulation rate is 450 m3/h. Lube oil pressure falling below "
        "1.2 bar initiates an instantaneous automatic safety shutdown."
    ),
}


async def ensure_evaluation_corpus_indexed(rag_service: RAGService, owner_id: Optional[str] = None) -> Dict[str, str]:
    """
    Ensures that the canonical evaluation corpus documents are indexed in the
    real production RAG system (Chroma vector store via nomic-embed-text) under owner_id.
    Validates that owner_id exists in SQLite users table to satisfy foreign key constraints.
    Returns mapping of {filename: document_id}.
    """
    from app.db.database import AsyncSessionLocal
    from app.db.models import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        valid_user_id = None
        if owner_id:
            res = await session.execute(select(User.id).where(User.id == owner_id))
            valid_user_id = res.scalar_one_or_none()

        if not valid_user_id:
            # Fallback to superuser or any existing user
            res = await session.execute(select(User.id).order_by(User.created_at.asc()).limit(1))
            valid_user_id = res.scalar_one_or_none()

    resolved_owner_id = valid_user_id or owner_id or "eval_owner"

    existing_docs = await rag_service.list_documents(owner_id=resolved_owner_id)
    existing_map = {}
    for d in existing_docs:
        fn = d.get("filename") if isinstance(d, dict) else getattr(d, "filename", "")
        did = d.get("id") if isinstance(d, dict) else getattr(d, "id", "")
        if fn and did:
            existing_map[fn] = did

    doc_ids = {}
    for filename, content in EVALUATION_CORPUS_DOCS.items():
        if filename in existing_map:
            doc_ids[filename] = existing_map[filename]
        else:
            res = await rag_service.ingest_document(
                file_bytes=content.encode("utf-8"),
                filename=filename,
                mime_type="text/plain",
                owner_id=resolved_owner_id,
            )
            doc_ids[filename] = res.document_id

    return doc_ids
