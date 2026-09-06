from typing import List, Optional
from app.db.uow import UnitOfWork
from app.core.workflow.schemas import WorkflowSpec
from app.core.agent.registry import AgentRegistry
from app.core.runtime.tool_executor import ToolRegistry

class WorkflowRegistry:
    """
    Registry for managing workflow definitions and versions.
    Validates workflows before persistence.
    """
    def __init__(self, uow: UnitOfWork, agent_registry: AgentRegistry, tool_registry: ToolRegistry):
        self.uow = uow
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry

    def validate_workflow(self, spec: WorkflowSpec):
        if spec.start_step not in spec.steps:
            raise ValueError(f"Start step '{spec.start_step}' is not defined in steps.")

        for step_id, step in spec.steps.items():
            if step.next_step and step.next_step not in spec.steps:
                raise ValueError(f"Step '{step_id}' references unknown next_step '{step.next_step}'.")
            if step.fallback_step and step.fallback_step not in spec.steps:
                raise ValueError(f"Step '{step_id}' references unknown fallback_step '{step.fallback_step}'.")

            if step.type == "AGENT":
                agent_id = step.configuration.get("agent_id")
                if not agent_id:
                    raise ValueError(f"AGENT step '{step_id}' must configure 'agent_id'.")
                if not self.agent_registry.get(agent_id):
                    raise ValueError(f"AGENT step '{step_id}' references unknown agent '{agent_id}'.")

            elif step.type == "TOOL":
                tool_name = step.configuration.get("tool")
                if not tool_name:
                    raise ValueError(f"TOOL step '{step_id}' must configure 'tool'.")
                if not self.tool_registry.get(tool_name):
                    raise ValueError(f"TOOL step '{step_id}' references unknown tool '{tool_name}'.")

            elif step.type == "CONDITION":
                if "left" not in step.configuration or "operator" not in step.configuration or "right" not in step.configuration:
                    raise ValueError(f"CONDITION step '{step_id}' missing 'left', 'operator', or 'right'.")
                allowed_ops = {"equals", "not_equals", "exists", "not_exists", "contains"}
                if step.configuration["operator"] not in allowed_ops:
                    raise ValueError(f"CONDITION step '{step_id}' has invalid operator '{step.configuration['operator']}'.")

    async def register_workflow(self, name: str, owner_id: str, version: str, spec: WorkflowSpec, description: str = "") -> str:
        self.validate_workflow(spec)
        
        async with self.uow as uow:
            workflow = await uow.workflows.create({
                "name": name,
                "owner_id": owner_id,
                "description": description
            })
            
            await uow.workflow_versions.create({
                "workflow_id": workflow.id,
                "version": version,
                "definition": spec.model_dump(),
                "input_schema": spec.input_schema
            })
            return workflow.id

    async def add_version(self, workflow_id: str, version: str, spec: WorkflowSpec) -> str:
        self.validate_workflow(spec)
        
        async with self.uow as uow:
            version_record = await uow.workflow_versions.create({
                "workflow_id": workflow_id,
                "version": version,
                "definition": spec.model_dump(),
                "input_schema": spec.input_schema
            })
            return version_record.id

    async def get_workflow_version(self, workflow_id: str, version: str):
        async with self.uow as uow:
            return await uow.workflow_versions.get_by_workflow_and_version(workflow_id, version)

    async def list_for_user(self, user_id: str):
        async with self.uow as uow:
            return await uow.workflows.list_for_owner(user_id)
