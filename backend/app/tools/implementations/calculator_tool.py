import json
from typing import Any, Dict

from backend.app.tools.base.tool_base import BaseTool


class CalculatorTool(BaseTool):
    """
    A simple calculator tool for basic mathematical operations.
    Supports addition, subtraction, multiplication, and division.
    """

    @property
    def get_tool_definition(self) -> Dict[str, Any]:
        """Get the tool definition for Anthropic API."""
        return {
            "name": "calculator",
            "description": "Perform basic mathematical calculations. Supports addition (+), subtraction (-), multiplication (*), and division (/).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2 + 3', '10 * 4', '100 / 5')"
                    }
                },
                "required": ["expression"]
            }
        }

    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """
        Execute the calculator tool.
        
        Args:
            parameters: Tool parameters containing the mathematical expression
            
        Returns:
            Result of the calculation or error message
        """
        try:
            expression = parameters.get("expression", "").strip()
            
            if not expression:
                return {
                    "success": False,
                    "error": "No expression provided",
                    "result": None
                }
            
            # Basic security: only allow safe mathematical operations
            allowed_chars = set("0123456789+-*/(). ")
            if not all(char in allowed_chars for char in expression):
                return {
                    "success": False,
                    "error": "Expression contains invalid characters. Only numbers, +, -, *, /, (, ), and spaces are allowed.",
                    "result": None
                }
            
            # Evaluate the expression safely
            try:
                result = eval(expression)
                
                # Check if result is a valid number
                if isinstance(result, (int, float)):
                    return {
                        "success": True,
                        "expression": expression,
                        "result": result,
                        "formatted_result": f"{expression} = {result}"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Expression did not evaluate to a number",
                        "result": None
                    }
                    
            except ZeroDivisionError:
                return {
                    "success": False,
                    "error": "Division by zero is not allowed",
                    "result": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Invalid mathematical expression: {str(e)}",
                    "result": None
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Calculator tool error: {str(e)}",
                "result": None
            }
