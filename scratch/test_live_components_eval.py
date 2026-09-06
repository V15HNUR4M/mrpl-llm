import asyncio
import os
from app.main import app, lifespan
from app.core.evaluation.dataset import MRPL_BENCHMARK_V1
from app.core.evaluation.runner import EvaluationRunner

async def main():
    async with lifespan(app):
        runner = EvaluationRunner(
            rag_service=getattr(app.state, "rag_service", None),
            agent_harness=getattr(app.state, "agent_harness", None),
            tool_executor=getattr(app.state, "authorized_tool_executor", None),
            model_gateway=getattr(app.state, "model_gateway", None),
            workflow_engine=getattr(app.state, "workflow_engine", None),
            multimodal_service=getattr(app.state, "multimodal_service", None),
        )
        print("Running dataset with live app.state components...")
        summary = await runner.run_dataset(MRPL_BENCHMARK_V1)
        print(f"Total cases: {summary.total_cases}")
        print(f"Passed: {summary.passed_cases}")
        print(f"Failed: {summary.failed_cases}")
        print(f"Pass rate: {summary.pass_rate}")
        print(f"Metrics: {summary.metrics}")

        results = EvaluationRunner.get_latest_results()
        for r in results:
            if not r.passed:
                print(f"FAILED: {r.case_id} [{r.category.value}] - error: {r.error} - details: {r.details}")

if __name__ == "__main__":
    asyncio.run(main())
