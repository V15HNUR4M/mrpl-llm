import pytest
from app.core.agent.schemas import AgentDefinition
from app.core.agent.registry import AgentRegistry, AgentNotFoundError

def test_registry_register_and_get():
    registry = AgentRegistry()
    agent = AgentDefinition(
        agent_id="test_agent",
        name="Test",
        description="Test",
        version="1.0",
        instructions="do things"
    )
    registry.register(agent)
    
    fetched = registry.get("test_agent")
    assert fetched.agent_id == "test_agent"
    
def test_registry_get_unknown():
    registry = AgentRegistry()
    with pytest.raises(AgentNotFoundError):
        registry.get("nonexistent")
        
def test_registry_list_all():
    registry = AgentRegistry()
    registry.register(AgentDefinition(agent_id="test1", name="1", description="", version="", instructions=""))
    registry.register(AgentDefinition(agent_id="test2", name="2", description="", version="", instructions=""))
    
    agents = registry.list_all()
    assert len(agents) == 2
