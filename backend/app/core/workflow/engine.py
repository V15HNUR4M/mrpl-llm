import asyncio
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.workflow.schemas import WorkflowSpec, WorkflowContext, WorkflowRunState, StepType
from app.core.runtime.harness import AgentHarness
from app.core.runtime.tool_executor import AuthorizedToolExecutor
from app.core.runtime.schemas import ToolRequest, RuntimeSession
from app.db.uow import UnitOfWork

MAX_WORKFLOW_DURATION = 300 # seconds
MAX_STEPS = 50
MAX_RESULT_BYTES = 100 * 1024 # 100KB per step

class ConditionEvaluator:
    @staticmethod
    def _resolve_path(path: str, context: WorkflowContext) -> Any:
        parts = path.split('.')
        if not parts:
            return None
        
        root = parts[0]
        if root == "inputs":
            val = context.inputs
        else:
            val = context.step_results.get(root)
            
        for part in parts[1:]:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return None
        return val

    @staticmethod
    def evaluate(config: Dict[str, Any], context: WorkflowContext) -> bool:
        left_path = config.get("left")
        operator = config.get("operator")
        right_val = config.get("right")
        
        left_val = ConditionEvaluator._resolve_path(left_path, context) if left_path else None
        
        if operator == "equals":
            return left_val == right_val
        elif operator == "not_equals":
            return left_val != right_val
        elif operator == "exists":
            return left_val is not None
        elif operator == "not_exists":
            return left_val is None
        elif operator == "contains":
            if isinstance(left_val, (str, list, dict)) and right_val is not None:
                return right_val in left_val
            return False
        
        return False


class WorkflowEngine:
    def __init__(
        self, 
        uow: UnitOfWork, 
        agent_harness: AgentHarness, 
        tool_executor: AuthorizedToolExecutor,
        observability_service=None
    ):
        self.uow = uow
        self.agent_harness = agent_harness
        self.tool_executor = tool_executor
        self.observability_service = observability_service

    async def _emit_telemetry(self, event_type: str, user_id: str, status: str, run_id: str = None, duration_ms: int = None, error_type: str = None, metadata: dict = None):
        if not self.observability_service:
            return
        try:
            from app.core.observability.schemas import TelemetryEventCreate
            severity = "ERROR" if status in ("failed", "error", "timeout") else ("WARN" if status == "cancelled" else "INFO")
            meta = metadata or {}
            if run_id:
                meta["run_id"] = run_id
            event = TelemetryEventCreate(
                event_type=event_type,
                component="workflow",
                severity=severity,
                user_id=user_id or None,
                correlation_id=run_id,
                duration_ms=duration_ms,
                status=status,
                error_type=error_type,
                metadata=meta
            )
            await self.observability_service.emit_event(event)
        except Exception:
            pass

    async def _audit(self, user_id: str, action: str, resource_id: str, result: str, metadata: dict = None):
        async with self.uow as uow:
            try:
                await uow.audit.create({
                    "user_id": user_id,
                    "action": action,
                    "resource_type": "workflow",
                    "resource_id": resource_id,
                    "result": result,
                    "metadata_": metadata or {}
                })
                await uow.commit()
            except Exception:
                pass

    async def execute(self, run_id: str, workflow_version_id: str, user_id: str, spec: WorkflowSpec, inputs: Dict[str, Any]):
        context = WorkflowContext(inputs=inputs)
        current_step = spec.start_step
        
        # We simulate the WorkflowRun state here.
        # Ideally, we load/save from DB, but the engine runs it in memory and updates DB asynchronously.
        
        # Enforce input validation (placeholder for JSONSchema validation)
        import jsonschema
        if spec.input_schema:
            try:
                jsonschema.validate(instance=inputs, schema=spec.input_schema)
            except jsonschema.ValidationError as e:
                await self._audit(user_id, "workflow_failed", workflow_version_id, "failed", {"error": str(e)})
                raise ValueError(f"Invalid workflow inputs: {e.message}")

        import time
        t0 = time.time()
        await self._audit(user_id, "workflow_started", workflow_version_id, "started", {"run_id": run_id})
        await self._emit_telemetry("workflow.run.started", user_id, "started", run_id=run_id, metadata={"workflow_version_id": workflow_version_id})

        step_count = 0
        status = WorkflowRunState.RUNNING
        
        try:
            async with asyncio.timeout(MAX_WORKFLOW_DURATION):
                while current_step:
                    if step_count >= MAX_STEPS:
                        status = WorkflowRunState.FAILED
                        await self._audit(user_id, "workflow_failed", workflow_version_id, "failed", {"error": "MAX_STEPS exceeded"})
                        dur = int((time.time() - t0) * 1000)
                        await self._emit_telemetry("workflow.run.failed", user_id, "failed", run_id=run_id, duration_ms=dur, error_type="MaxStepsExceeded")
                        break
                        
                    step = spec.steps.get(current_step)
                    if not step:
                        status = WorkflowRunState.FAILED
                        await self._audit(user_id, "workflow_failed", workflow_version_id, "failed", {"error": f"Step {current_step} not found"})
                        dur = int((time.time() - t0) * 1000)
                        await self._emit_telemetry("workflow.run.failed", user_id, "failed", run_id=run_id, duration_ms=dur, error_type="StepNotFound")
                        break
                        
                    step_count += 1
                    
                    try:
                        if step.type == StepType.TOOL:
                            tool_req = ToolRequest(
                                tool=step.configuration["tool"],
                                arguments=step.configuration.get("arguments", {}), # In a real implementation we would resolve context paths here
                                call_id=str(uuid.uuid4())
                            )
                            # Execute via AuthorizedToolExecutor
                            # We pass the user_id via context to enforce tool authorization
                            res = await self.tool_executor.execute(tool_req, context={"user_id": user_id})
                            result_dict = res.model_dump()
                            
                        elif step.type == StepType.AGENT:
                            agent_id = step.configuration["agent_id"]
                            user_input = step.configuration.get("input", "")
                            # Provide session context
                            session = RuntimeSession(
                                session_id=str(uuid.uuid4()),
                                conversation_id=str(uuid.uuid4()),
                                agent_id=agent_id,
                                agent_version="latest",
                                user_id=user_id
                            )
                            decision = await self.agent_harness.execute(session, user_input)
                            result_dict = decision.model_dump()
                            
                        elif step.type == StepType.CONDITION:
                            is_true = ConditionEvaluator.evaluate(step.configuration, context)
                            result_dict = {"status": "success", "result": is_true}
                            
                    except Exception as e:
                        result_dict = {"status": "error", "error": str(e)}

                    # Enforce result size bound
                    result_json = json.dumps(result_dict)
                    if len(result_json.encode('utf-8')) > MAX_RESULT_BYTES:
                        result_dict = {"status": "error", "error": "Result exceeded maximum byte limit"}
                        
                    context.step_results[current_step] = result_dict
                    step_status = "error" if result_dict.get("status") == "error" else "success"
                    await self._emit_telemetry("workflow.step.completed", user_id, step_status, run_id=run_id, metadata={"step": current_step, "step_count": step_count})

                    # Route next step
                    if step.type == StepType.CONDITION:
                        is_true = result_dict.get("result", False)
                        current_step = step.next_step if is_true else step.fallback_step
                    else:
                        if result_dict.get("status") == "error":
                            current_step = step.fallback_step
                        else:
                            current_step = step.next_step

                if status == WorkflowRunState.RUNNING:
                    status = WorkflowRunState.COMPLETED
                    dur = int((time.time() - t0) * 1000)
                    await self._audit(user_id, "workflow_completed", workflow_version_id, "success", {"run_id": run_id})
                    await self._emit_telemetry("workflow.run.completed", user_id, "success", run_id=run_id, duration_ms=dur)

        except asyncio.TimeoutError:
            status = WorkflowRunState.TIMED_OUT
            dur = int((time.time() - t0) * 1000)
            await self._audit(user_id, "workflow_timed_out", workflow_version_id, "timeout", {"run_id": run_id})
            await self._emit_telemetry("workflow.run.timeout", user_id, "timed_out", run_id=run_id, duration_ms=dur, error_type="TimeoutError")
        except asyncio.CancelledError:
            status = WorkflowRunState.CANCELLED
            dur = int((time.time() - t0) * 1000)
            await self._audit(user_id, "workflow_cancelled", workflow_version_id, "cancelled", {"run_id": run_id})
            await self._emit_telemetry("workflow.run.cancelled", user_id, "cancelled", run_id=run_id, duration_ms=dur, error_type="CancelledError")
        except Exception as e:
            status = WorkflowRunState.FAILED
            dur = int((time.time() - t0) * 1000)
            await self._audit(user_id, "workflow_failed", workflow_version_id, "failed", {"run_id": run_id, "error": str(e)})
            await self._emit_telemetry("workflow.run.failed", user_id, "failed", run_id=run_id, duration_ms=dur, error_type=type(e).__name__)

        return status, context
