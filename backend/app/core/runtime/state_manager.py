import asyncio
from typing import Dict, Set, Optional


class AgentStateManager:
    """
    Tracks runtime agent execution states via request/correlation IDs.
    
    Status definitions:
    - disabled: Agent is explicitly marked disabled in configuration
    - running: Agent currently has one or more in-flight executions
    - error: Most recent execution failed (and not currently running)
    - ready: Most recent execution succeeded or idle (and not currently running)
    - unavailable: Missing model or system dependency
    """
    def __init__(self):
        self._active_executions: Dict[str, Set[str]] = {}  # agent_id -> set of correlation_ids
        self._last_execution_status: Dict[str, str] = {}   # agent_id -> "success" | "error"
        self._lock = asyncio.Lock()

    def start_execution(self, agent_id: str, correlation_id: str) -> None:
        if agent_id not in self._active_executions:
            self._active_executions[agent_id] = set()
        self._active_executions[agent_id].add(correlation_id)

    def complete_execution(self, agent_id: str, correlation_id: str, success: bool = True) -> None:
        if agent_id in self._active_executions:
            self._active_executions[agent_id].discard(correlation_id)
        # Update latest execution status
        self._last_execution_status[agent_id] = "success" if success else "error"

    def get_status(self, agent_id: str, is_enabled: bool = True, is_available: bool = True) -> str:
        if not is_enabled:
            return "disabled"
        if not is_available:
            return "unavailable"
        if self._active_executions.get(agent_id):
            return "running"
        if self._last_execution_status.get(agent_id) == "error":
            return "error"
        return "ready"

    def get_active_count(self, agent_id: str) -> int:
        return len(self._active_executions.get(agent_id, set()))

    def reset(self) -> None:
        self._active_executions.clear()
        self._last_execution_status.clear()


_global_state_manager: Optional[AgentStateManager] = None

def get_agent_state_manager() -> AgentStateManager:
    global _global_state_manager
    if _global_state_manager is None:
        _global_state_manager = AgentStateManager()
    return _global_state_manager
