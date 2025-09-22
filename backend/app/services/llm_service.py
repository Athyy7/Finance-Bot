import json
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, status

from backend.app.models.domain.error import Error
from backend.app.repositories.error_repository import ErrorRepo
from backend.app.services.anthropic_service import AnthropicService
from backend.app.services.openai_service import OpenAIService
# from backend.app.tools.registry.tool_registry import ToolRegistry
from backend.app.models.schemas.llm_schema import LLMProvider




class LLMService:
    def __init__(
        self,
        anthropic_service: AnthropicService = Depends(),
        openai_service: OpenAIService = Depends(),
        error_repo: ErrorRepo = Depends(),
        # tool_registry: ToolRegistry = Depends(),
        primary_provider: LLMProvider = LLMProvider.ANTHROPIC,
        fallback_provider: LLMProvider = LLMProvider.OPENAI,
    ) -> None:
        self.anthropic_service = anthropic_service
        self.openai_service = openai_service
        self.error_repo = error_repo

        # Default configuration
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        
        # self.tool_registry = tool_registry

        # Service mapping
        self.service_map = {
            LLMProvider.ANTHROPIC: self.anthropic_service,
            LLMProvider.OPENAI: self.openai_service,
        }

    async def log_fallback_event(
        self, primary_error: Exception, provider: str
    ) -> None:
        """Log when a fallback occurs"""
        error_message = f"LLM fallback from {provider} to fallback provider. Error: {str(primary_error)}"
        error = Error(tool_name="llm_service", error_message=error_message)
        await self.error_repo.insert_error(error)

    async def create_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = 1024,
        system: Optional[str] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = 0,
        primary_provider: Optional[LLMProvider] = None,
        fallback_provider: Optional[LLMProvider] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Create a completion with fallback mechanism.
        Primary provider: Anthropic (default, can be overridden per call)
        Fallback provider: OpenAI (triggered when primary returns status code >= 500)

        Args:
            messages: List of message objects with role and content
            tools: Optional list of tool definitions
            max_tokens: Maximum number of tokens to generate
            system: Optional system prompt (Anthropic only)
            tool_choice: Optional tool choice configuration (Anthropic only)
            temperature: Optional temperature for randomness
            primary_provider: Optional override for primary provider (per-call)
            fallback_provider: Optional override for fallback provider (per-call)
            **kwargs: Additional parameters

        Returns:
            Response from LLM API (Anthropic or OpenAI)
        """
        # Use per-call providers if provided, otherwise use instance defaults
        effective_primary = primary_provider if primary_provider is not None else self.primary_provider
        effective_fallback = fallback_provider if fallback_provider is not None else self.fallback_provider
        
        try:
            # Try primary provider first
            if effective_primary == LLMProvider.ANTHROPIC:
                # raise HTTPException(status_code=529, detail="Faato")
                anthropic_response = await self.anthropic_service.create_message(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens if max_tokens is not None else 1024,
                    system=system,
                    tool_choice=tool_choice,
                    temperature=temperature,
                )
                anthropic_response["llm_provider"] = LLMProvider.ANTHROPIC
                anthropic_response["fallback_llm_provider"] = LLMProvider.OPENAI
                anthropic_response["llm_responded"] = LLMProvider.ANTHROPIC
                with open("anthropic_response.json", "w") as f:
                    json.dump(anthropic_response, f)
                return anthropic_response
            else:
                openai_response = await self.openai_service.create_completion(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature if temperature is not None else 0.0,
                )
                openai_response["llm_provider"] = LLMProvider.OPENAI
                openai_response["fallback_llm_provider"] = LLMProvider.ANTHROPIC
                openai_response["llm_responded"] = LLMProvider.OPENAI
                return openai_response

        except HTTPException as e:
            # Check if the error is a server error (status code >= 500)
            if e.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                print(f"🔴 Primary LLM service failed, Going to secondary")
                await self.log_fallback_event(e, effective_primary)

                # Adjust parameters for fallback provider
                fallback_params = self._adjust_params_for_fallback(
                    {
                        "messages": messages,
                        "tools": tools,
                        "max_tokens": max_tokens,
                        "system": system,
                        "tool_choice": tool_choice,
                        "temperature": temperature,
                        **kwargs,
                    }
                )

                try:
                    # Fallback to secondary provider
                    if effective_fallback == LLMProvider.OPENAI:

                        openai_tools = []
                        for tool in tools :
                            openai_tools.append(self.tool_registry._format_for_openai(tool))

                        fallback_params["tools"] = openai_tools
                            
                        with open("fallback_tools.json", "w") as f:
                            json.dump(openai_tools, f)

                        print(f"🔴 Fallback to secondary provider: OpenAI")
                    
                        # with open("fallback_params.json", "w") as f:
                        #     json.dump(fallback_params, f)
                       
                        
                        openai_response = await self.openai_service.create_completion(
                            messages=fallback_params["messages"],
                            tools=fallback_params.get("tools"),
                            max_tokens=fallback_params.get("max_tokens"),
                            temperature=fallback_params.get("temperature", 0.0),
                        )
                        openai_response["llm_provider"] = LLMProvider.ANTHROPIC
                        openai_response["fallback_llm_provider"] = LLMProvider.OPENAI
                        openai_response["llm_responded"] = LLMProvider.OPENAI

                        # print(f"openai_response : {openai_response}")
                        # with open("openai_response.json", "w") as f:
                        #     json.dump(openai_response, f)
                        # print(f"type of openai_response : {type(openai_response)}")

                        return openai_response
                    else:
                        anthropic_response = await self.anthropic_service.create_message(
                            messages=fallback_params["messages"],
                            tools=fallback_params.get("tools"),
                            max_tokens=fallback_params.get("max_tokens", 1024),
                            system=fallback_params.get("system"),
                            tool_choice=fallback_params.get("tool_choice"),
                            temperature=fallback_params.get("temperature"),
                        )
                        anthropic_response["llm_provider"] = LLMProvider.OPENAI
                        anthropic_response["fallback_llm_provider"] = LLMProvider.ANTHROPIC
                        anthropic_response["llm_responded"] = LLMProvider.ANTHROPIC
                        return anthropic_response

                except Exception as fallback_error:
                    # Both providers failed
                    error_message = f"Both LLM services failed. Primary ({effective_primary}): {str(e)}. Fallback ({effective_fallback}): {str(fallback_error)}"
                    error = Error(
                        tool_name="llm_service", error_message=error_message
                    )
                    await self.error_repo.insert_error(error)

                    raise HTTPException(
                        status_code=500,
                        detail=error_message,
                    )
            else:
                # Re-raise the error if it's not a server error
                await self.error_repo.insert_error(
                    Error(
                        tool_name="llm_service",
                        error_message=f"Primary LLM service failed: {str(e)}",
                    )
                )
                raise HTTPException(
                    status_code=e.status_code,
                    detail=f"Primary LLM service failed: {str(e)}",
                )

        except Exception as e:
            # For any other unexpected errors, try fallback
            await self.log_fallback_event(e, self.primary_provider)

            # Adjust parameters for fallback provider
            fallback_params = self._adjust_params_for_fallback(
                {
                    "messages": messages,
                    "tools": tools,
                    "max_tokens": max_tokens,
                    "system": system,
                    "tool_choice": tool_choice,
                    "temperature": temperature,
                    **kwargs,
                }
            )

            try:
                # Fallback to secondary provider
                if self.fallback_provider == LLMProvider.OPENAI:
                    return await self.openai_service.create_completion(
                        messages=fallback_params["messages"],
                        tools=fallback_params.get("tools"),
                        max_tokens=fallback_params.get("max_tokens"),
                        temperature=fallback_params.get("temperature", 0.0),
                    )
                else:
                    return await self.anthropic_service.create_message(
                        messages=fallback_params["messages"],
                        tools=fallback_params.get("tools"),
                        max_tokens=fallback_params.get("max_tokens", 1024),
                        system=fallback_params.get("system"),
                        tool_choice=fallback_params.get("tool_choice"),
                        temperature=fallback_params.get("temperature"),
                    )

            except Exception as fallback_error:
                # Both providers failed
                error_message = f"Both LLM services failed. Primary ({self.primary_provider}): {str(e)}. Fallback ({self.fallback_provider}): {str(fallback_error)}"
                error = Error(
                    tool_name="llm_service", error_message=error_message
                )
                await self.error_repo.insert_error(error)

                raise HTTPException(
                    status_code=500,
                    detail=error_message,
                )

    def _adjust_params_for_fallback(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Adjust parameters when switching between providers to ensure compatibility.

        Different LLM providers have different parameter names and expectations.
        This method translates between them.
        """
        # Clone the params to avoid modifying the original
        adjusted_params = params.copy()

        # Remove provider-specific parameters for OpenAI fallback
        if self.fallback_provider == LLMProvider.OPENAI:
            # OpenAI doesn't support system as a separate parameter (it should be in messages)
            # and doesn't support tool_choice in the same way
            # print(f"fallback to openai triggered here adjusted params : {adjusted_params}")
            system_prompt = adjusted_params.pop("system", None)
            adjusted_params.pop("tool_choice", None)

            # Convert messages to OpenAI format and handle system prompt
            messages = adjusted_params.get("messages", [])
            converted_messages = self._adjust_messages_for_fallback(messages, LLMProvider.OPENAI)
            
            # If there's a system prompt, add it as the first message
            if system_prompt:
                # Check if first message is already a system message
                if not converted_messages or converted_messages[0].get("role") != "system":
                    converted_messages.insert(
                        0, {"role": "system", "content": system_prompt}
                    )
            
            adjusted_params["messages"] = converted_messages

        # Anthropic-specific adjustments
        elif self.fallback_provider == LLMProvider.ANTHROPIC:
            # Anthropic uses system as a separate parameter
            # Extract system message from messages if present
            messages = adjusted_params.get("messages", [])
            converted_messages = self._adjust_messages_for_fallback(messages, LLMProvider.ANTHROPIC)
            
            if converted_messages and converted_messages[0].get("role") == "system":
                system_content = converted_messages[0]["content"]
                adjusted_params["system"] = system_content
                adjusted_params["messages"] = converted_messages[1:]  # Remove system message from messages
            else:
                adjusted_params["messages"] = converted_messages

        return adjusted_params

    def _adjust_messages_for_fallback(
        self, messages: List[Dict[str, Any]], target_provider: LLMProvider
    ) -> List[Dict[str, Any]]:
        """
        Convert messages between Anthropic and OpenAI formats.
        
        Args:
            messages: List of messages to convert
            target_provider: The provider format to convert to
            
        Returns:
            List of messages in the target provider's format
        """
        if not messages:
            return messages
            
        converted_messages = []
        
        for message in messages:
            converted_message = {"role": message.get("role")}
            content = message.get("content")
            
            if target_provider == LLMProvider.OPENAI:
                # Convert Anthropic format to OpenAI format
                converted_message.update(self._convert_to_openai_format(message, content))
            else:
                # Convert OpenAI format to Anthropic format
                converted_message.update(self._convert_to_anthropic_format(message, content))
                
            converted_messages.append(converted_message)
            
        return converted_messages
    
    def _convert_to_openai_format(self, message: Dict[str, Any], content: Any) -> Dict[str, Any]:
        """Convert a single message from Anthropic format to OpenAI format."""
        result = {}
        
        if isinstance(content, list):
            # Anthropic format with content blocks
            text_parts = []
            tool_calls = []
            
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    # Convert Anthropic tool_use to OpenAI tool_calls
                    tool_call = {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": str(block.get("input", {})) if block.get("input") else "{}"
                        }
                    }
                    tool_calls.append(tool_call)
                elif block.get("type") == "tool_result":
                    # This should be handled as a separate tool message
                    # Convert to OpenAI tool response format
                    result["role"] = "tool"
                    result["tool_call_id"] = block.get("tool_use_id")
                    result["content"] = str(block.get("content", ""))
                    return result
            
            # Set content and tool_calls for assistant messages
            if text_parts:
                result["content"] = " ".join(text_parts)
            if tool_calls:
                result["tool_calls"] = tool_calls
                
        elif message.get("role") == "user" and any(
            isinstance(content, list) and 
            any(block.get("type") == "tool_result" for block in content)
            for content in [message.get("content")]
        ):
            # Handle Anthropic tool result in user message
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        result["role"] = "tool"
                        result["tool_call_id"] = block.get("tool_use_id")
                        result["content"] = str(block.get("content", ""))
                        break
        else:
            # Simple string content
            result["content"] = str(content) if content is not None else ""
            
        return result
    
    def _convert_to_anthropic_format(self, message: Dict[str, Any], content: Any) -> Dict[str, Any]:
        """Convert a single message from OpenAI format to Anthropic format."""
        result = {}
        
        # Handle OpenAI tool responses
        if message.get("role") == "tool":
            # Convert OpenAI tool response to Anthropic format
            result["role"] = "user"
            result["content"] = [{
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id"),
                "content": str(content) if content is not None else ""
            }]
            return result
        
        # Handle OpenAI assistant messages with tool calls
        if message.get("tool_calls"):
            content_blocks = []
            
            # Add text content if present
            if content:
                content_blocks.append({
                    "type": "text",
                    "text": str(content)
                })
            
            # Convert tool calls to Anthropic format
            for tool_call in message.get("tool_calls", []):
                function = tool_call.get("function", {})
                arguments = function.get("arguments", "{}")
                
                # Parse arguments if it's a string
                try:
                    if isinstance(arguments, str):
                        parsed_args = json.loads(arguments)
                    else:
                        parsed_args = arguments
                except:
                    parsed_args = arguments
                
                content_blocks.append({
                    "type": "tool_use",
                    "id": tool_call.get("id"),
                    "name": function.get("name"),
                    "input": parsed_args
                })
            
            result["content"] = content_blocks
        else:
            # Simple text content - wrap in Anthropic format
            if content:
                result["content"] = [{
                    "type": "text",
                    "text": str(content)
                }]
            else:
                result["content"] = []
                
        return result

    def set_providers(
        self, primary: LLMProvider, fallback: LLMProvider
    ) -> None:
        """
        Set the primary and fallback LLM providers.

        Args:
            primary: The primary LLM provider to use
            fallback: The fallback LLM provider to use when primary fails
        """
        if primary == fallback:
            raise ValueError("Primary and fallback providers must be different")

        self.primary_provider = primary
        self.fallback_provider = fallback
