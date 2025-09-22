import asyncio
from typing import Any, Dict, List

import httpx
from fastapi import Depends, HTTPException

from backend.app.config.settings import settings

# from backend.app.models.domain.error import Error
from backend.app.repositories.error_repository import ErrorRepo

# from backend.app.services.embedding_tracing_service import embedding_tracing
# from backend.app.utils.logging_utils import loggers


class EmbeddingService:
    def __init__(self, error_repo: ErrorRepo = Depends(ErrorRepo)) -> None:
        self.error_repo = error_repo
        self.pinecone_api_key = settings.PINECONE_API_KEY
        self.dense_embed_url = settings.PINECONE_EMBED_URL
        self.pinecone_embedding_url = settings.PINECONE_EMBED_URL
        self.pinecone_api_version = settings.PINECONE_API_VERSION
        self.timeout = httpx.Timeout(
            connect=60.0,  # Time to establish a connection
            read=300.0,  # Time to read the response
            write=300.0,  # Time to send data
            pool=60.0,  # Time to wait for a connection from the pool
        )

    async def _log_error(
        self, error: Exception, operation: str, context: Dict[str, Any] = None
    ):
        """Log error to database with proper context"""
        try:
            await self.error_repo.log_error(
                error=error,
                additional_context={
                    "file": "embedding_service.py",
                    "operation": operation,
                    **(context or {}),
                },
            )
        except Exception:
            # Don't raise here to avoid cascading failures
            pass

    def _create_batches(
        self, inputs: List[Any], batch_size: int = 50
    ) -> List[List[Any]]:
        """Split inputs into batches of specified size"""
        batches = []
        for i in range(0, len(inputs), batch_size):
            batch = inputs[i : i + batch_size]
            batches.append(batch)
        return batches

    async def _process_single_batch(
        self,
        batch: List[Any],
        model_name: str,
        input_type: str,
        truncate: str = "END",
        dimension: int = 1024,
    ) -> Dict[str, Any]:
        """Process a single batch of inputs for embeddings"""
        # Convert string inputs to proper format for Pinecone API
        formatted_inputs = []
        for input_text in batch:
            if isinstance(input_text, str):
                formatted_inputs.append({"text": input_text})
            else:
                formatted_inputs.append(input_text)

        payload = {
            "model": model_name,
            "parameters": {
                "input_type": input_type,
                "truncate": truncate,
            },
            "inputs": formatted_inputs,
        }

        if model_name != "multilingual-e5-large":
            payload["parameters"]["dimension"] = dimension

        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json",
            "X-Pinecone-API-Version": self.pinecone_api_version,
        }

        url = self.dense_embed_url

        async with httpx.AsyncClient(
            timeout=self.timeout, verify=False
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"Error response body: {response.text}")
            response.raise_for_status()
            return response.json()

    async def pinecone_dense_embeddings_batch(
        self,
        inputs: List[Any],
        model_name: str,
        input_type: str,
        truncate: str = "END",
        dimension: int = 1024,
        batch_size: int = 50,
    ) -> Dict[str, Any]:
        """Process embeddings in parallel batches of specified size"""
        if not inputs:
            return {"data": []}

        # If inputs are smaller than batch size, process normally
        if len(inputs) <= batch_size:
            return await self._process_single_batch(
                inputs, model_name, input_type, truncate, dimension
            )

        try:
            # Split inputs into batches
            batches = self._create_batches(inputs, batch_size)
            print(
                f"=== DEBUG: Processing {len(inputs)} inputs in {len(batches)} batches of size {batch_size} ==="
            )

            # Process all batches in parallel
            batch_tasks = [
                self._process_single_batch(
                    batch, model_name, input_type, truncate, dimension
                )
                for batch in batches
            ]

            batch_responses = await asyncio.gather(*batch_tasks)

            # Combine all batch responses into a single response
            combined_data = []
            for response in batch_responses:
                if response and "data" in response:
                    combined_data.extend(response["data"])

            print(
                f"=== DEBUG: Combined {len(combined_data)} embeddings from {len(batches)} batches ==="
            )

            return {"data": combined_data}

        except Exception as e:
            await self._log_error(
                e,
                "pinecone_dense_embeddings_batch",
                {
                    "method": "pinecone_dense_embeddings_batch",
                    "model_name": model_name,
                    "input_type": input_type,
                    "truncate": truncate,
                    "dimension": dimension,
                    "input_count": len(inputs),
                    "batch_size": batch_size,
                    "batches_count": len(
                        self._create_batches(inputs, batch_size)
                    ),
                },
            )
            raise

    # @embedding_tracing(provider="pinecone")
    async def pinecone_dense_embeddings(
        self,
        inputs: list,
        model_name: str,
        input_type: str,
        truncate: str = "END",
        dimension: int = 1024,
    ):
        """
        Process embeddings with automatic batching for large inputs.
        Uses parallel processing for batches of 50 items.
        """
        try:
            print("=== DEBUG: Embedding Service ===")
            print(f"Model: {model_name}")
            print(f"Input type: {input_type}")
            print(f"Inputs count: {len(inputs)}")
            print(f"Inputs sample: {inputs[0] if inputs else 'None'}")

            # Use batch processing for better performance
            response_data = await self.pinecone_dense_embeddings_batch(
                inputs=inputs,
                model_name=model_name,
                input_type=input_type,
                truncate=truncate,
                dimension=dimension,
                batch_size=50,
            )

            return response_data

        except httpx.HTTPStatusError as e:
            await self._log_error(
                e,
                "pinecone_dense_embeddings_http_status",
                {
                    "method": "pinecone_dense_embeddings",
                    "model_name": model_name,
                    "input_type": input_type,
                    "truncate": truncate,
                    "dimension": dimension,
                    "status_code": (
                        e.response.status_code
                        if hasattr(e, "response")
                        and hasattr(e.response, "status_code")
                        else None
                    ),
                    "response_text": (
                        e.response.text
                        if hasattr(e, "response")
                        and hasattr(e.response, "text")
                        else None
                    ),
                    "input_count": len(inputs) if inputs else 0,
                },
            )

            raise HTTPException(
                status_code=400,
                detail=f"{str(e)}-{getattr(getattr(e, 'response', None), 'text', '')}",
            )
        except Exception as e:
            await self._log_error(
                e,
                "pinecone_dense_embeddings_general",
                {
                    "method": "pinecone_dense_embeddings",
                    "model_name": model_name,
                    "input_type": input_type,
                    "truncate": truncate,
                    "dimension": dimension,
                    "input_count": len(inputs) if inputs else 0,
                },
            )
            # loggers["main"].error(
            #     f"Error dense embeddings in pinecone dense embeddings: {str(e)}"
            # )
            raise HTTPException(status_code=500, detail=str(e))

    def pinecone_sparse_embeddings(self, inputs):
        try:
            pass
            # sparse_vector = bm25.encode_documents(inputs)
            # return sparse_vector

        except Exception as e:
            # Note: This is a sync method, so we can't use async _log_error here
            # If this method becomes active, consider making it async or using sync logging
            # loggers["main"].error(f"Error creating sparse embeddings: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
