from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends

from backend.app.models.schemas.chat_schema import ChatRequest, ConversationState
from backend.app.services.streaming_chat_service import StreamingChatService
from backend.app.utils.logging_utils import get_logger

logger = get_logger("streaming_chat")


class StreamingChatUsecase:
    """
    Use case for handling streaming chat interactions.
    Coordinates between the controller and chat service.
    """

    def __init__(
        self,
        streaming_chat_service: StreamingChatService = Depends(),
    ):
        self.streaming_chat_service = streaming_chat_service

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """
        Execute streaming chat use case.
        
        Args:
            request: Chat request with user message and configuration
            
        Yields:
            SSE formatted stream events
        """
        try:
            logger.info(f"Starting streaming chat - conversation_id: {request.conversation_id or 'new'}")
            
            # Validate request
            if not request.message or not request.message.strip():
                yield f'data: {{"type": "error", "data": {{"error": "Message cannot be empty"}}}}\n\n'
                return

            # Stream chat response
            async for event in self.streaming_chat_service.stream_chat(
                message=request.message,
                conversation_id=request.conversation_id,
                max_tokens=request.max_tokens or 4096,
                temperature=request.temperature or 0.0,
                system_prompt=request.system_prompt,
                include_tools=request.include_tools if request.include_tools is not None else True,
            ):
                yield event

            logger.info(f"Streaming chat completed - conversation_id: {request.conversation_id or 'new'}")

        except Exception as e:
            error_msg = f"Streaming chat use case failed: {str(e)}"
            logger.error(error_msg)
            yield f'data: {{"type": "error", "data": {{"error": "{error_msg}"}}}}\n\n'

    async def get_conversation(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Get conversation history by ID.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            Conversation state or None if not found
        """
        try:
            return await self.streaming_chat_service.get_conversation(conversation_id)
        except Exception as e:
            logger.error(f"Failed to get conversation {conversation_id}: {str(e)}")
            return None

    async def clear_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        Clear conversation history.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            Success status and message
        """
        try:
            success = await self.streaming_chat_service.clear_conversation(conversation_id)
            
            if success:
                return {
                    "success": True,
                    "message": f"Conversation {conversation_id} cleared successfully",
                    "conversation_id": conversation_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Conversation {conversation_id} not found",
                    "conversation_id": conversation_id
                }

        except Exception as e:
            error_msg = f"Failed to clear conversation {conversation_id}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "conversation_id": conversation_id
            }

    async def list_conversations(self) -> Dict[str, Any]:
        """
        List all active conversations.
        
        Returns:
            List of conversation IDs
        """
        try:
            conversation_ids = await self.streaming_chat_service.list_conversations()
            
            return {
                "success": True,
                "conversations": conversation_ids,
                "count": len(conversation_ids)
            }

        except Exception as e:
            error_msg = f"Failed to list conversations: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "conversations": [],
                "count": 0
            }

    async def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get conversation summary information.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            Conversation summary data
        """
        try:
            conversation = await self.streaming_chat_service.get_conversation(conversation_id)
            
            if not conversation:
                return {
                    "success": False,
                    "message": f"Conversation {conversation_id} not found",
                    "conversation_id": conversation_id
                }

            # Calculate summary statistics
            total_messages = len(conversation.messages)
            user_messages = len([msg for msg in conversation.messages if msg.role == "user"])
            assistant_messages = len([msg for msg in conversation.messages if msg.role == "assistant"])
            tool_messages = len([msg for msg in conversation.messages if msg.role == "tool"])
            
            # Count tool calls
            total_tool_calls = 0
            for msg in conversation.messages:
                if msg.tool_calls:
                    total_tool_calls += len(msg.tool_calls)

            return {
                "success": True,
                "conversation_id": conversation_id,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
                "statistics": {
                    "total_messages": total_messages,
                    "user_messages": user_messages,
                    "assistant_messages": assistant_messages,
                    "tool_messages": tool_messages,
                    "total_tool_calls": total_tool_calls
                },
                "metadata": conversation.metadata
            }

        except Exception as e:
            error_msg = f"Failed to get conversation summary for {conversation_id}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "conversation_id": conversation_id
            }
