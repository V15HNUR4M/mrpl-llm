import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user
from app.db.uow import UnitOfWork, get_uow
from app.db.models import User
from app.core.workflow.schemas import WorkflowSpec, WorkflowRunState
from app.core.workflow.registry import WorkflowRegistry
from app.core.workflow.engine import WorkflowEngine
from app.core.agent.registry import AgentRegistry
from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor
from app.core.runtime.harness import AgentHarness
from app.core.context_engine.engine import ContextEngine
from app.core.model_gateway.gateway import ModelGateway

router = APIRouter()

# For the sake of this implementation, we assume these exist in dependency injection or global state
# In a real setup, these would be proper FastAPI dependencies.
def get_workflow_registry(uow: UnitOfWork = Depends(get_uow)):
    # Assuming global AgentRegistry and ToolRegistry exist
    agent_registry = AgentRegistry()
    tool_registry = ToolRegistry()
    return WorkflowRegistry(uow, agent_registry, tool_registry)

def get_workflow_engine(uow: UnitOfWork = Depends(get_uow)):
    # Dummy instances for engine dependencies
    agent_registry = AgentRegistry()
    tool_registry = ToolRegistry()
    local_exec = LocalToolExecutor(tool_registry)
    auth_exec = AuthorizedToolExecutor(local_exec, uow=uow)
    gateway = ModelGateway()
    ctx_engine = ContextEngine()
    harness = AgentHarness(agent_registry, ctx_engine, gateway, auth_exec)
    return WorkflowEngine(uow, harness, auth_exec)

@router.post("/", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_workflow(
    name: str,
    spec: WorkflowSpec,
    description: str = "",
    version: str = "v1",
    current_user: User = Depends(get_current_user),
    registry: WorkflowRegistry = Depends(get_workflow_registry)
):
    try:
        workflow_id = await registry.register_workflow(
            name=name,
            owner_id=current_user.id,
            version=version,
            spec=spec,
            description=description
        )
        return {"id": workflow_id, "status": "created"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[Dict[str, Any]])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    registry: WorkflowRegistry = Depends(get_workflow_registry)
):
    workflows = await registry.list_for_user(current_user.id)
    return [{"id": w.id, "name": w.name, "description": w.description} for w in workflows]

@router.get("/{workflow_id}", response_model=Dict[str, Any])
async def get_workflow(
    workflow_id: str,
    version: str = "v1",
    current_user: User = Depends(get_current_user),
    registry: WorkflowRegistry = Depends(get_workflow_registry)
):
    # Enforce ownership check
    async with registry.uow as uow:
        workflow = await uow.workflows.get_by_id(workflow_id)
        if not workflow or workflow.owner_id != current_user.id:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        wv = await uow.workflow_versions.get_by_workflow_and_version(workflow_id, version)
        if not wv:
            raise HTTPException(status_code=404, detail="Version not found")
            
        return {
            "id": workflow.id,
            "name": workflow.name,
            "version": wv.version,
            "definition": wv.definition
        }

@router.post("/{workflow_id}/run", response_model=Dict[str, Any])
async def run_workflow(
    workflow_id: str,
    inputs: Dict[str, Any],
    background_tasks: BackgroundTasks,
    version: str = "v1",
    current_user: User = Depends(get_current_user),
    registry: WorkflowRegistry = Depends(get_workflow_registry),
    engine: WorkflowEngine = Depends(get_workflow_engine)
):
    async with registry.uow as uow:
        workflow = await uow.workflows.get_by_id(workflow_id)
        if not workflow or workflow.owner_id != current_user.id:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        wv = await uow.workflow_versions.get_by_workflow_and_version(workflow_id, version)
        if not wv or not wv.enabled:
            raise HTTPException(status_code=400, detail="Version not found or disabled")
            
        # Create Run
        run = await uow.workflow_runs.create({
            "workflow_version_id": wv.id,
            "user_id": current_user.id,
            "state": WorkflowRunState.PENDING.value,
            "context_data": {"inputs": inputs, "step_results": {}}
        })
        run_id = run.id
        await uow.commit()

    # Define background execution task
    async def _execute_task():
        # Load spec
        spec = WorkflowSpec(**wv.definition)
        final_state, final_context = await engine.execute(
            run_id=run_id,
            workflow_version_id=wv.id,
            user_id=current_user.id,
            spec=spec,
            inputs=inputs
        )
        
        # Update run in DB
        async with engine.uow as uow:
            run_db = await uow.workflow_runs.get_by_id(run_id)
            if run_db:
                run_db.state = final_state.value
                run_db.context_data = final_context.model_dump()
                import datetime
                run_db.completed_at = datetime.datetime.now(datetime.timezone.utc)
                await uow.commit()

    background_tasks.add_task(_execute_task)
    
    return {"run_id": run_id, "status": "PENDING"}

@router.get("/runs/{run_id}", response_model=Dict[str, Any])
async def get_workflow_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        run = await uow.workflow_runs.get_by_id(run_id)
        if not run or run.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Run not found")
            
        return {
            "run_id": run.id,
            "state": run.state,
            "current_step": run.current_step,
            "context": run.context_data
        }

@router.post("/runs/{run_id}/cancel", response_model=Dict[str, Any])
async def cancel_workflow_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow)
):
    async with uow:
        run = await uow.workflow_runs.get_by_id(run_id)
        if not run or run.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Run not found")
            
        if run.state in [WorkflowRunState.COMPLETED.value, WorkflowRunState.FAILED.value, WorkflowRunState.CANCELLED.value]:
            raise HTTPException(status_code=400, detail="Cannot cancel terminal run")
            
        run.state = WorkflowRunState.CANCELLED.value
        await uow.commit()
        return {"run_id": run.id, "status": "CANCELLED"}
