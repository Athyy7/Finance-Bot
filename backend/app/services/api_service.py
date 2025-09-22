from typing import Any, Dict, Tuple

import httpx
from fastapi import Depends, status
from fastapi.exceptions import HTTPException

from backend.app.config.settings import settings
from backend.app.models.domain.error import Error
from backend.app.repositories.error_repository import ErrorRepo


class ApiService:
    def __init__(self, error_repo: ErrorRepo = Depends(ErrorRepo)) -> None:
        self.timeout = httpx.Timeout(
            connect=settings.API_SERVICE_CONNECT_TIMEOUT,
            read=settings.API_SERVICE_READ_TIMEOUT,
            write=settings.API_SERVICE_WRITE_TIMEOUT,
            pool=settings.API_SERVICE_POOL_TIMEOUT,
        )
        self.error_repo = error_repo

    async def get(
        self, url: str, headers: dict = None, data: dict = None
    ) -> httpx.Response:
        """
        Sends an asynchronous GET request with a timeout.
        :param url: The URL to send the request to.
        :param headers: Optional HTTP headers.
        :param data: Optional query parameters.
        :return: The HTTP response.
        """
        try:

            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                response = await client.get(url, headers=headers, params=data)
                response.raise_for_status()
                try:
                    return response.json()
                except:
                    return response.text
        except httpx.RequestError as exc:
            error_msg = (
                f"An error occurred while requesting {exc.request.url!r}."
            )
            await self.error_repo.insert_error(Error(error_message=error_msg))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )
        except httpx.HTTPStatusError as exc:
            error_msg = f"Error response {exc.response.status_code} while requesting {exc.request.url!r}. \n error from api_service in get()"
            await self.error_repo.insert_error(Error(error_message=error_msg))
            raise HTTPException(
                status_code=exc.response.status_code, detail=error_msg
            )

    async def post(
        self,
        url: str,
        headers: dict = None,
        data: dict = None,
        files: dict = None,
    ) -> httpx.Response:
        """
        Sends an asynchronous POST request with a timeout.
        :param url: The URL to send the request to.
        :param headers: Optional HTTP headers.
        :param data: The payload to send in JSON format.
        :return: The HTTP response.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                if files:
                    response = await client.post(
                        url, headers=headers, data=data, files=files
                    )
                else:
                    response = await client.post(
                        url, headers=headers, json=data
                    )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"API request failed with error: {str(exc)} \n , {exc.response.text}"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"API request failed with error: {str(exc)} \n , {exc.response.text}",
            )
        except httpx.RequestError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"API request failed with error: {str(exc)} \n error from api_service in post()"
                )
            )
            raise HTTPException(
                status_code=500,
                detail=f"API request failed with error: {str(exc)} \n error from api_service in post()",
            )

        except Exception as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"API request failed with error: {str(exc)} \n error from api_service in post()"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"API request failed with error: {str(exc)} \n error from api_service in post()",
            )

    async def post_with_cookies(
        self,
        url: str,
        json_data: dict = None,
        headers: dict = None,
        cookies: dict = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Sends an asynchronous POST request and returns both response data and cookies.

        :param url: The URL to send the request to.
        :param json_data: The payload to send in JSON format.
        :param headers: Optional HTTP headers.
        :param cookies: Optional cookies to send with the request.
        :return: Tuple containing (response_data, response_cookies)
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False, cookies=cookies
            ) as client:
                response = await client.post(
                    url, headers=headers, json=json_data
                )
                response.raise_for_status()

                # Extract cookies from response
                response_cookies = dict(response.cookies)

                # Parse response data
                try:
                    response_data = response.json()
                except ValueError:
                    response_data = {"text": response.text}

                return response_data, response_cookies

        except httpx.HTTPStatusError as exc:
            error_msg = f"HTTP error {exc.response.status_code} while requesting {exc.request.url!r}."
            if hasattr(exc.response, "text"):
                error_msg += f" Response: {exc.response.text}"
            await self.error_repo.insert_error(Error(error_message=error_msg))
            raise HTTPException(
                status_code=exc.response.status_code, detail=error_msg
            )
        except httpx.RequestError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"Request error while accessing {exc.request.url!r}: {str(exc)}"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Request error while accessing {exc.request.url!r}: {str(exc)}",
            )
        except Exception as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"Unexpected error in post_with_cookies: {str(exc)}"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error in post_with_cookies: {str(exc)}",
            )

    async def post_stream(
        self,
        url: str,
        headers: dict = None,
        data: dict = None,
    ):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                # Use stream=True to get a streaming response
                async with client.stream(
                    "POST", url, headers=headers, json=data
                ) as response:
                    response.raise_for_status()
                    # For Anthropic streaming, we need to parse the stream
                    async for line in response.aiter_lines():
                        if line.strip():
                            yield line

        except httpx.HTTPStatusError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"Streaming API request failed with error: {str(exc)} \n , {exc.response.text}"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Streaming API request failed with error: {str(exc)} \n , {exc.response.text} error from api_service in post_stream()",
            )
        except httpx.RequestError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"Streaming API request failed with error: {str(exc)} \n error from api_service in post_stream()"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Streaming API request failed with error: {str(exc)} \n error from api_service in post_stream()",
            )
        except Exception as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"Streaming API request failed with error: {str(exc)} \n error from api_service in post_stream()"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Streaming API request failed with error: {str(exc)} \n error from api_service in post_stream()",
            )

    async def delete(
        self,
        url: str,
        headers: dict = None,
    ) -> httpx.Response:
        """
        Sends an asynchronous DELETE request with a timeout.
        :param url: The URL to send the request to.
        :param headers: Optional HTTP headers.
        :return: The HTTP response.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()
                try:
                    return response.json()
                except:
                    return {"success": True}
        except httpx.HTTPStatusError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"DELETE request failed with error: {str(exc)} \n , {exc.response.text}"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"DELETE request failed with error: {str(exc)} \n , {exc.response.text}",
            )
        except httpx.RequestError as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"DELETE request failed with error: {str(exc)} \n error from api_service in delete()"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"DELETE request failed with error: {str(exc)} \n error from api_service in delete()",
            )
        except Exception as exc:
            await self.error_repo.insert_error(
                Error(
                    error_message=f"DELETE request failed with error: {str(exc)} \n error from api_service in delete()"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"DELETE request failed with error: {str(exc)} \n error from api_service in delete()",
            )
