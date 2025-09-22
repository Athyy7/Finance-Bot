import asyncio
import logging
from typing import Dict, Any, Optional
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

from backend.app.utils.logging_utils import loggers


class MCPClientService:
    """
    Pythonic MCP client service for calling tools on the MCP server
    Supports both SSE and stdio transports using async context managers
    """
    
    def __init__(self, transport_type: str = "sse", server_url: str = "http://localhost:8000/sse"):
        self.server_url = server_url
        self.transport_type = transport_type.lower()
        self._session_context = None
        self._streams_context = None
        self.session: Optional[ClientSession] = None
        self.available_tools = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """Connect to the MCP server using the appropriate transport"""
        try:
            if self.transport_type == "sse":
                self._streams_context = sse_client(self.server_url)
                streams = await self._streams_context.__aenter__()
                
                self._session_context = ClientSession(streams[0], streams[1])
                self.session = await self._session_context.__aenter__()
                
                await self.session.initialize()
                loggers["mcp"].info(f"Connected to MCP server at {self.server_url} using SSE transport")
                
            elif self.transport_type == "stdio":
                # For OpenMemory MCP server
                #                 {
                #   "mcp": {
                #     "servers": {
                #       "memory": {
                #         "command": "npx",
                #         "args": [
                #           "-y",
                #           "@modelcontextprotocol/server-memory"
                #         ]
                #       }
                #     }
                #   }
                # }

                # KnowledgeGraph MCP Server
                # server_params = StdioServerParameters(
                #     command="npx",
                #     args=["-y", "@modelcontextprotocol/server-memory"]
                # )

                # For OpenMemory MCP server
                server_params = StdioServerParameters(
                    command="npx",
                    args=["-y", "openmemory"],
                    env={
                        "OPENMEMORY_API_KEY": "om-ohm3oii81sptaxjxepix71ghvhl5t321",
                        "CLIENT_NAME": "openmemory"
                    }
                )
                
                self._streams_context = stdio_client(server_params)
                streams = await self._streams_context.__aenter__()
                
                self._session_context = ClientSession(streams[0], streams[1])
                self.session = await self._session_context.__aenter__()
                
                await self.session.initialize()
                loggers["mcp"].info("Connected to OpenMemory MCP server using stdio transport")
                
            else:
                raise ValueError(f"Unsupported transport type: {self.transport_type}")
            
            # Fetch available tools
            tools_response = await self.session.list_tools()
            self.available_tools = tools_response.tools
            loggers["mcp"].info(f"Available tools: {[tool.name for tool in self.available_tools]}")
            
        except Exception as e:
            loggers["mcp"].error(f"Failed to connect to MCP server: {str(e)}")
            await self.disconnect()
            raise
    
    async def disconnect(self):
        """Clean disconnect from the MCP server"""
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
                self._session_context = None
                self.session = None
                
            if self._streams_context:
                await self._streams_context.__aexit__(None, None, None)
                self._streams_context = None
                
            loggers["mcp"].info("Disconnected from MCP server")
            
        except Exception as e:
            loggers["mcp"].error(f"Error during disconnect: {str(e)}")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Call a tool on the MCP server
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool (defaults to empty dict)
            
        Returns:
            Tool result as dictionary
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server. Use 'async with' or call connect() first.")
        
        try:
            arguments = arguments or {}
            result = await self.session.call_tool(tool_name, arguments)
            loggers["mcp"].info(f"Called tool {tool_name} with args {arguments}")
            return result.model_dump()
            
        except Exception as e:
            loggers["mcp"].error(f"Error calling tool {tool_name}: {str(e)}")
            return {"error": str(e)}

    async def list_tools(self) -> Dict[str, Any]:
        """
        List available tools on the MCP server
        
        Returns:
            Dictionary containing available tools
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server. Use 'async with' or call connect() first.")
        
        try:
            # Return cached tools if available
            if self.available_tools:
                return {"tools": [tool.model_dump() for tool in self.available_tools]}
            
            # Fetch fresh tools
            tools_response = await self.session.list_tools()
            self.available_tools = tools_response.tools
            return {"tools": [tool.model_dump() for tool in self.available_tools]}
            
        except Exception as e:
            loggers["mcp"].error(f"Error listing tools: {str(e)}")
            return {"error": str(e)}

    async def list_prompts(self) -> Dict[str, Any]:
        """List available prompts on the MCP server"""
        if not self.session:
            raise RuntimeError("Not connected to MCP server. Use 'async with' or call connect() first.")
        
        try:
            result = await self.session.list_prompts()
            return result.model_dump()
        except Exception as e:
            loggers["mcp"].error(f"Error listing prompts: {str(e)}")
            return {"error": str(e)}

    async def get_prompt(self, name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get a specific prompt from the MCP server"""
        if not self.session:
            raise RuntimeError("Not connected to MCP server. Use 'async with' or call connect() first.")
        
        try:
            arguments = arguments or {}
            result = await self.session.get_prompt(name, arguments)
            return result.model_dump()
        except Exception as e:
            loggers["mcp"].error(f"Error getting prompt {name}: {str(e)}")
            return {"error": str(e)}


# Convenience functions for one-off operations
async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any] = None, 
                       transport: str = "stdio", server_url: str = "http://localhost:8000/sse") -> Dict[str, Any]:
    """
    Convenience function to call an MCP tool with automatic connection management
    
    Usage:
        result = await call_mcp_tool("add-memory", {"content": "User likes coffee"})
    """
    async with MCPClientService(transport, server_url) as client:
        return await client.call_tool(tool_name, arguments)


async def list_mcp_tools(transport: str = "stdio", server_url: str = "http://localhost:8000/sse") -> Dict[str, Any]:
    """
    Convenience function to list MCP tools with automatic connection management
    
    Usage:
        tools = await list_mcp_tools()
    """
    async with MCPClientService(transport, server_url) as client:
        return await client.list_tools() 