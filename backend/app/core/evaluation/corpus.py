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


SYSTEM_EVAL_USER_ID = "system_eval_runner"
SYSTEM_EVAL_USERNAME = "eval_runner"
SYSTEM_EVAL_ROLE = "SYSTEM"


async def get_or_create_system_eval_user() -> str:
    """
    Idempotently ensures that the dedicated system evaluation runner user exists.
    """
    from app.db.database import AsyncSessionLocal
    from app.db.models import User
    from app.core.security import get_password_hash
    from sqlalchemy import select
    import secrets

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.id == SYSTEM_EVAL_USER_ID))
        user = res.scalar_one_or_none()
        if not user:
            res_name = await session.execute(select(User).where(User.username == SYSTEM_EVAL_USERNAME))
            user = res_name.scalar_one_or_none()
        
        if not user:
            user = User(
                id=SYSTEM_EVAL_USER_ID,
                username=SYSTEM_EVAL_USERNAME,
                email="eval_runner@mrpl.local",
                password_hash=get_password_hash(secrets.token_urlsafe(32)),
                display_name="Evaluation Runner",
                role=SYSTEM_EVAL_ROLE,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            return user.id
        return user.id


async def ensure_evaluation_corpus_indexed(rag_service: RAGService, owner_id: Optional[str] = None) -> Dict[str, str]:
    """
    Ensures that the canonical evaluation corpus documents are indexed in the
    real production RAG system (Chroma vector store via nomic-embed-text) under
    the dedicated system_eval_runner with access_scope="EVALUATION".
    Returns mapping of {filename: document_id}.
    """
    from app.db.database import AsyncSessionLocal
    from app.db.models import Document
    from sqlalchemy import select

    resolved_owner_id = owner_id or await get_or_create_system_eval_user()

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Document.id, Document.filename).where(
                Document.owner_id == resolved_owner_id,
                Document.access_scope == "EVALUATION"
            )
        )
        existing_docs = res.all()
        existing_map = {fn: did for did, fn in existing_docs}

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
                access_scope="EVALUATION",
            )
            doc_ids[filename] = res.document_id

    return doc_ids

