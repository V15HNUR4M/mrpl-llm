import pytest
import pytest_asyncio
import asyncio
from app.core.agent.registry import AgentRegistry, AgentDefinition
from app.core.context_engine.engine import ContextEngine
from app.core.model_gateway.gateway import ModelGateway
from app.core.model_gateway.schemas import GenerationRequest, GenerationResponse, Usage
from app.core.model_gateway.provider import ModelProvider
from app.core.runtime.tool_executor import FakeToolExecutor
from app.core.runtime.harness import AgentHarness
from app.core.runtime.schemas import RuntimeSession, ExecutionState
from app.core.runtime.errors import IterationLimitExceeded, ExecutionTimeout

class MockModelProvider(ModelProvider):
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        from app.core.model_gateway.schemas import ToolCall
        if self.call_count < len(self.responses):
            val = self.responses[self.call_count]
        else:
            val = "Final answer out of bounds"
        self.call_count += 1
        
        if isinstance(val, dict):
            # It's a tool call dict
            tc = ToolCall(id="mock-id", function=val)
            return GenerationResponse(text="", model=request.model, tool_calls=[tc], usage=Usage())
        else:
            return GenerationResponse(text=val, model=request.model, usage=Usage())

    async def stream(self, request): pass
    async def health(self): return True
    async def get_model_info(self, model_id): pass
    async def list_models(self): pass

@pytest.fixture
def base_setup():
    registry = AgentRegistry()
    agent = AgentDefinition(
        agent_id="test_agent", name="Test", description="Test", version="1.0",
        instructions="System Prompt",
    )
    agent.execution_limits.max_steps = 3
    agent.execution_limits.timeout_seconds = 2
    registry.register(agent)
    
    context_engine = ContextEngine()
    tool_executor = FakeToolExecutor()
    return registry, context_engine, tool_executor

@pytest.mark.asyncio
async def test_harness_happy_path(base_setup):
    registry, context_engine, tool_executor = base_setup
    
    gateway = ModelGateway()
    mock_provider = MockModelProvider(["This is the final answer."])
    gateway.register_provider("mock", mock_provider)
    gateway.register_model_route("qwen2.5:latest", "mock")
    
    harness = AgentHarness(registry, context_engine, gateway, tool_executor)
    session = RuntimeSession(session_id="1", conversation_id="1", agent_id="test_agent", agent_version="1.0", user_id="1")
    
    decision = await harness.execute(session, "Hello")
    assert decision.final_answer == "This is the final answer."
    assert session.state == ExecutionState.COMPLETED
    assert session.iteration_count == 1

@pytest.mark.asyncio
async def test_harness_tool_call(base_setup):
    registry, context_engine, tool_executor = base_setup
    
    gateway = ModelGateway()
    # 1st call asks for a tool, 2nd call gives final answer
    mock_provider = MockModelProvider([
        {"name": "search_documents", "arguments": {"query": "test"}},
        'Here is what I found.'
    ])
    gateway.register_provider("mock", mock_provider)
    gateway.register_model_route("qwen2.5:latest", "mock")
    
    harness = AgentHarness(registry, context_engine, gateway, tool_executor)
    session = RuntimeSession(session_id="2", conversation_id="1", agent_id="test_agent", agent_version="1.0", user_id="1")
    
    decision = await harness.execute(session, "Search for test")
    assert decision.final_answer == "Here is what I found."
    assert session.state == ExecutionState.COMPLETED
    assert session.iteration_count == 2
    assert session.tool_call_count == 1

@pytest.mark.asyncio
async def test_harness_iteration_limit(base_setup):
    registry, context_engine, tool_executor = base_setup
    
    gateway = ModelGateway()
    # Always asks for a tool to force iteration limit
    mock_provider = MockModelProvider([
        {"name": "search_documents", "arguments": {"query": "test"}},
        {"name": "search_documents", "arguments": {"query": "test"}},
        {"name": "search_documents", "arguments": {"query": "test"}},
        {"name": "search_documents", "arguments": {"query": "test"}}
    ])
    gateway.register_provider("mock", mock_provider)
    gateway.register_model_route("qwen2.5:latest", "mock")
    
    harness = AgentHarness(registry, context_engine, gateway, tool_executor)
    session = RuntimeSession(session_id="3", conversation_id="1", agent_id="test_agent", agent_version="1.0", user_id="1")
    
    with pytest.raises(IterationLimitExceeded):
        await harness.execute(session, "Do it")
    
    assert session.state == ExecutionState.LIMIT_REACHED

@pytest.mark.asyncio
async def test_harness_timeout(base_setup):
    registry, context_engine, tool_executor = base_setup
    
    class SlowProvider(ModelProvider):
        async def generate(self, request):
            await asyncio.sleep(3)
            return GenerationResponse(text="Late", model="test")
        async def stream(self, request): pass
        async def health(self): return True
        async def get_model_info(self, model_id): pass
        async def list_models(self): pass

    gateway = ModelGateway()
    gateway.register_provider("slow", SlowProvider())
    gateway.register_model_route("qwen2.5:latest", "slow")
    
    harness = AgentHarness(registry, context_engine, gateway, tool_executor)
    session = RuntimeSession(session_id="4", conversation_id="1", agent_id="test_agent", agent_version="1.0", user_id="1")
    
    with pytest.raises(ExecutionTimeout):
        await harness.execute(session, "Do it")
        
    assert session.state == ExecutionState.TIMED_OUT
