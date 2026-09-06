import asyncio
import os
import json
from app.core.evaluation.dataset import MRPL_BENCHMARK_V1
from app.core.evaluation.runner import EvaluationRunner

async def main():
    runner = EvaluationRunner()
    summary = await runner.run_dataset(MRPL_BENCHMARK_V1)
    print(f"Total cases: {summary.total_cases}")
    print(f"Passed: {summary.passed_cases}")
    print(f"Failed: {summary.failed_cases}")
    print(f"Pass rate: {summary.pass_rate}")
    
    results = EvaluationRunner.get_latest_results()
    failures = [r for r in results if not r.passed]
    print(f"\n--- FAILURES ({len(failures)}) ---")
    for f in failures:
        print(f"\nCase ID: {f.case_id} [{f.category.value}]")
        print(f"  Metrics: {f.metrics}")
        print(f"  Error: {f.error}")
        print(f"  Details: {f.details}")

if __name__ == "__main__":
    asyncio.run(main())
