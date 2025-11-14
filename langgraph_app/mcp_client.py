# mcp_client.py
import asyncio
from fastmcp import Client

class MCPClientWrapper:
    """A wrapper for connecting to and calling MCP server tools dynamically."""

    def __init__(self, base_url="http://localhost:8000/mcp"):
        self.base_url = base_url
        self.client = None
        self.connected = False

    async def connect(self):
        """Connect to MCP server (only once per session)."""
        if not self.connected:
            self.client = Client(self.base_url)
            await self.client.__aenter__()  # async context manager
            self.connected = True
            print("✅ Connected to MCP server")

    async def call_tool(self, tool_name, params=None):
        """Call any MCP tool dynamically."""
        if not self.connected:
            print("client....")
            await self.connect()
        result = await self.client.call_tool(tool_name, params or {})
        print("result: ", result)
        return result
