import json
from typing import Any, Dict, List, Optional

from fastapi import Depends

from backend.app.config.settings import settings
from backend.app.models.domain.error import Error
from backend.app.repositories.error_repository import ErrorRepo
from backend.app.repositories.llm_usage_repository import LLMUsageRepository
from backend.app.services.api_service import ApiService
from backend.app.utils.request_context import get_request_id


class OpenAIService:
    def __init__(
        self,
        llm_usage_repo: LLMUsageRepository = Depends(),
        error_repo: ErrorRepo = Depends(),
        api_service: ApiService = Depends(),
    ):
        self.llm_usage_repo = llm_usage_repo
        self.error_repo = error_repo
        self.api_service = api_service
        self.openai_api_key = settings.OPENAI_API_KEY
        self.openai_model = settings.OPENAI_MODEL
        self.base_url = settings.OPENAI_BASE_URL

    async def create_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Create a chat completion using the OpenAI API.

        Args:
            messages: List of message objects with role and content
            tools: Optional list of tool definitions
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)

        Returns:
            Response from OpenAI API
        """
        try:
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            }

            # Prepare payload
            payload = {
                "model": self.openai_model,
                "messages": messages,
                "temperature": temperature,
            }

            if self.openai_model in ["gpt-5-2025-08-07", "gpt-5-mini-2025-08-07", "gpt-5-nano-2025-08-07"]:
                payload["temperature"] = 1.0
                # payload["reasoning"] = {
                #     "effort" : "low"
                # }

            # Add max_tokens if provided
            if max_tokens is not None:
                if self.openai_model in ["gpt-5-2025-08-07", "gpt-5-mini-2025-08-07", "gpt-5-nano-2025-08-07"]:
                    payload["max_completion_tokens"] = max_tokens
                else:
                    payload["max_tokens"] = max_tokens

            # Add tools if provided
            if tools:
                payload["tools"] = tools

            # Make the API call using ApiService
            response_data = await self.api_service.post(
                url=f"{self.base_url}/chat/completions",
                headers=headers,
                data=payload,
            )

            with open("jsons/openai_response_data.json", "a") as f:
                f.write(json.dumps(response_data, indent=4))

            # Log the usage (if needed)
            await self._log_usage(payload, response_data)

            return response_data

        except Exception as e:
            # ApiService already handles and logs HTTP errors, so we just need to handle any additional errors
            error_message = f"Unexpected error in create_completion: {str(e)}"
            error = Error(tool_name="openai_api", error_message=error_message)
            await self.error_repo.insert_error(error)
            raise e

    async def _log_usage(
        self, request_data: Dict[str, Any], response_data: Dict[str, Any]
    ) -> None:
        """
        Log the usage statistics for the API call.

        Args:
            request_data: The request payload sent to OpenAI
            response_data: The response received from OpenAI
        """
        try:
            # Get request ID from context
            request_id = get_request_id()

            usage = response_data.get("usage", {})
            usage_data = {
                "request_id": request_id,
                "model": request_data.get("model"),
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "provider": "openai",
                "request_data": request_data,
                "response_data": response_data,
            }

            await self.llm_usage_repo.add_llm_usage(usage_data)
        except Exception as e:
            # Log the error but don't fail the main operation
            error = Error(
                tool_name="openai_api",
                error_message=f"Failed to log usage: {str(e)}",
            )
            await self.error_repo.insert_error(error)
