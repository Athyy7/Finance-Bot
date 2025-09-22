import asyncio
import time
from datetime import datetime
from typing import Any, Dict

import httpx
from fastapi import Depends, HTTPException
from pinecone import Pinecone

from backend.app.config.settings import settings
from backend.app.repositories.error_repository import ErrorRepo

# from backend.app.utils.logging_utils import loggers


class PineconeService:
    def __init__(self, error_repo: ErrorRepo = Depends(ErrorRepo)):
        self.pinecone_api_key = settings.PINECONE_API_KEY
        self.api_version = settings.PINECONE_API_VERSION
        self.index_url = settings.PINECONE_CREATE_INDEX_URL
        self.dense_embed_url = settings.PINECONE_EMBED_URL
        self.upsert_url = settings.PINECONE_UPSERT_URL
        self.query_url = settings.PINECONE_QUERY_URL
        self.delete_url = "https://{}/vectors/delete"
        self.list_index_url = settings.PINECONE_LIST_INDEXES_URL
        self.semaphore = asyncio.Semaphore(settings.INDEXING_SEMAPHORE_VALUE)
        self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.error_repo = error_repo
        self.timeout = httpx.Timeout(
            connect=60.0,  # Time to establish a connection
            read=120.0,  # Time to read the response
            write=120.0,  # Time to send data
            pool=60.0,  # Time to wait for a connection from the pool
        )

    async def _log_error(self, error: Exception, operation: str, context: Dict[str, Any] = None):
        """Log error to database with proper context"""
        try:
            await self.error_repo.log_error(
                error=error,
                additional_context={
                    "file": "pinecone_service.py",
                    "operation": operation,
                    **(context or {})
                }
            )
        except Exception:
            # Don't raise here to avoid cascading failures
            pass

    async def list_pinecone_indexes(self):
        url = self.list_index_url

        headers = {
            "Api-Key": self.pinecone_api_key,
            "X-Pinecone-API-Version": self.api_version,
        }

        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            # loggers["main"].error(
            #     f"Error in listing pinecone indexes HTTPStatusError : {e.response.text} - {str(e)}"
            # )
            await self._log_error(e, "list_pinecone_indexes", {
                "method": "list_pinecone_indexes",
                "url": url,
                "status_code": e.response.status_code,
                "response_text": e.response.text if hasattr(e.response, 'text') else None
            })
            raise HTTPException(
                status_code=400,
                detail=f"Error in listing pinecone indexes HTTPStatusError: {e.response.text} - {str(e)}",
            )
        except Exception as e:
            await self._log_error(e, "list_pinecone_indexes", {
                "method": "list_pinecone_indexes",
                "url": url
            })
            # loggers["main"].error(f"Error in pinecone list indexes: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error in pinecone list indexes: {str(e)}",
            )

    async def create_index(
        self, index_name: str, dimension: int, metric: str
    ) -> Dict[str, Any]:
        print(
            f"Creating index {index_name} with dimension {dimension} and metric {metric}"
        )
        if self.pc.has_index(index_name) == False:
            index_data = {
                "name": index_name,
                "dimension": dimension,
                "metric": metric,
                "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
            }

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Api-Key": self.pinecone_api_key,
                "X-Pinecone-API-Version": self.api_version,
            }

            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.post(
                        self.index_url, headers=headers, json=index_data
                    )
                    response.raise_for_status()

                    retry_count = 0
                    max_retries = 30
                    while retry_count < max_retries:
                        status = (
                            self.pc.describe_index(index_name)
                            .get("status")
                            .get("state")
                        )
                        # loggers["main"].info(f"Index status: {status}")

                        if status == "Ready":
                            # loggers["main"].info(f"Index {index_name} is ready")
                            break

                        retry_count += 1
                        time.sleep(2)

                    if retry_count > max_retries:
                        timeout_error = Exception("Index creation timed out")
                        await self._log_error(timeout_error, "create_index_timeout", {
                            "method": "create_index",
                            "index_name": index_name,
                            "dimension": dimension,
                            "metric": metric,
                            "retry_count": retry_count,
                            "max_retries": max_retries
                        })
                        raise HTTPException(
                            status_code=500, detail="Index creation timed out"
                        )

                    # loggers["main"].info("Index Created")
                    return response.json()

            except httpx.HTTPStatusError as e:
                await self._log_error(e, "create_index_http_status", {
                    "method": "create_index",
                    "index_name": index_name,
                    "dimension": dimension,
                    "metric": metric,
                    "url": self.index_url,
                    "status_code": e.response.status_code,
                    "response_text": e.response.text if hasattr(e.response, 'text') else None
                })

                # loggers["main"].error(
                #     f"Error creating index HTTPStatusError: {e.response.text} - {str(e)}"
                # )
                raise HTTPException(
                    status_code=400,
                    detail=f"Error creating index HTTPStatusError: {e.response.text} - {str(e)}",
                )
            except Exception as e:
                await self._log_error(e, "create_index_general", {
                    "method": "create_index",
                    "index_name": index_name,
                    "dimension": dimension,
                    "metric": metric
                })
                # loggers["main"].error(f"Error creating index: {str(e)}")
                raise HTTPException(
                    status_code=500, detail=f"Error creating index: {str(e)}"
                )

        else:
            # loggers["main"].info("index already created")
            return {"host": self.pc.describe_index(index_name).get("host")}

    async def upsert_format(
        self, chunks: list, vector_embeddings: list  # , sparse_embeddings: list
    ):
        results = []
        for i in range(len(chunks)):
            metadata = {
                key: value for key, value in chunks[i].items() if key != "_id"
            }

            metadata["created_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            result = {
                "id": chunks[i]["_id"],
                "values": vector_embeddings[i],
                "metadata": metadata,
                # "sparse_values": {
                #     "indices": sparse_embeddings[i]["indices"],
                #     "values": sparse_embeddings[i]["values"],
                # },
            }
            results.append(result)
        return results

    async def upsert_vectors(self, index_host, input, namespace):
        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json",
            "X-Pinecone-API-Version": self.api_version,
        }

        url = self.upsert_url.format(index_host)

        payload = {"vectors": input, "namespace": namespace}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                response = await client.post(
                    url=url, headers=headers, json=payload
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            # loggers["main"].error(
            #     f"Error in upsert vectors http status error : {str(e)} - {e.response.text}"
            # )
            await self._log_error(e, "upsert_vectors_http_status", {
                "method": "upsert_vectors",
                "index_host": index_host,
                "namespace": namespace,
                "url": url,
                "status_code": e.response.status_code,
                "response_text": e.response.text if hasattr(e.response, 'text') else None,
                "vector_count": len(input) if input else 0
            })
            raise HTTPException(
                status_code=400,
                detail=f"Error in upsert vectors http status error : {str(e)} - {e.response.text}",
            )

        except httpx.HTTPError as e:
            await self._log_error(e, "upsert_vectors_http_error", {
                "method": "upsert_vectors",
                "index_host": index_host,
                "namespace": namespace,
                "url": url,
                "vector_count": len(input) if input else 0
            })
            # loggers["main"].error(
            #     f"Error in upsert vectors http error : {str(e)}"
            # )
            raise HTTPException(
                status_code=400,
                detail=f"Error in upsert vectors http error : {str(e)}",
            )

        except Exception as e:
            await self._log_error(e, "upsert_vectors_general", {
                "method": "upsert_vectors",
                "index_host": index_host,
                "namespace": namespace,
                "url": url,
                "vector_count": len(input) if input else 0
            })
            # loggers["main"].error(f"Error in upsert vectors : {str(e)} ")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_vectors(self, index_host: str, namespace: str, ids: list):
        """
        Delete vectors from Pinecone index by their IDs
        
        Args:
            index_host (str): The host URL for the Pinecone index
            namespace (str): The namespace to delete vectors from
            ids (list): List of vector IDs to delete
            
        Returns:
            dict: Response from Pinecone delete operation
            
        Raises:
            HTTPException: If the delete operation fails
        """
        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json",
            "X-Pinecone-API-Version": self.api_version,
        }

        url = self.delete_url.format(index_host)
        
        payload = {
            "ids": ids,
            "namespace": namespace
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                response = await client.post(
                    url=url, headers=headers, json=payload
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            await self._log_error(e, "delete_vectors_http_status", {
                "method": "delete_vectors",
                "index_host": index_host,
                "namespace": namespace,
                "url": url,
                "status_code": e.response.status_code,
                "response_text": e.response.text if hasattr(e.response, 'text') else None,
                "ids_count": len(ids) if ids else 0,
                "ids": ids[:10] if ids else []  # Log first 10 IDs for debugging
            })
            # loggers["main"].error(
            #     f"Error in delete vectors http status error : {str(e)} - {e.response.text}"
            # )
            raise HTTPException(
                status_code=400,
                detail=f"Error in delete vectors http status error : {str(e)} - {e.response.text}",
            )

        except httpx.HTTPError as e:
            await self._log_error(e, "delete_vectors_http_error", {
                "method": "delete_vectors",
                "index_host": index_host,
                "namespace": namespace,
                "url": url,
                "ids_count": len(ids) if ids else 0,
                "ids": ids[:10] if ids else []
            })
            # loggers["main"].error(
            #     f"Error in delete vectors http error : {str(e)}"
            # )
            raise HTTPException(
                status_code=400,
                detail=f"Error in delete vectors http error : {str(e)}",
            )

        except Exception as e:
            await self._log_error(e, "delete_vectors_general", {
                "method": "delete_vectors",
                "index_host": index_host,
                "namespace": namespace,
                "url": url,
                "ids_count": len(ids) if ids else 0,
                "ids": ids[:10] if ids else []
            })
            # loggers["main"].error(f"Error in delete vectors : {str(e)} ")
            raise HTTPException(status_code=500, detail=f"Error in delete vectors: {str(e)}")

    def hybrid_scale(self, dense, sparse, alpha: float):

        if alpha < 0 or alpha > 1:
            raise ValueError("Alpha must be between 0 and 1")
        # scale sparse and dense vectors to create hybrid search vecs
        hsparse = {
            "indices": sparse["indices"],
            "values": [v * (1 - alpha) for v in sparse["values"]],
        }
        hdense = [v * alpha for v in dense]
        return hdense, hsparse


    async def pinecone_hybrid_query(
        self,
        index_host,
        namespace,
        top_k,
        alpha: int,
        query_vector_embeds: list,
        query_sparse_embeds: dict,
        include_metadata: bool,
        filter_dict: dict = None,
    ):

        if query_vector_embeds is None or query_sparse_embeds is None:
            time.sleep(2)

        headers = {
            "Api-Key": self.pinecone_api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Pinecone-API-Version": self.api_version,
        }

        hdense, hsparse = self.hybrid_scale(
            query_vector_embeds, query_sparse_embeds, alpha
        )

        payload = {
            "includeValues": False,
            "includeMetadata": include_metadata,
            "vector": hdense,
            "sparseVector": {
                "indices": hsparse.get("indices"),
                "values": hsparse.get("values"),
            },
            "topK": top_k,
            "namespace": namespace,
        }

        if filter_dict:
            payload["filter"] = filter_dict

        url = self.query_url.format(index_host)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=False
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
                # loggers["pinecone"].info(
                #     f"pinecone hybrid query read units: {response.json()['usage']}"
                # )
                return response.json()

        except httpx.HTTPStatusError as e:
            # loggers["main"].error(
            #     f"HTTP status error in hybrid query: {e.response.text} - {str(e)}"
            # )
            await self._log_error(e, "hybrid_query_http_status", {
                "method": "pinecone_hybrid_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "alpha": alpha,
                "url": url,
                "status_code": e.response.status_code,
                "response_text": e.response.text if hasattr(e.response, 'text') else None
            })
            raise HTTPException(
                status_code=400,
                detail=f"HTTP status error in hybrid query: {e.response.text} - {str(e)}",
            )

        except httpx.HTTPError as e:

            # loggers["main"].error(f"HTTP error in hybrid query:  {str(e)}")
            await self._log_error(e, "hybrid_query_http_error", {
                "method": "pinecone_hybrid_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "alpha": alpha,
                "url": url
            })
            raise HTTPException(
                status_code=400, detail=f"HTTP error in hybrid query: {str(e)}"
            )

        except Exception as e:
            # loggers["main"].error(f"Error performing hybrid query: {str(e)}")
            await self._log_error(e, "hybrid_query_general", {
                "method": "pinecone_hybrid_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "alpha": alpha,
                "url": url
            })
            raise HTTPException(status_code=500, detail=str(e))

   
    async def pinecone_query(
        self,
        index_host: str,
        namespace: str,
        top_k: int,
        vector: list,
        include_metadata: bool,
        filter_dict: dict = None,
    ):

        headers = {
            "Api-Key": self.pinecone_api_key,
            "Content-Type": "application/json",
            "X-Pinecone-API-Version": self.api_version,
        }

        payload = {
            "namespace": namespace,
            "vector": vector,
            "filter": filter_dict,
            "topK": top_k,
            "includeValues": False,
            "includeMetadata": include_metadata,
        }

        if filter_dict:
            payload["filter"] = filter_dict

        url = self.query_url.format(index_host)

        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(url, headers=headers, json=payload)
                # loggers["pinecone"].info(
                #     f"pinecone Normal query read units: {response.json()['usage']}"
                # )
                return response.json()

        except httpx.HTTPStatusError as e:
            # loggers["main"].error(
            #     f"HTTP status error in pinecone query: {e.response.text} - {str(e)}"
            # )
            await self._log_error(e, "pinecone_query_http_status", {
                "method": "pinecone_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "url": url,
                "status_code": e.response.status_code,
                "response_text": e.response.text if hasattr(e.response, 'text') else None,
                "vector_length": len(vector) if vector else 0
            })
            raise HTTPException(
                status_code=400,
                detail=f"HTTP status error in pinecone query: {e.response.text} - {str(e)}",
            )

        except httpx.RequestError as e:
            # loggers["main"].error(f"Request error in pinecone query: {str(e)}")
            await self._log_error(e, "pinecone_query_request_error", {
                "method": "pinecone_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "url": url,
                "vector_length": len(vector) if vector else 0
            })
            raise HTTPException(
                status_code=400,
                detail=f"Request error in pinecone query: {str(e)}",
            )

        except httpx.HTTPError as e:
            # loggers["main"].error(f"HTTP error in pinecone query: {str(e)}")
            await self._log_error(e, "pinecone_query_http_error", {
                "method": "pinecone_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "url": url,
                "vector_length": len(vector) if vector else 0
            })
            raise HTTPException(
                status_code=400,
                detail=f"HTTP error in pinecone query: {str(e)}",
            )

        except Exception as e:
            # loggers["main"].error(f"Error in pinecone query : {str(e)}")
            await self._log_error(e, "pinecone_query_general", {
                "method": "pinecone_query",
                "index_host": index_host,
                "namespace": namespace,
                "top_k": top_k,
                "url": url,
                "vector_length": len(vector) if vector else 0
            })
            raise HTTPException(
                status_code=500, detail=f"Error in pinecone query : {str(e)}"
            )

    async def get_index_details(self, index_name: str):
        url = f"https://api.pinecone.io/indexes/{index_name}"

        headers = {
            "Api-Key": self.pinecone_api_key,
            "X-Pinecone-API-Version": self.api_version,
        }

        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                index_details = response.json()
                return index_details

        except httpx.HTTPStatusError as e:
            # loggers["main"].error(
            #     f"Error getting index details HTTPStatusError: {e.response.text} - {str(e)}"
            # )
            await self._log_error(e, "get_index_details_http_status", {
                "method": "get_index_details",
                "index_name": index_name,
                "url": url,
                "status_code": e.response.status_code,
                "response_text": e.response.text if hasattr(e.response, 'text') else None
            })
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Error getting index details: {e.response.text}",
            )
        except Exception as e:
            # loggers["main"].error(f"Error retrieving index details: {str(e)}")
            await self._log_error(e, "get_index_details_general", {
                "method": "get_index_details",
                "index_name": index_name,
                "url": url
            })
            raise HTTPException(
                status_code=500,
                detail=f"Error retrieving index details: {str(e)}",
            )

    async def get_index_host(self, index_name: str) -> str:
        try:
            index_details = await self.get_index_details(index_name)
            if "host" not in index_details:
                host_not_found_error = Exception(f"Host not found in index details for {index_name}")
                await self._log_error(host_not_found_error, "get_index_host_no_host", {
                    "method": "get_index_host",
                    "index_name": index_name,
                    "index_details": index_details
                })
                raise HTTPException(
                    status_code=400,
                    detail=f"Host not found in index details for {index_name}",
                )
            return index_details["host"]
        except HTTPException:
            raise
        except Exception as e:
            # loggers["main"].error(
            #     f"Error extracting host from index details: {str(e)}"
            # )
            await self._log_error(e, "get_index_host_general", {
                "method": "get_index_host",
                "index_name": index_name
            })
            raise HTTPException(
                status_code=500,
                detail=f"Error extracting host from index details: {str(e)}",
            )
