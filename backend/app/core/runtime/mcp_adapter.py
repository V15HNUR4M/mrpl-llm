from typing import Dict, Any

from app.core.runtime.tool_executor import Tool, AuthorizationPolicy
from app.core.runtime.schemas import ToolResult

class MCPServerUnavailableError(Exception):
    """Raised when the MCP server cannot be reached."""

class MCPServerClient:
    """
    Thin async client for an MCP server (HTTP transport).
    Statically configured — no dynamic trust delegation.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url
        self.timeout = timeout

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Calls the MCP server and returns the raw response dict."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/tools/call",
                    json={"name": tool_name, "arguments": arguments}
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            raise MCPServerUnavailableError(f"Cannot connect to MCP server at {self.base_url}")
        except Exception as e:
            raise RuntimeError(f"MCP call error: {e}")

class MCPAdapter(Tool):
    """
    Adapts an MCP-server-backed tool to the local Tool interface.
    The Harness sees this as an ordinary Tool — MCP is an implementation detail.
    """

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_schema: Dict[str, Any],
        mcp_client: MCPServerClient,
        authorization_policy: AuthorizationPolicy = None,
    ):
        self._name = tool_name
        self._description = tool_description
        self._schema = tool_schema
        self._client = mcp_client
        self._auth_policy = authorization_policy or AuthorizationPolicy.PUBLIC
        self._enabled = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self._schema

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return self._auth_policy

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            raw_result = await self._client.call_tool(self._name, arguments)
            # Normalize MCP output into ToolResult
            if isinstance(raw_result, dict):
                status = "error" if raw_result.get("isError") else "success"
                # Extract content
                content = raw_result.get("content", raw_result)
                if isinstance(content, list):
                    # MCP returns content as list of {type, text} blocks
                    output = "\n".join(
                        item.get("text", str(item)) for item in content
                        if isinstance(item, dict)
                    )
                else:
                    output = content
            else:
                output = str(raw_result)
                status = "success"

            return ToolResult(output=output, status=status)

        except MCPServerUnavailableError:
            return ToolResult(
                output=f"MCP server for tool '{self._name}' is unavailable.",
                status="error",
                metadata={"error_type": "mcp_unavailable"}
            )
        except Exception as e:
            return ToolResult(
                output=f"MCP call failed: {str(e)}",
                status="error",
                metadata={"error_type": "mcp_error"}
            )
