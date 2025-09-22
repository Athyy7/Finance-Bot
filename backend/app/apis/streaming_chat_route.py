from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse, StreamingResponse

from backend.app.controllers.streaming_chat_controller import StreamingChatController
from ..controllers.streaming_chat_controller import StreamingChatController
from ..models.schemas.chat_schema import ChatRequest, ConversationState

from backend.app.utils.error_handler import handle_exceptions

router = APIRouter()


@router.post("/chat/stream")
@handle_exceptions
async def stream_chat(
    request: ChatRequest,
    controller: StreamingChatController = Depends(),
) -> StreamingResponse:
    """
    Stream chat endpoint for agentic chatbot.
    
    This endpoint accepts a user message and streams the response back,
    including tool calls and their results.
    
    Args:
        request: Chat request with user message and configuration
        
    Returns:
        Streaming response with SSE events
        
    Example:
        ```
        POST /api/chat/stream
        {
            "message": "What's the weather like today?",
            "conversation_id": "optional-conversation-id",
            "max_tokens": 4096,
            "temperature": 0.0,
            "include_tools": true
        }
        ```
        
    Stream events:
        - message_start: Chat iteration started
        - text_delta: Text content chunk
        - tool_call: Tool is being executed
        - tool_result: Tool execution completed
        - message_complete: Chat completed
        - error: Error occurred
    """
    return await controller.stream_chat(request)


@router.get("/chat/conversations/{conversation_id}")
@handle_exceptions
async def get_conversation(
    conversation_id: str = Path(..., description="Conversation ID"),
    controller: StreamingChatController = Depends(),
) -> JSONResponse:
    """
    Get conversation history by ID.
    
    Args:
        conversation_id: Unique conversation identifier
        
    Returns:
        JSON response with conversation data
    """
    return await controller.get_conversation(conversation_id)


@router.delete("/chat/conversations/{conversation_id}")
@handle_exceptions
async def clear_conversation(
    conversation_id: str = Path(..., description="Conversation ID"),
    controller: StreamingChatController = Depends(),
) -> JSONResponse:
    """
    Clear conversation history.
    
    Args:
        conversation_id: Unique conversation identifier
        
    Returns:
        JSON response with operation status
    """
    return await controller.clear_conversation(conversation_id)


@router.get("/chat/conversations")
@handle_exceptions
async def list_conversations(
    controller: StreamingChatController = Depends(),
) -> JSONResponse:
    """
    List all active conversations.
    
    Returns:
        JSON response with list of conversation IDs
    """
    return await controller.list_conversations()


@router.get("/chat/conversations/{conversation_id}/summary")
@handle_exceptions
async def get_conversation_summary(
    conversation_id: str = Path(..., description="Conversation ID"),
    controller: StreamingChatController = Depends(),
) -> JSONResponse:
    """
    Get conversation summary information.
    
    Args:
        conversation_id: Unique conversation identifier
        
    Returns:
        JSON response with conversation statistics and metadata
    """
    return await controller.get_conversation_summary(conversation_id)


@router.get("/chat/health")
@handle_exceptions
async def health_check() -> JSONResponse:
    """
    Health check endpoint for the chat service.
    
    Returns:
        JSON response with service health status
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "streaming_chat",
            "message": "Streaming chat service is running"
        }
    )
