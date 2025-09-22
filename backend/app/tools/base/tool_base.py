from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):

    @property
    @abstractmethod
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for the tool.
        """

    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """
        Execute the tool with the given parameters.
        """
