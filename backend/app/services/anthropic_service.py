import json
import time
from typing import Any, Dict, List, Optional

import anthropic
from fastapi import Depends

from backend.app.config.settings import settings
from backend.app.models.domain.error import Error
from backend.app.repositories.error_repository import ErrorRepo
from backend.app.repositories.llm_usage_repository import LLMUsageRepository
from backend.app.services.api_service import ApiService
from backend.app.utils.request_context import get_request_id


class AnthropicService:
    def __init__(
        self,
        llm_usage_repo: LLMUsageRepository = Depends(),
        error_repo: ErrorRepo = Depends(),
        api_service: ApiService = Depends(),
    ):
        self.llm_usage_repo = llm_usage_repo
        self.error_repo = error_repo
        self.api_service = api_service
        self.anthropic_api_key = settings.ANTHROPIC_API_KEY
        self.anthropic_model = settings.ANTHROPIC_MODEL
        self.base_url = settings.ANTHROPIC_BASE_URL
        
        # Initialize Anthropic SDK client for streaming
        self.client = anthropic.AsyncAnthropic(
            api_key=self.anthropic_api_key
        )

    async def create_message(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1024,
        system: Optional[str] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = 0.0,
    ) -> Dict[str, Any]:
        """
        Create a message using the Anthropic API.

        Args:
            messages: List of message objects with role and content
            tools: Optional list of tool definitions
            max_tokens: Maximum number of tokens to generate
            system: Optional system prompt
            tool_choice: Optional tool choice configuration
            temperature: Optional temperature for randomness

        Returns:
            Response from Anthropic API
        """
        try:
            # Prepare headers
            headers = {
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }

            # Prepare payload
            payload = {
                "model": self.anthropic_model,
                "max_tokens": max_tokens,
                "messages": messages,
            }

            # Add optional parameters
            if system:
                payload["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]

            if tools:
                # Add cache_control to the last tool if tools are provided
                if tools and len(tools) > 0:
                    last_tool = tools[-1]
                    if "cache_control" not in last_tool:
                        last_tool["cache_control"] = {"type": "ephemeral"}
                payload["tools"] = tools

            if tool_choice:
                payload["tool_choice"] = tool_choice

            if temperature is not None:
                payload["temperature"] = temperature

            # Make the API call using ApiService
            response_data = await self.api_service.post(
                url=f"{self.base_url}/v1/messages",
                headers=headers,
                data=payload,
            )

            # Log the usage (if needed)
            await self._log_usage(payload, response_data)

            return response_data

        except Exception as e:
            # ApiService already handles and logs HTTP errors, so we just need to handle any additional errors
            error_message = f"Unexpected error in create_message: {str(e)}"
            error = Error(
                tool_name="anthropic_api", error_message=error_message
            )
            await self.error_repo.insert_error(error)
            raise e

    async def _log_usage(
        self, request_data: Dict[str, Any], response_data: Dict[str, Any]
    ) -> None:
        """
        Log the usage statistics for the API call.

        Args:
            request_data: The request payload sent to Anthropic
            response_data: The response received from Anthropic
        """
        try:
            # Get request ID from context
            request_id = get_request_id()

            usage_data = {
                "request_id": request_id,
                "model": request_data.get("model"),
                "input_tokens": response_data.get("usage", {}).get(
                    "input_tokens", 0
                ),
                "output_tokens": response_data.get("usage", {}).get(
                    "output_tokens", 0
                ),
                "total_tokens": response_data.get("usage", {}).get(
                    "input_tokens", 0
                )
                + response_data.get("usage", {}).get("output_tokens", 0),
                "provider": "anthropic",
                "request_data": request_data,
                "response_data": response_data,
            }

            await self.llm_usage_repo.add_llm_usage(usage_data)
        except Exception as e:
            # Log the error but don't fail the main operation
            error = Error(
                tool_name="anthropic_api",
                error_message=f"Failed to log usage: {str(e)}",
            )
            await self.error_repo.insert_error(error)

    async def anthropic_sdk_stream_call(
        self,
        messages: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = 0.0,
        tool_choice: Optional[Dict[str, Any]] = None,
    ):
        """
        Create a streaming message using the Anthropic SDK.
        
        Args:
            messages: List of message objects with role and content
            model_name: Optional model name override (defaults to settings model)
            max_tokens: Maximum number of tokens to generate
            system_prompt: Optional system prompt
            tools: Optional list of tool definitions
            temperature: Optional temperature for randomness
            tool_choice: Optional tool choice configuration
            
        Yields:
            Stream events from Anthropic API
        """
        try:
            # Use provided model_name or fallback to settings
            model = model_name or self.anthropic_model
            
            # Build stream parameters
            stream_params = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }
            
            # Add optional parameters
            if system_prompt:
                stream_params["system"] = system_prompt
                
            if tools:
                stream_params["tools"] = tools
                
            if tool_choice:
                stream_params["tool_choice"] = tool_choice

            # Start streaming
            async with self.client.messages.stream(**stream_params) as stream:
                async for event in stream:
                    yield event

                # Get final message and add metadata
                final_message = await stream.get_final_message()
                request_id = getattr(stream, "_request_id", f"req_{int(time.time())}")

                final_message_dict = final_message.model_dump()
                final_message_dict["_request_id"] = request_id
                final_message_dict["_provider"] = "anthropic"

                # Final message content logged for debugging if needed

                # Yield final message event (only the dict format, not SSE string)
                yield {"type": "anthropic_final_message", "data": final_message_dict}

                # Log usage statistics
                await self._log_streaming_usage(stream_params, final_message, model)

        except Exception as e:
            # Log error
            error_message = f"Unexpected error in anthropic_sdk_stream_call: {str(e)}"
            error = Error(
                tool_name="anthropic_streaming_api", 
                error_message=error_message
            )
            await self.error_repo.insert_error(error)
            raise e

    async def _log_streaming_usage(
        self, 
        request_data: Dict[str, Any], 
        final_message: Any,
        model: str
    ) -> None:
        """
        Log the usage statistics for the streaming API call.

        Args:
            request_data: The request parameters sent to Anthropic
            final_message: The final message object from Anthropic stream
            model: The model used for the request
        """
        try:
            # Get request ID from context
            request_id = get_request_id()

            # Extract usage data from final message
            usage_data = {}
            if hasattr(final_message, 'usage') and final_message.usage:
                usage_data = {
                    "request_id": request_id,
                    "model": model,
                    "input_tokens": final_message.usage.input_tokens,
                    "output_tokens": final_message.usage.output_tokens,
                    "total_tokens": final_message.usage.input_tokens + final_message.usage.output_tokens,
                    "provider": "anthropic",
                    "request_data": request_data,
                    "response_data": final_message.model_dump(),
                }
            else:
                # Fallback if usage info not available
                usage_data = {
                    "request_id": request_id,
                    "model": model,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "provider": "anthropic",
                    "request_data": request_data,
                    "response_data": final_message.model_dump(),
                }

            await self.llm_usage_repo.add_llm_usage(usage_data)
        except Exception as e:
            # Log the error but don't fail the main operation
            error = Error(
                tool_name="anthropic_streaming_api",
                error_message=f"Failed to log streaming usage: {str(e)}",
            )
            await self.error_repo.insert_error(error)
