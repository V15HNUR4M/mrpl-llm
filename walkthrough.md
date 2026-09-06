# Track 12: Testing & Evaluation — Walkthrough & Verification

## Overview

Track 12 establishes a deterministic-first evaluation framework that empirically answers:
> *"Does the MRPL AI Workbench produce correct, grounded, secure and reproducible results?"*

The framework acts strictly as an **observer of actual system behavior**, upholding all boundaries of Tracks 1–11:
- `AgentHarness` → `Tool Registry` → `AuthorizationPolicy` → `AuthorizedToolExecutor` → `search_documents` → `ContextCandidate` → `ContextEngine` → `ModelGateway` → `Provider Adapter`
- No secondary runtime or architecture bypasses.
- Ground truth facts exist exclusively within evaluation benchmark fixtures, not hardcoded into production logic.

---

## 1. Components Delivered

### Core Evaluation Engine (`backend/app/core/evaluation/`)
- `schemas.py`: Pydantic V2 contracts for `EvaluationCategory`, `EvaluationCase`, `EvaluationDataset`, `EvaluationResult`, and `EvaluationSummary`.
- `metrics.py`: Deterministic metrics:
  - Retrieval: `calculate_recall_at_k`, `calculate_precision_at_k`, `calculate_mrr`.
  - Grounding & Faithfulness: `check_expected_facts`, `check_forbidden_facts`, `check_citation_faithfulness`.
  - Hallucination: `check_no_answer_refusal`.
  - Memory: `check_memory_conflict_supersession`.
  - Security & Tools: `check_tool_authorization_enforcement`.
- `dataset.py`: `MRPL_BENCHMARK_V1` benchmark suite with **66 concrete cases** across all 10 categories.
- `runner.py`: `EvaluationRunner` executing benchmark cases against live services, computing latencies, checking threshold violations, and aggregating summaries.
- `reporting.py`: Markdown and structured JSON exporters.

### Privileged Operations API (`backend/app/api/v1/endpoints/evaluation.py`)
- `GET /api/v1/evaluation/dataset`: Returns benchmark dataset overview. Authenticated.
- `GET /api/v1/evaluation/latest`: Retrieves most recent evaluation run summary. Authenticated.
- `POST /api/v1/evaluation/run`: Triggers benchmark run. **ADMIN RBAC strictly enforced** (USER receives 403 Forbidden).

### Frontend Evaluation Dashboard (`frontend/src/pages/Evaluation.tsx`)
- Lightweight dashboard displaying benchmark run ID, model/provider, pass rate, category breakdown, deterministic metrics, threshold violations, and p50/p95 latency.
- Accessible via sidebar navigation under `/evaluation`.
- Built and verified with 0 TypeScript/build errors.

---

## 2. Verification Results

### 1. Focused Tests (`backend/tests/test_track12_evaluation.py`)
- **Collected**: 46
- **Passed**: 46
- **Failed**: 0
- **Duration**: 30.70s

### 2. Full Backend Regression (`backend/tests/`)
- **Collected**: 420
- **Passed**: 420 (Tracks 1–11: 374 + Track 12: 46)
- **Failed**: 0
- **Duration**: 329.27s (0:05:29)

### 3. Frontend Tests (`frontend`)
- **Tests**: 24 passed (8 test files)
- **Duration**: 10.33s

### 4. Frontend Production Build
- **Status**: PASS (`tsc -b && vite build` completed in 1.51s with 0 errors)

### 5. Live Evaluation Benchmark (`scratch/test_live_evaluation.py`)
- **Result**: ALL 10 SCENARIOS PASSED
  1. RAG Factual Question: PASS (1033.16ms)
  2. RAG Cross-Document Question: PASS (1250.53ms)
  3. No-Answer Refusal: PASS (358.84ms)
  4. Citation Verification: PASS (0.03ms)
  5. Memory Retrieval: PASS (94.55ms)
  6. Authorized Tool Invocation: PASS (335.27ms)
  7. Unauthorized Tool Attempt (Admin Denied): PASS (0.04ms)
  8. Workflow Subsystem: PASS (33.48ms)
  9. Multimodal / Image Upload: PASS (73.51ms)
  10. Deleted / Stale Knowledge Scenario: PASS (872.02ms)
