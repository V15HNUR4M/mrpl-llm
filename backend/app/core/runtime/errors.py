class AgentExecutionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class IterationLimitExceeded(AgentExecutionError):
    def __init__(self, limit: int):
        super().__init__(f"Agent exceeded the maximum iteration limit of {limit}")

class ToolCallLimitExceeded(AgentExecutionError):
    def __init__(self, limit: int):
        super().__init__(f"Agent exceeded the maximum tool call limit of {limit}")

class ExecutionCancelled(AgentExecutionError):
    def __init__(self):
        super().__init__("Execution was cancelled by the user")

class ExecutionTimeout(AgentExecutionError):
    def __init__(self, seconds: int):
        super().__init__(f"Execution timed out after {seconds} seconds")
