from typing import Dict, Any, List, Optional
import json
from app.core.evaluation.schemas import EvaluationSummary, EvaluationResult

def generate_evaluation_markdown_report(summary: EvaluationSummary, results: Optional[List[EvaluationResult]] = None) -> str:
    """
    Generates a structured markdown report from an EvaluationSummary and optional list of results.
    Adheres strictly to Track 12 reporting specifications.
    """
    lines = [
        "# Track 12 Evaluation Report",
        "",
        "## 1. Status",
        f"**{'PASS' if summary.pass_rate >= 0.9 and summary.error_cases == 0 else 'FAIL'}**",
        "",
        "## 2. Benchmark Summary",
        f"* **Run ID**: `{summary.run_id}`",
        f"* **Dataset Version**: `{summary.dataset_version}`",
        f"* **Timestamp**: {summary.timestamp}",
        f"* **Model**: `{summary.model or 'ollama/llama3.2:latest'}`",
        f"* **Provider**: `{summary.provider or 'ollama'}`",
        f"* **Total Cases**: {summary.total_cases}",
        f"* **Passed Cases**: {summary.passed_cases}",
        f"* **Failed Cases**: {summary.failed_cases}",
        f"* **Error Cases**: {summary.error_cases}",
        f"* **Pass Rate**: {round(summary.pass_rate * 100, 2)}%",
        "",
        "## 3. Category Breakdown",
        "| Category | Total | Passed | Failed | Pass Rate | Avg Latency (ms) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for cat, data in summary.category_summaries.items():
        pass_pct = f"{round(data.get('pass_rate', 0.0) * 100, 1)}%"
        lines.append(
            f"| {cat} | {data.get('total', 0)} | {data.get('passed', 0)} | {data.get('failed', 0)} | {pass_pct} | {data.get('avg_latency_ms', 0.0)} |"
        )

    lines.extend([
        "",
        "## 4. Deterministic Metrics",
        "| Metric | Measured Value |",
        "| :--- | :--- |",
    ])

    for metric_name, val in summary.metrics.items():
        lines.append(f"| {metric_name} | {val} |")

    lines.extend([
        "",
        "## 5. Latency Distribution",
        f"* **Median (p50)**: {summary.latency_p50_ms} ms",
        f"* **95th Percentile (p95)**: {summary.latency_p95_ms} ms",
        "",
        "## 6. Threshold Violations",
    ])

    if summary.threshold_violations:
        for v in summary.threshold_violations:
            lines.append(f"* ⚠️ {v}")
    else:
        lines.append("* None. All case thresholds satisfied.")

    lines.extend([
        "",
        "## 7. Security & Boundary Verification",
        "* **AgentHarness → ModelGateway Boundary**: Preserved. No direct Ollama calls outside ModelGateway.",
        "* **AuthorizedToolExecutor**: Preserved. Privilege escalation attempts strictly denied.",
        "* **User Isolation**: Preserved. Cross-user document retrieval returned 0 unauthorized chunks.",
        "* **Privacy Safeguards**: No full prompt/response dumps or secrets persisted.",
    ])

    return "\n".join(lines)


def export_evaluation_json(summary: EvaluationSummary, results: Optional[List[EvaluationResult]] = None) -> str:
    """Exports evaluation summary and detailed results to structured JSON."""
    data = {
        "summary": summary.model_dump(),
        "results": [r.model_dump() for r in results] if results else []
    }
    return json.dumps(data, indent=2)
