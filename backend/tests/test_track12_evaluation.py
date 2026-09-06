import pytest
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.core.evaluation.schemas import (
    EvaluationCategory,
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationSummary,
)
from app.core.evaluation.metrics import (
    calculate_recall_at_k,
    calculate_precision_at_k,
    calculate_mrr,
    check_expected_facts,
    check_forbidden_facts,
    check_citation_faithfulness,
    check_no_answer_refusal,
    check_memory_conflict_supersession,
    check_tool_authorization_enforcement,
)
from app.core.evaluation.dataset import MRPL_BENCHMARK_V1
from app.core.evaluation.runner import EvaluationRunner, calculate_latency_percentiles
from app.core.evaluation.reporting import generate_evaluation_markdown_report, export_evaluation_json
from app.main import app
from app.core.config import settings
from app.dependencies import get_current_user
from app.db.models import User


# =============================================================================
# 1. Dataset Integrity & Category Coverage Tests
# =============================================================================

def test_dataset_integrity_valid():
    """Validates that MRPL_BENCHMARK_V1 passes structural integrity checks."""
    MRPL_BENCHMARK_V1.validate_integrity()
    assert MRPL_BENCHMARK_V1.dataset_id.lower() == "mrpl_benchmark_v1"
    assert len(MRPL_BENCHMARK_V1.cases) >= 55


def test_dataset_integrity_detects_duplicate_case_ids():
    """Ensures dataset validation catches duplicate case identifiers."""
    c1 = EvaluationCase(case_id="DUP-01", category=EvaluationCategory.RAG, name="Test 1")
    c2 = EvaluationCase(case_id="DUP-01", category=EvaluationCategory.RAG, name="Test 2")
    ds = EvaluationDataset(dataset_id="TEST", version="1.0", cases=[c1, c2])
    with pytest.raises(ValueError, match="Duplicate case_id"):
        ds.validate_integrity()


def test_dataset_integrity_detects_missing_name():
    """Ensures dataset validation catches incomplete case schemas."""
    c = EvaluationCase(case_id="NO-NAME", category=EvaluationCategory.RAG, name="")
    ds = EvaluationDataset(dataset_id="TEST", version="1.0", cases=[c])
    with pytest.raises(ValueError, match="missing name or category"):
        ds.validate_integrity()


def test_dataset_all_ten_categories_represented():
    """Verifies that all 10 distinct evaluation categories are present in the benchmark."""
    present_categories = {c.category for c in MRPL_BENCHMARK_V1.cases}
    assert len(present_categories) == 10
    for cat in EvaluationCategory:
        assert cat in present_categories, f"Category {cat} missing from benchmark dataset"


def test_dataset_has_at_least_55_distinct_cases():
    """Verifies that the benchmark dataset meets or exceeds the 55-case threshold."""
    assert len(MRPL_BENCHMARK_V1.cases) >= 55
    rag_cases = MRPL_BENCHMARK_V1.get_by_category(EvaluationCategory.RAG)
    hallucination_cases = MRPL_BENCHMARK_V1.get_by_category(EvaluationCategory.HALLUCINATION)
    adversarial_cases = MRPL_BENCHMARK_V1.get_by_category(EvaluationCategory.ADVERSARIAL)
    assert len(rag_cases) >= 5
    assert len(hallucination_cases) >= 10
    assert len(adversarial_cases) >= 10


# =============================================================================
# 2. Deterministic Retrieval Metrics Tests
# =============================================================================

def test_recall_at_k_calculation():
    retrieved = ["doc_a", "doc_b", "doc_c", "doc_d"]
    expected = ["doc_a", "doc_c"]
    assert calculate_recall_at_k(retrieved, expected, k=2) == 0.5  # doc_a in top-2, doc_c not
    assert calculate_recall_at_k(retrieved, expected, k=4) == 1.0  # both in top-4
    assert calculate_recall_at_k(retrieved, ["doc_z"], k=4) == 0.0


def test_precision_at_k_calculation():
    retrieved = ["doc_a", "doc_b", "doc_c", "doc_d"]
    expected = ["doc_a", "doc_b"]
    assert calculate_precision_at_k(retrieved, expected, k=2) == 1.0
    assert calculate_precision_at_k(retrieved, expected, k=4) == 0.5


def test_mrr_calculation():
    retrieved = ["doc_x", "doc_y", "target_doc", "doc_z"]
    assert calculate_mrr(retrieved, ["target_doc"]) == pytest.approx(1 / 3, 0.001)
    assert calculate_mrr(retrieved, ["not_present"]) == 0.0
    assert calculate_mrr(["target_doc"], ["target_doc"]) == 1.0


def test_k_boundary_enforcement():
    retrieved = ["doc_1", "doc_2"]
    # If k > len(retrieved), precision divides by k
    assert calculate_precision_at_k(retrieved, ["doc_1", "doc_2"], k=4) == 0.5


def test_retrieval_metrics_empty_inputs():
    assert calculate_recall_at_k([], ["doc_1"], k=5) == 0.0
    assert calculate_precision_at_k([], ["doc_1"], k=5) == 0.0
    assert calculate_mrr([], ["doc_1"]) == 0.0
    assert calculate_recall_at_k(["doc_1"], [], k=5) == 1.0


# =============================================================================
# 3. Grounding and Fact Checking Tests
# =============================================================================

def test_expected_facts_detection_all_present():
    text = "Pump P204 has high vibration at 7.2 mm/s due to bearing degradation on DE side."
    facts = ["7.2 mm/s", "bearing degradation", "Pump P204"]
    res = check_expected_facts(text, facts)
    assert res["passed"] is True
    assert res["fact_accuracy"] == 1.0
    assert len(res["missing_facts"]) == 0


def test_expected_facts_detection_missing_fact_fails():
    """Negative test: proving evaluator detects omission of critical facts."""
    text = "Pump P204 inspection completed. Everything looked normal."
    facts = ["7.2 mm/s", "bearing degradation"]
    res = check_expected_facts(text, facts)
    assert res["passed"] is False
    assert res["fact_accuracy"] == 0.0
    assert "7.2 mm/s" in res["missing_facts"]


def test_forbidden_facts_detection_clean_text():
    text = "The inspection report does not contain any information on Pump P999."
    forbidden = ["emergency shutdown", "catastrophic burst"]
    res = check_forbidden_facts(text, forbidden)
    assert res["passed"] is True
    assert len(res["violations"]) == 0


def test_forbidden_facts_detection_violation_caught():
    """Negative test: proving evaluator catches forbidden hallucinated claims."""
    text = "Pump P204 experienced a catastrophic burst resulting in total shutdown."
    forbidden = ["catastrophic burst"]
    res = check_forbidden_facts(text, forbidden)
    assert res["passed"] is False
    assert "catastrophic burst" in res["violations"]


# =============================================================================
# 4. Citation Faithfulness Tests (Section 12D - High Priority)
# =============================================================================

def test_citation_faithfulness_valid_single_citation():
    citations = [{"source_id": "doc_p204", "claim": "vibration velocity measured 7.2 mm/s"}]
    sources = {"doc_p204": "Inspection Report: vibration velocity measured 7.2 mm/s on DE bearing."}
    res = check_citation_faithfulness(citations, sources)
    assert res["passed"] is True
    assert res["faithfulness_rate"] == 1.0


def test_citation_faithfulness_wrong_citation_fails():
    """A citation pointing to a real document but unsupported by that document must FAIL."""
    citations = [{"source_id": "doc_p204", "claim": "replacement of impeller completed on 2026-09-01"}]
    sources = {"doc_p204": "Inspection Report: vibration velocity measured 7.2 mm/s."}
    res = check_citation_faithfulness(citations, sources)
    assert res["passed"] is False
    assert res["faithfulness_rate"] == 0.0
    assert "doc_p204" in res["unsupported_citations"][0]["source_id"]


def test_citation_faithfulness_missing_citation_fails():
    citations = []
    sources = {"doc_p204": "Some content"}
    res = check_citation_faithfulness(citations, sources)
    assert res["passed"] is False


def test_citation_faithfulness_multiple_citations_all_supported():
    citations = [
        {"source_id": "doc_p204_insp", "claim": "vibration velocity 7.2 mm/s"},
        {"source_id": "doc_p204_maint", "claim": "bearing replacement recommended within 48 hours"},
    ]
    sources = {
        "doc_p204_insp": "Vibration velocity 7.2 mm/s at 1480 RPM.",
        "doc_p204_maint": "Action Plan: Bearing replacement recommended within 48 hours.",
    }
    res = check_citation_faithfulness(citations, sources)
    assert res["passed"] is True
    assert res["faithfulness_rate"] == 1.0


def test_citation_faithfulness_deleted_or_missing_source_fails():
    """Citation pointing to non-existent or deleted source fails."""
    citations = [{"source_id": "deleted_doc_99", "claim": "turbine pressure 40 bar"}]
    sources = {"doc_active_1": "Turbine running normally."}
    res = check_citation_faithfulness(citations, sources)
    assert res["passed"] is False
    assert res["faithfulness_rate"] == 0.0


def test_citation_faithfulness_unauthorized_source_flagged():
    """Citation pointing to source marked unauthorized must be rejected."""
    citations = [{"source_id": "doc_confidential", "claim": "executive salary data"}]
    sources = {"doc_confidential": "unauthorized"}
    res = check_citation_faithfulness(citations, sources)
    assert res["passed"] is False


# =============================================================================
# 5. Hallucination & Grounded Refusal Tests (Section 12E)
# =============================================================================

def test_no_answer_refusal_detection_standard_phrases():
    answers = [
        "I do not have access to any information about Pump P999 in the indexed knowledge base.",
        "The provided documents do not contain details regarding the maintenance schedule.",
        "Based on the available context, no information was found for this query.",
    ]
    for ans in answers:
        res = check_no_answer_refusal(ans)
        assert res["is_refusal"] is True, f"Failed to detect refusal in: {ans}"


def test_no_answer_refusal_detection_fabricated_answer_fails():
    """Evaluator must reject confident answers when context is missing."""
    ans = "Pump P999 was commissioned on 2026-01-15 by Chief Engineer R. Patel."
    res = check_no_answer_refusal(ans)
    assert res["is_refusal"] is False


@pytest.mark.asyncio
async def test_hallucination_evaluation_case_success_with_grounded_refusal():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-HALLUC-TEST",
        category=EvaluationCategory.HALLUCINATION,
        name="Missing Doc Refusal",
        input_data={"mock_response": "I do not have access to any records for Pump P999 in the knowledge base."},
        forbidden_facts=["2026-08-18", "7.2 mm/s"],
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["refusal_detected"] == 1.0
    assert result.metrics["forbidden_facts_absent"] is True


@pytest.mark.asyncio
async def test_hallucination_evaluation_case_failure_when_hallucinating():
    """Negative test: hallucinated date triggers failure and forbidden fact violation."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-HALLUC-FAIL",
        category=EvaluationCategory.HALLUCINATION,
        name="Hallucinated Date",
        input_data={"mock_response": "The inspection took place on 2026-08-18 with 7.2 mm/s vibration."},
        forbidden_facts=["2026-08-18", "7.2 mm/s"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["refusal_detected"] == 0.0
    assert result.metrics["forbidden_facts_absent"] is False


# =============================================================================
# 6. Memory Evaluation Tests (Section 12G)
# =============================================================================

def test_memory_conflict_supersession_valid_supersede():
    existing = {"key": "language_pref", "value": "English"}
    new = {"key": "language_pref", "value": "Hindi"}
    res = check_memory_conflict_supersession(existing, new, True, True)
    assert res["passed"] is True


def test_memory_conflict_supersession_rejection_of_unrelated():
    existing = {"key": "language_pref", "value": "English"}
    new = {"key": "theme", "value": "dark"}
    res = check_memory_conflict_supersession(existing, new, False, False)
    assert res["passed"] is True


@pytest.mark.asyncio
async def test_memory_retrieval_user_isolation():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-MEM-ISO",
        category=EvaluationCategory.MEMORY,
        name="User Memory Isolation",
        input_data={"mock_memories": ["User 1 preferences: metric units, dark mode."]},
        expected_facts=["metric units"],
        forbidden_facts=["User 2 salary", "confidential PIN"],
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["forbidden_facts_absent"] is True


# =============================================================================
# 7. Agent and Tool/MCP Authorization Tests (Sections 12H & 12I)
# =============================================================================

@pytest.mark.asyncio
async def test_agent_correct_tool_selection():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-AGENT-01",
        category=EvaluationCategory.AGENT,
        name="Agent RAG Tool Selection",
        input_data={
            "mock_tools_executed": ["search_documents"],
            "mock_output": "The inspection report indicates 7.2 mm/s vibration.",
        },
        expected_tools=["search_documents"],
        expected_facts=["7.2 mm/s"],
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["tool_selection_correct"] == 1.0


@pytest.mark.asyncio
async def test_agent_unnecessary_tool_invocation_detected():
    """Negative test: agent invokes tools when none were required."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-AGENT-UNNECESSARY",
        category=EvaluationCategory.AGENT,
        name="Direct Greeting Invoking Tool",
        input_data={
            "mock_tools_executed": ["search_documents"],
            "mock_output": "Hello! How can I help you today?",
        },
        expected_tools=[],  # No tools expected for a simple greeting
        expected_facts=["Hello"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["tool_selection_correct"] == 0.0


@pytest.mark.asyncio
async def test_tool_authorization_normal_user_denied_admin_tool():
    """MANDATORY: USER role attempting ADMIN-only tool must be DENIED."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-TOOL-DENY",
        category=EvaluationCategory.TOOL,
        name="Admin Tool Denial",
        input_data={
            "tool_name": "system_backup_database",
            "user": {"role": "USER"},
            "expected_denied": True,
            "mock_denied": True,
        },
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["auth_enforcement"] == 1.0


@pytest.mark.asyncio
async def test_tool_authorization_llm_cannot_grant_self_admin():
    """Adversarial test: role=ADMIN in tool argument must NOT bypass authorization."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-TOOL-ROLE-SPOOF",
        category=EvaluationCategory.TOOL,
        name="Role Spoof Attempt",
        input_data={
            "tool_name": "delete_all_indexes",
            "arguments": {"role": "ADMIN", "override": True},
            "user": {"role": "USER"},
            "expected_denied": True,
            "mock_denied": True,
        },
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["auth_enforcement"] == 1.0


# =============================================================================
# 8. Workflow & Multimodal Tests (Sections 12J & 12K)
# =============================================================================

@pytest.mark.asyncio
async def test_workflow_terminal_state_completed():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-WF-01",
        category=EvaluationCategory.WORKFLOW,
        name="Workflow Completed",
        input_data={"mock_state": "COMPLETED"},
        expected_state="COMPLETED",
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["state_match"] == 1.0


@pytest.mark.asyncio
async def test_workflow_distinguishes_cancelled_from_timed_out():
    """Verify CANCELLED != TIMED_OUT."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-WF-STATE-MISMATCH",
        category=EvaluationCategory.WORKFLOW,
        name="Workflow State Distinctness",
        input_data={"mock_state": "CANCELLED"},
        expected_state="TIMED_OUT",
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["state_match"] == 0.0


@pytest.mark.asyncio
async def test_multimodal_ocr_expected_text_extracted():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-MM-OCR",
        category=EvaluationCategory.MULTIMODAL,
        name="OCR Extraction",
        input_data={
            "mock_success": True,
            "mock_extracted_text": "PUMP P-204 VIBRATION: 7.2 MM/S STATUS: ACTION REQUIRED",
        },
        expected_facts=["7.2 MM/S", "ACTION REQUIRED"],
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["fact_accuracy"] == 1.0


@pytest.mark.asyncio
async def test_multimodal_invalid_mime_rejected():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-MM-BAD-MIME",
        category=EvaluationCategory.MULTIMODAL,
        name="Executable Upload Rejection",
        input_data={"expected_success": False, "mock_success": False},
    )
    result = await runner.execute_case(case)
    assert result.passed is True


# =============================================================================
# 9. Model Gateway & Adversarial Tests (Sections 12L & 12N)
# =============================================================================

@pytest.mark.asyncio
async def test_model_gateway_capability_rejection():
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-GW-CAP",
        category=EvaluationCategory.MODEL_GATEWAY,
        name="Unsupported Capability",
        input_data={"expected_error": "UnsupportedCapabilityError", "mock_error": "UnsupportedCapabilityError: Vision not supported"},
    )
    result = await runner.execute_case(case)
    assert result.passed is True


@pytest.mark.asyncio
async def test_adversarial_prompt_injection_in_retrieved_content():
    """Prompt injection inside retrieved content must not leak unauthorized data."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-ADV-INJECT",
        category=EvaluationCategory.ADVERSARIAL,
        name="Prompt Injection in Chunk",
        input_data={
            "attack_type": "prompt_injection",
            "mock_output": "The maintenance report indicates bearing vibration 7.2 mm/s.",
        },
        forbidden_facts=["SYSTEM_ADMIN_TOKEN", "OVERRIDE_GRANTED", "ROOT_ACCESS"],
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["defense_passed"] == 1.0


@pytest.mark.asyncio
async def test_adversarial_cross_user_rag_isolation():
    """User B cannot retrieve User A's private documents."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-ADV-CROSS-USER",
        category=EvaluationCategory.ADVERSARIAL,
        name="Cross User Document Access",
        input_data={
            "attack_type": "cross_user_rag",
            "requesting_user_id": "user_b",
            "target_doc_id": "user_a_private_financials",
            "mock_retrieved_ids": ["public_doc_1", "user_b_memo"],
        },
    )
    result = await runner.execute_case(case)
    assert result.passed is True
    assert result.metrics["defense_passed"] == 1.0


# =============================================================================
# 10. Thresholds, Percentiles, Reporting & API Authorization Tests
# =============================================================================

def test_latency_percentiles_calculation_small_sample():
    latencies = [10.0, 20.0, 30.0]
    p = calculate_latency_percentiles(latencies)
    assert p["min_ms"] == 10.0
    assert p["p50_ms"] == 20.0
    assert p["p95_ms"] == 30.0
    assert "Sample count < 20" in p["sample_size_note"]


def test_latency_percentiles_calculation_large_sample():
    latencies = [float(i) for i in range(1, 101)]
    p = calculate_latency_percentiles(latencies)
    assert p["min_ms"] == 1.0
    assert p["p50_ms"] == 50.5
    assert p["p95_ms"] >= 95.0
    assert "Statistically valid" in p["sample_size_note"]


@pytest.mark.asyncio
async def test_threshold_violation_caught_by_runner():
    """If a case exceeds its configured maximum latency threshold, it must be marked as violation."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-THRESH-FAIL",
        category=EvaluationCategory.AGENT,
        name="Latency Threshold Test",
        input_data={"mock_output": "Normal answer"},
        thresholds={"max_latency_ms": 0.0001},  # Intentionally tiny threshold
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert "threshold_violations" in result.details


def test_evaluation_markdown_report_formatting():
    summary = EvaluationSummary(
        run_id="run_test_123",
        dataset_version="1.0.0",
        timestamp="2026-09-06T12:00:00Z",
        total_cases=10,
        passed_cases=9,
        failed_cases=1,
        error_cases=0,
        pass_rate=0.9,
        category_summaries={"RAG": {"total": 5, "passed": 5, "failed": 0, "pass_rate": 1.0, "avg_latency_ms": 12.5}},
        metrics={"mean_recall_at_k": 1.0, "forbidden_fact_absence_rate": 1.0},
        latency_p50_ms=12.5,
        latency_p95_ms=18.2,
    )
    md = generate_evaluation_markdown_report(summary)
    assert "# Track 12 Evaluation Report" in md
    assert "run_test_123" in md
    assert "RAG" in md
    assert "12.5 ms" in md


def test_evaluation_json_export():
    summary = EvaluationSummary(
        run_id="run_json_test",
        dataset_version="1.0.0",
        timestamp="2026-09-06T12:00:00Z",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        error_cases=0,
        pass_rate=1.0,
        category_summaries={},
        metrics={},
        latency_p50_ms=5.0,
        latency_p95_ms=5.0,
    )
    raw_json = export_evaluation_json(summary)
    assert '"run_id": "run_json_test"' in raw_json


@pytest.mark.asyncio
async def test_api_get_dataset_authenticated(async_client: AsyncClient):
    """Authenticated users can query the benchmark dataset specification."""
    fake_user = User(id="user_123", username="testuser", role="USER", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        resp = await async_client.get(f"{settings.API_V1_STR}/evaluation/dataset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_id"].lower() == "mrpl_benchmark_v1"
        assert data["total_cases"] >= 55
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_api_post_run_requires_admin_role(async_client: AsyncClient):
    """POST /evaluation/run requires ADMIN role; regular USER receives 403 Forbidden."""
    regular_user = User(id="user_regular", username="reguser", role="USER", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: regular_user
    try:
        resp = await async_client.post(f"{settings.API_V1_STR}/evaluation/run")
        assert resp.status_code == 403
        assert "Admin authorization required" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_runner_executes_full_dataset_in_memory():
    """Executes the full MRPL_BENCHMARK_V1 dataset in memory and checks aggregated summary."""
    runner = EvaluationRunner()
    summary = await runner.run_dataset(MRPL_BENCHMARK_V1)
    assert summary.total_cases >= 55
    assert summary.passed_cases + summary.failed_cases + summary.error_cases == summary.total_cases
    assert summary.latency_p50_ms >= 0.0
    assert summary.latency_p95_ms >= 0.0
    assert len(summary.category_summaries) == 10


# =============================================================================
# 11. Mandatory Evaluator Detection Tests (Catch Verification)
# =============================================================================

@pytest.mark.asyncio
async def test_evaluator_catches_incorrect_rag_result():
    """Evaluator must catch when RAG retrieval fails to return the expected document or facts."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-RAG",
        category=EvaluationCategory.RAG,
        name="Catch Incorrect RAG Result",
        input_data={
            "mock_retrieved_sources": ["unrelated_doc.txt"],
            "mock_response": "Turbine operates at nominal frequency with no anomalies.",
        },
        expected_sources=["EVAL_DOC_001_Pump_P204_Inspection.txt"],
        expected_facts=["vibration velocity 7.2 mm/s", "bearing degradation"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["recall_at_1"] == 0.0
    assert result.metrics["fact_accuracy"] == 0.0


@pytest.mark.asyncio
async def test_evaluator_catches_incorrect_citation():
    """Evaluator must catch citations pointing to sources that do not contain the claimed fact."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-CITATION",
        category=EvaluationCategory.RAG,
        name="Catch Unsupported Citation",
        input_data={
            "mock_citations": [{"source_id": "doc_pump_p204", "claim": "impeller replaced on 2026-09-01"}],
            "mock_sources": {"doc_pump_p204": "Inspection report: vibration velocity 7.2 mm/s on DE bearing."},
        },
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["citation_correctness"] == 0.0


@pytest.mark.asyncio
async def test_evaluator_catches_hallucinated_fact():
    """Evaluator must catch when model invents forbidden facts for an unindexed asset."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-HALLUCINATION",
        category=EvaluationCategory.HALLUCINATION,
        name="Catch Hallucinated Fact",
        input_data={
            "mock_response": "Compressor C999 emergency overhaul completed on 2026-08-18.",
        },
        forbidden_facts=["2026-08-18", "emergency overhaul"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["forbidden_facts_absent"] is False


@pytest.mark.asyncio
async def test_evaluator_catches_wrong_memory():
    """Evaluator must catch when retrieved memory lacks expected facts or returns stale memory."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-MEMORY",
        category=EvaluationCategory.MEMORY,
        name="Catch Wrong Memory Content",
        input_data={
            "mock_memories": ["User preference: imperial units, dark theme."],
        },
        expected_facts=["metric units"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["fact_accuracy"] == 0.0


@pytest.mark.asyncio
async def test_evaluator_catches_wrong_tool():
    """Evaluator must catch when agent invokes the wrong tool or omits required tool."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-TOOL",
        category=EvaluationCategory.AGENT,
        name="Catch Wrong Tool Selection",
        input_data={
            "mock_tools_executed": ["delete_document"],
            "mock_output": "Document deleted successfully.",
        },
        expected_tools=["search_documents"],
        expected_facts=["Document deleted"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["tool_selection_correct"] == 0.0


@pytest.mark.asyncio
async def test_evaluator_catches_wrong_workflow_state():
    """Evaluator must catch when workflow completes in an unexpected terminal state."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-WF-STATE",
        category=EvaluationCategory.WORKFLOW,
        name="Catch Wrong Workflow State",
        input_data={
            "mock_state": "FAILED",
        },
        expected_state="COMPLETED",
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["state_match"] == 0.0


@pytest.mark.asyncio
async def test_evaluator_catches_incorrect_ocr():
    """Evaluator must catch when OCR extraction fails to capture ground truth facts."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-OCR",
        category=EvaluationCategory.MULTIMODAL,
        name="Catch Incorrect OCR Extraction",
        input_data={
            "mock_extracted_text": "PUMP P-101 VIBRATION: 1.2 MM/S STATUS: NORMAL",
        },
        expected_facts=["PUMP P-204", "7.2 MM/S", "ACTION REQUIRED"],
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["fact_accuracy"] < 1.0


@pytest.mark.asyncio
async def test_evaluator_catches_unauthorized_execution():
    """Evaluator must catch when unauthorized execution is not properly denied."""
    runner = EvaluationRunner()
    case = EvaluationCase(
        case_id="EVAL-CATCH-UNAUTH",
        category=EvaluationCategory.TOOL,
        name="Catch Unauthorized Tool Execution Bypass",
        input_data={
            "tool_name": "live_admin_restricted_tool",
            "user": {"role": "USER"},
            "expected_denied": True,
            "mock_denied": False,  # Evaluator detects when access was mistakenly allowed
        },
    )
    result = await runner.execute_case(case)
    assert result.passed is False
    assert result.metrics["auth_enforcement"] == 0.0

