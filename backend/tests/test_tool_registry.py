import pytest
from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor, Tool
from app.core.runtime.schemas import ToolRequest, ToolResult

class DummyTool(Tool):
    @property
    def name(self) -> str:
        return "dummy_tool"
    
    @property
    def description(self) -> str:
        return "Dummy tool for testing"

    @property
    def input_schema(self) -> dict:
        return {}

    async def execute(self, arguments: dict, context: dict) -> ToolResult:
        return ToolResult(output={"result": "success"}, status="success")

@pytest.mark.asyncio
async def test_tool_registry():
    registry = ToolRegistry()
    registry.register(DummyTool())
    
    executor = LocalToolExecutor(registry)
    
    # 1. Allowed tool
    req = ToolRequest(tool="dummy_tool", arguments={}, call_id="123")
    res = await executor.execute(req, {}, allowed_tools=["dummy_tool"])
    assert res.status == "success"
    assert res.output["result"] == "success"
    
    # 2. Unauthorized tool
    req2 = ToolRequest(tool="dummy_tool", arguments={}, call_id="124")
    res2 = await executor.execute(req2, {}, allowed_tools=["other_tool"])
    assert res2.status == "error"
    assert "not allowed" in res2.output
    
    # 3. Unknown tool
    req3 = ToolRequest(tool="unknown_tool", arguments={}, call_id="125")
    res3 = await executor.execute(req3, {}, allowed_tools=["unknown_tool"])
    assert res3.status == "error"
    assert "Unknown tool" in res3.output
