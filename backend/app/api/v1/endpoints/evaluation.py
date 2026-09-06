from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.db.models import User
from app.core.evaluation.schemas import EvaluationSummary, EvaluationDataset
from app.core.evaluation.dataset import MRPL_BENCHMARK_V1
from app.core.evaluation.runner import EvaluationRunner

router = APIRouter()


@router.get("/dataset", response_model=Dict[str, Any])
async def get_benchmark_dataset_info(
    current_user: User = Depends(get_current_user),
):
    """
    Returns metadata and overview of the evaluation benchmark dataset.
    Requires authenticated session.
    """
    is_admin = bool(str(current_user.role) == "ADMIN")
    cases_summary = []
    for c in MRPL_BENCHMARK_V1.cases:
        item = {
            "case_id": c.case_id,
            "category": c.category.value,
            "name": c.name,
            "description": c.description,
            "is_adversarial": c.is_adversarial,
        }
        if is_admin:
            item["thresholds"] = c.thresholds
            item["expected_sources"] = c.expected_sources
        cases_summary.append(item)

    return {
        "dataset_id": MRPL_BENCHMARK_V1.dataset_id,
        "version": MRPL_BENCHMARK_V1.version,
        "description": MRPL_BENCHMARK_V1.description,
        "total_cases": len(MRPL_BENCHMARK_V1.cases),
        "cases": cases_summary,
    }


@router.get("/latest", response_model=Dict[str, Any])
async def get_latest_evaluation(
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves the most recent evaluation benchmark summary.
    """
    latest = EvaluationRunner.get_latest_summary()
    if not latest:
        return {
            "status": "NO_RUNS",
            "message": "No evaluation run has been executed yet. Trigger a run via POST /api/v1/evaluation/run.",
            "summary": None,
        }
    return {
        "status": "AVAILABLE",
        "summary": latest.model_dump(),
    }


@router.post("/run", response_model=EvaluationSummary, status_code=200)
async def run_evaluation_benchmark(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Triggers an evaluation benchmark run across the sovereign system.
    This is a privileged operational action and requires ADMIN role.
    """
    is_admin = bool(str(current_user.role) == "ADMIN")
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin authorization required to trigger evaluation benchmark runs.",
        )

    # Initialize runner with real services from app.state
    runner = EvaluationRunner(
        rag_service=getattr(request.app.state, "rag_service", None),
        agent_harness=getattr(request.app.state, "agent_harness", None),
        tool_executor=getattr(request.app.state, "authorized_tool_executor", None)
        or getattr(request.app.state, "tool_executor", None),
        model_gateway=getattr(request.app.state, "gateway", None),
        workflow_engine=getattr(request.app.state, "workflow_engine", None),
        multimodal_service=getattr(request.app.state, "multimodal_service", None),
    )

    summary = await runner.run_dataset(MRPL_BENCHMARK_V1)
    return summary
