from typing import Any, Dict, List, Optional
from enum import Enum


from backend.app.tools.base.tool_base import BaseTool

class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

class ToolRegistry:
    """Registry for managing and providing tools to agents."""

    def __init__(self, include_default_tools: bool = True):
        self._tools: Dict[str, BaseTool] = {}

        if include_default_tools:
            self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default tools."""
        # Import default tools here to avoid circular imports
        try:
            from backend.app.tools.implementations.calculator_tool import CalculatorTool
            self.calculator_tool = CalculatorTool()
            self.register(self.calculator_tool)
        except ImportError:
            # Tools not implemented yet, continue without them
            pass
            
        try:
            from backend.app.tools.implementations.get_user_information_tool import GetUserInformationTool
            self.get_user_information_tool = GetUserInformationTool()
            self.register(self.get_user_information_tool)
        except ImportError:
            # Tool not implemented yet, continue without it
            pass
        

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: The tool instance to register
        """
        tool_definition = tool.get_tool_definition
        if callable(tool_definition):
            tool_definition = tool_definition()
        tool_name = tool_definition.get("name")

        if not tool_name:
            raise ValueError("Tool must have a 'name' in its definition")

        self._tools[tool_name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a specific tool by name.

        Args:
            name: Name of the tool to retrieve

        Returns:
            The tool instance or None if not found
        """
        return self._tools.get(name)

    def get_all_tools(
        self,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ) -> Dict[str, BaseTool]:
        """
        Get all registered tools with optional filtering.

        Args:
            include_tools: List of tool names to include (if provided, only these tools are returned)
            exclude_tools: List of tool names to exclude from the results

        Returns:
            Dictionary of filtered tools {tool_name: tool_instance}
        """
        filtered_tools = {}

        for name, tool in self._tools.items():
            # If include_tools is specified, only include those tools
            if include_tools is not None:
                if name not in include_tools:
                    continue

            # Exclude tools if specified
            if exclude_tools is not None:
                if name in exclude_tools:
                    continue

            filtered_tools[name] = tool

        return filtered_tools

    def get_tools_for_provider(
        self,
        provider: LLMProvider,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get tool definitions formatted for specific LLM provider.

        Args:
            provider: The LLM provider to format tools for
            include_tools: List of tool names to include
            exclude_tools: List of tool names to exclude

        Returns:
            List of tool definitions formatted for the specified provider
        """
        filtered_tools = self.get_all_tools(include_tools, exclude_tools)
        tool_definitions = []

        for tool in filtered_tools.values():
            tool_definition = tool.get_tool_definition
            if callable(tool_definition):
                tool_definition = tool_definition()

            if provider == LLMProvider.OPENAI:
                # OpenAI format (assuming the base format is already OpenAI-compatible)
                formatted_definition = self._format_for_openai(tool_definition)
            elif provider == LLMProvider.ANTHROPIC:
                # Anthropic format
                formatted_definition = self._format_for_anthropic(
                    tool_definition
                )
            else:
                # Default to original format
                formatted_definition = tool_definition

            tool_definitions.append(formatted_definition)

        return tool_definitions

    def _format_for_openai(
        self, tool_definition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Format tool definition for OpenAI API.
        Converts from Anthropic format (base) to OpenAI format.

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "Tool description",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...],
                    "additionalProperties": false
                },
                "strict": true
            }
        }
        """

        #OpenAI Suggests to use strict True for function calling so they can reliably adhere to function schema
        openai_format = {
            "type": "function",
            "function": {
                "name": tool_definition.get("name"),
                "description": tool_definition.get("description"),
                # "strict": True, # Strict True karne se every parameter required me jayega, optional parameter he to use type me list bana ke ek null add kardo
            },
        }

        # Convert input_schema to parameters
        if "input_schema" in tool_definition:
            parameters = tool_definition["input_schema"].copy()
            # Add additionalProperties: false for OpenAI strict mode
            parameters["additionalProperties"] = False
            openai_format["function"]["parameters"] = parameters

        return openai_format

    def _format_for_anthropic(
        self, tool_definition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Format tool definition for Anthropic API.
        Assumes the base format is already Anthropic-compatible.

        Anthropic format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
        """
        return tool_definition

    def list_tool_names(self) -> List[str]:
        """
        Get a list of all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def tool_count(self) -> int:
        """
        Get the count of registered tools.

        Returns:
            Number of registered tools
        """
        return len(self._tools)

    def clear_registry(self) -> None:
        """
        Clear all registered tools.
        Useful for testing or resetting the registry.
        """
        self._tools.clear()
