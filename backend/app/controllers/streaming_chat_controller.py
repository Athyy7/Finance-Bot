from fastapi import Depends, status
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any

from ..models.schemas.chat_schema import ChatRequest, ConversationState
from backend.app.usecases.streaming_chat_usecase import StreamingChatUsecase
from backend.app.utils.logging_utils import get_logger

logger = get_logger("streaming_chat_controller")


class StreamingChatController:
    """Controller for handling streaming chat interactions."""

    def __init__(
        self,
        streaming_chat_usecase: StreamingChatUsecase = Depends(),
    ):
        self.streaming_chat_usecase = streaming_chat_usecase

    async def stream_chat(self, request: ChatRequest) -> StreamingResponse:
        """
        Handle streaming chat request.
        
        Args:
            request: Chat request with user message and configuration
            
        Returns:
            StreamingResponse with SSE events
        """
        try:
            print(request)
            logger.info(f"Received streaming chat request - conversation_id: {request.conversation_id or 'new'}")

            # Create streaming generator with proper SSE format and anti-buffering
            async def generate_stream():
                try:
                    # Send immediate ping to establish connection
                    yield f'data: {{"type": "connection_test", "data": {{"message": "stream_connected"}}}}\n\n'
                    
                    async for event in self.streaming_chat_usecase.stream_chat(request):
                        # Ensure event ends with double newline for SSE format
                        if not event.endswith('\n\n'):
                            event += '\n\n'
                        
                        # Add explicit flush markers to fight buffering
                        yield event
                        
                        # Send periodic ping to keep connection alive and prevent buffering
                        # if "text_delta" in event:
                        #     yield f': keep-alive\n\n'  # SSE comment for anti-buffering
                            
                except Exception as e:
                    # Send error event if streaming fails
                    error_event = f'data: {{"type": "error", "data": {{"error": "{str(e)}"}}}}\n\n'
                    yield error_event

            # Return streaming response with proper SSE headers
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",  # Correct SSE media type
                headers={
                    # Cache control headers
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    
                    # Connection headers  
                    "Connection": "keep-alive",
                    
                    # Anti-buffering headers for various proxies/servers
                    "X-Accel-Buffering": "no",      # Disable nginx buffering
                    "X-Nginx-Buffering": "no",      # Alternative nginx header
                    "Proxy-Buffering": "off",       # Disable proxy buffering
                    "X-Apache-Compress": "off",     # Disable Apache compression
                    "X-Content-Type-Options": "nosniff", # Prevent MIME sniffing
                    
                    # CORS headers
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    
                    # Additional streaming headers
                    "Transfer-Encoding": "chunked",  # Force chunked encoding
                }
            )

        except Exception as e:
            error_msg = f"Streaming chat controller failed: {str(e)}"
            logger.error(error_msg)

            return JSONResponse(
                content={
                    "success": False,
                    "message": "Failed to start streaming chat",
                    "error": error_msg,
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_conversation(self, conversation_id: str) -> JSONResponse:
        """
        Get conversation history by ID.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            JSON response with conversation data
        """
        try:
            conversation = await self.streaming_chat_usecase.get_conversation(conversation_id)
            
            if conversation:
                return JSONResponse(
                    content={
                        "success": True,
                        "conversation": conversation.model_dump(),
                        "message": "Conversation retrieved successfully"
                    },
                    status_code=status.HTTP_200_OK
                )
            else:
                return JSONResponse(
                    content={
                        "success": False,
                        "message": f"Conversation {conversation_id} not found",
                        "conversation": None
                    },
                    status_code=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            error_msg = f"Failed to get conversation {conversation_id}: {str(e)}"
            logger.error(error_msg)

            return JSONResponse(
                content={
                    "success": False,
                    "message": "Failed to retrieve conversation",
                    "error": error_msg,
                    "conversation": None
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def clear_conversation(self, conversation_id: str) -> JSONResponse:
        """
        Clear conversation history.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            JSON response with operation status
        """
        try:
            result = await self.streaming_chat_usecase.clear_conversation(conversation_id)
            
            if result["success"]:
                return JSONResponse(
                    content=result,
                    status_code=status.HTTP_200_OK
                )
            else:
                return JSONResponse(
                    content=result,
                    status_code=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            error_msg = f"Failed to clear conversation {conversation_id}: {str(e)}"
            logger.error(error_msg)

            return JSONResponse(
                content={
                    "success": False,
                    "message": "Failed to clear conversation",
                    "error": error_msg,
                    "conversation_id": conversation_id
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def list_conversations(self) -> JSONResponse:
        """
        List all active conversations.
        
        Returns:
            JSON response with list of conversation IDs
        """
        try:
            result = await self.streaming_chat_usecase.list_conversations()
            
            return JSONResponse(
                content=result,
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            error_msg = f"Failed to list conversations: {str(e)}"
            logger.error(error_msg)

            return JSONResponse(
                content={
                    "success": False,
                    "message": "Failed to list conversations",
                    "error": error_msg,
                    "conversations": [],
                    "count": 0
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_conversation_summary(self, conversation_id: str) -> JSONResponse:
        """
        Get conversation summary information.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            JSON response with conversation summary
        """
        try:
            result = await self.streaming_chat_usecase.get_conversation_summary(conversation_id)
            
            if result["success"]:
                return JSONResponse(
                    content=result,
                    status_code=status.HTTP_200_OK
                )
            else:
                return JSONResponse(
                    content=result,
                    status_code=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            error_msg = f"Failed to get conversation summary for {conversation_id}: {str(e)}"
            logger.error(error_msg)

            return JSONResponse(
                content={
                    "success": False,
                    "message": "Failed to get conversation summary",
                    "error": error_msg,
                    "conversation_id": conversation_id
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
