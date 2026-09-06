from typing import Dict, List, Optional
from app.core.agent.schemas import AgentDefinition

class AgentNotFoundError(Exception):
    pass

class AgentDisabledError(Exception):
    pass

class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> AgentDefinition:
        agent = self._agents.get(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found.")
        return agent

    def list_all(self) -> List[AgentDefinition]:
        return list(self._agents.values())

    def remove(self, agent_id: str) -> None:
        if agent_id in self._agents:
            del self._agents[agent_id]
