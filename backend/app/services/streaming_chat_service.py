import json
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends

from backend.app.models.domain.error import Error
from backend.app.models.schemas.chat_schema import (
    ChatMessage, 
    ConversationState, 
    StreamEvent,
    ToolCall,
    ToolResult
)
from backend.app.models.schemas.llm_schema import LLMProvider
from backend.app.repositories.error_repository import ErrorRepo
from backend.app.services.anthropic_service import AnthropicService
from backend.app.tools.registry.tool_registry import ToolRegistry
from backend.app.utils.logging_utils import get_logger
from backend.app.prompts.financial_agent_prompt import SYSTEM_PROMPT

logger = get_logger("streaming_chat_service")

# Global conversation store (persistent across requests)
# In production, this should be Redis/Database
_global_conversations: Dict[str, ConversationState] = {}


class StreamingChatService:
    """
    Service for handling streaming agentic chat with tool calling capabilities.
    Manages conversation state and handles Anthropic streaming responses.
    """

    def __init__(
        self,
        anthropic_service: AnthropicService = Depends(),
        # tool_registry: ToolRegistry = Depends(),  # Create instance manually for now
        error_repo: ErrorRepo = Depends(),
    ):
        self.anthropic_service = anthropic_service
        self.tool_registry = ToolRegistry()  # Create instance manually
        self.error_repo = error_repo
        
        # Use global conversation store (persistent across requests)
        self.conversations = _global_conversations
        
        # Use the system prompt from the prompts module
        self.default_system_prompt = SYSTEM_PROMPT

    async def stream_chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
        include_tools: bool = True,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat response with tool calling support.
        
        Args:
            message: User message
            conversation_id: Optional conversation ID for context
            max_tokens: Maximum tokens for response
            temperature: Temperature for response generation
            system_prompt: Optional system prompt override
            include_tools: Whether to enable tool calling
            
        Yields:
            SSE formatted stream events
        """
        try:
            # Get or create conversation
            if conversation_id:
                conversation = self.conversations.get(conversation_id)
                if conversation:
                    logger.info(f"Found existing conversation {conversation_id} with {len(conversation.messages)} messages")
                else:
                    logger.info(f"Conversation {conversation_id} not found, creating new one")
                    conversation = self._create_conversation(conversation_id)
            else:
                conversation_id = str(uuid.uuid4())
                logger.info(f"No conversation_id provided, creating new conversation: {conversation_id}")
                conversation = self._create_conversation(conversation_id)

            # Debug: Show current conversations in memory
            logger.info(f"Total conversations in memory: {len(self.conversations)}")
            logger.info(f"Conversation IDs: {list(self.conversations.keys())}")

            # Add user message to conversation
            user_message = ChatMessage(role="user", content=message)
            conversation.messages.append(user_message)
            conversation.updated_at = datetime.utcnow().isoformat()
            
            logger.info(f"Added user message to conversation {conversation_id}. Total messages: {len(conversation.messages)}")

            # Prepare system prompt
            system = system_prompt or self.default_system_prompt
            
            # Get available tools
            tools = []
            if include_tools:
                tools = self.tool_registry.get_tools_for_provider(LLMProvider.ANTHROPIC)

            # Send initial connection event with conversation info
            initial_event = StreamEvent(
                type="stream_start",
                data={
                    "conversation_id": conversation.conversation_id,
                    "message_count": len(conversation.messages),
                    "is_new_conversation": len(conversation.messages) == 1
                }
            )
            yield f"data: {json.dumps(initial_event.model_dump())}\n\n"

            # Start streaming with tool calling loop
            logger.info(f"Starting tool calling loop for conversation: {conversation.conversation_id}")
            async for event in self._stream_with_tool_calling(
                conversation, system, tools, max_tokens, temperature
            ):
                yield event

        except Exception as e:
            error_msg = f"Streaming chat error: {str(e)}"
            print(f"[ERROR] Streaming chat error: {error_msg}")
            await self._log_error("streaming_chat_service", error_msg)
            
            error_event = StreamEvent(
                type="error",
                data={"error": error_msg, "conversation_id": conversation_id}
            )
            yield f"data: {json.dumps(error_event.model_dump())}\n\n"

    async def _stream_with_tool_calling(
        self,
        conversation: ConversationState,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        max_iterations: int = 1000,
    ) -> AsyncGenerator[str, None]:
        """
        Handle streaming with tool calling loop.
        
        Args:
            conversation: Conversation state
            system_prompt: System prompt
            tools: Available tools
            max_tokens: Maximum tokens
            temperature: Temperature
            max_iterations: Maximum tool calling iterations
            
        Yields:
            SSE formatted stream events
        """
        iteration_count = 0
        
        while iteration_count < max_iterations:
            iteration_count += 1
            
            # Prepare messages for Anthropic
            anthropic_messages = self._convert_messages_for_anthropic(conversation.messages)
            
            # Debug logging
            logger.info(f"Iteration {iteration_count}: {len(conversation.messages)} messages in conversation")
            logger.info(f"Last 3 messages: {[{'role': m.role, 'content_preview': str(m.content)[:100]} for m in conversation.messages[-3:]]}")
            
            # Track current assistant message parts
            current_text_content = ""
            current_tool_calls = []
            # Track tool input JSON accumulation
            tool_json_accumulator = {}
            
            # Stream from Anthropic with immediate yield testing
            logger.info(f"Starting Anthropic stream for iteration {iteration_count}")
            
            try:
                event_count = 0
                async for event in self.anthropic_service.anthropic_sdk_stream_call(
                    messages=anthropic_messages,
                    system_prompt=system_prompt,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    event_count += 1
                    logger.info(f"Received event #{event_count} from Anthropic: {getattr(event, 'type', 'unknown')}")
                    
                    # Handle different event types
                    if hasattr(event, 'type'):
                        event_type = event.type
                        
                        if event_type == "message_start":
                            # Send start event to frontend
                            start_event = StreamEvent(
                                type="message_start",
                                data={
                                    "conversation_id": conversation.conversation_id,
                                    "iteration": iteration_count
                                }
                            )
                            yield f"data: {json.dumps(start_event.model_dump())}\n\n"
                        
                        elif event_type == "content_block_start":
                            block = event.content_block
                            if block.type == "text":
                                # Text block started
                                logger.info(f"Text block started")
                            elif block.type == "tool_use":
                                # Tool use block started
                                logger.info(f"Tool use block started: {block.name} (id: {block.id})")
                                tool_call = ToolCall(
                                    id=block.id,
                                    name=block.name,
                                    input=getattr(block, 'input', {})  # Get input if available
                                )
                                current_tool_calls.append(tool_call)
                                # Initialize JSON accumulator for this tool
                                tool_json_accumulator[block.id] = ""
                                logger.info(f"Added tool call to current list: {tool_call.model_dump()}")
                        
                        elif event_type == "content_block_delta":
                            delta = event.delta
                            
                            if delta.type == "text_delta":
                                # Stream text delta to frontend
                                current_text_content += delta.text
                                text_event = StreamEvent(
                                    type="text_delta",
                                    data={
                                        "text": delta.text,
                                        "conversation_id": conversation.conversation_id
                                    }
                                )
                                yield f"data: {json.dumps(text_event.model_dump())}\n\n"
                            
                            elif delta.type == "input_json_delta":
                                # Accumulate tool input JSON properly
                                partial_json = getattr(delta, 'partial_json', '')
                                logger.info(f"Received input_json_delta: '{partial_json}'")
                                
                                if current_tool_calls:
                                    # Get the last tool call being built
                                    last_tool = current_tool_calls[-1]
                                    # Accumulate the partial JSON
                                    if last_tool.id in tool_json_accumulator:
                                        tool_json_accumulator[last_tool.id] += partial_json
                                        logger.info(f"Accumulated JSON for {last_tool.name}: '{tool_json_accumulator[last_tool.id]}'")
                        
                        elif event_type == "content_block_stop":
                            # Block completed - check if it's a tool_use block and parse JSON
                            block_index = getattr(event, 'index', None)
                            if block_index is not None and current_tool_calls:
                                # Check if we have accumulated JSON for any tool
                                for tool_call in current_tool_calls:
                                    if tool_call.id in tool_json_accumulator:
                                        accumulated_json = tool_json_accumulator[tool_call.id].strip()
                                        if accumulated_json:
                                            try:
                                                # Parse the complete JSON
                                                parsed_input = json.loads(accumulated_json)
                                                # Update the tool call input
                                                tool_call.input = parsed_input
                                                logger.info(f"Successfully parsed tool input for {tool_call.name}: {parsed_input}")
                                            except json.JSONDecodeError as e:
                                                logger.error(f"Failed to parse JSON for tool {tool_call.name}: '{accumulated_json}' - Error: {e}")
                                            # Clear the accumulator
                                            del tool_json_accumulator[tool_call.id]
                        
                        elif event_type == "message_delta":
                            # Message metadata (like stop reason)
                            pass
                        
                        elif event_type == "message_stop":
                            # Message completed
                            break
                    
                    # Handle final message event (from anthropic service)
                    elif isinstance(event, dict) and event.get("type") == "anthropic_final_message":
                        final_data = event.get("data", {})
                        logger.info(f"Processing final message with content blocks")
                        
                        # Clear current tool calls and rebuild from final message to ensure complete inputs
                        current_tool_calls.clear()
                        
                        # Extract complete tool calls from final message
                        content_blocks = final_data.get("content", [])
                        for block in content_blocks:
                            if block.get("type") == "tool_use":
                                tool_input = block.get("input", {})
                                logger.info(f"Final message tool call: {block.get('name')} with input: {tool_input}")
                                
                                tool_call = ToolCall(
                                    id=block.get("id"),
                                    name=block.get("name"),
                                    input=tool_input
                                )
                                current_tool_calls.append(tool_call)

                # Save assistant message to conversation
                assistant_message_content = []
                
                if current_text_content.strip():
                    assistant_message_content.append({
                        "type": "text",
                        "text": current_text_content
                    })
                
                for tool_call in current_tool_calls:
                    assistant_message_content.append({
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.input
                    })

                assistant_message = ChatMessage(
                    role="assistant",
                    content=assistant_message_content,
                    tool_calls=[tc.model_dump() for tc in current_tool_calls] if current_tool_calls else None
                )
                conversation.messages.append(assistant_message)

                # If no tool calls, we're done
                if not current_tool_calls:
                    completion_event = StreamEvent(
                        type="message_complete",
                        data={
                            "conversation_id": conversation.conversation_id,
                            "iterations_used": iteration_count,
                            "total_messages": len(conversation.messages),
                            "note": "Use this conversation_id in your next request to continue the conversation"
                        }
                    )
                    yield f"data: {json.dumps(completion_event.model_dump())}\n\n"
                    break

                # Execute tool calls
                tool_results = []
                for tool_call in current_tool_calls:
                    tool_event = StreamEvent(
                        type="tool_call",
                        data={
                            "tool_name": tool_call.name,
                            "tool_id": tool_call.id,
                            "conversation_id": conversation.conversation_id
                        }
                    )
                    yield f"data: {json.dumps(tool_event.model_dump())}\n\n"

                    # Execute tool
                    logger.info(f"Executing tool {tool_call.name} with input: {tool_call.input}")
                    tool_result = await self._execute_tool(tool_call)
                    logger.info(f"Tool {tool_call.name} result: {tool_result.result}")
                    tool_results.append(tool_result)

                    # Stream tool result with actual content
                    tool_result_event = StreamEvent(
                        type="tool_result",
                        data={
                            "tool_name": tool_call.name,
                            "tool_id": tool_call.id,
                            "success": tool_result.success,
                            "result": tool_result.result,  # Include actual result
                            "conversation_id": conversation.conversation_id
                        }
                    )
                    yield f"data: {json.dumps(tool_result_event.model_dump())}\n\n"

                # Add tool results to conversation
                for tool_result in tool_results:
                    # Format tool result content properly for LLM
                    if isinstance(tool_result.result, dict):
                        # For structured results like calculator, use formatted_result if available
                        if 'formatted_result' in tool_result.result:
                            content = tool_result.result['formatted_result']
                        else:
                            content = json.dumps(tool_result.result, indent=2)
                    else:
                        content = str(tool_result.result)
                    
                    tool_message = ChatMessage(
                        role="tool",
                        content=content,
                        tool_call_id=tool_result.tool_call_id
                    )
                    conversation.messages.append(tool_message)
                    logger.info(f"Added tool result to conversation: {tool_call.name} -> {content[:200]}")

                # Continue to next iteration
                conversation.updated_at = datetime.utcnow().isoformat()

            except Exception as e:
                error_msg = f"Streaming iteration {iteration_count} failed: {str(e)}"
                await self._log_error("streaming_chat_service", error_msg)
                
                error_event = StreamEvent(
                    type="error",
                    data={
                        "error": error_msg,
                        "conversation_id": conversation.conversation_id,
                        "iteration": iteration_count
                    }
                )
                yield f"data: {json.dumps(error_event.model_dump())}\n\n"
                break

        # Max iterations reached
        if iteration_count >= max_iterations:
            max_iter_event = StreamEvent(
                type="max_iterations_reached",
                data={
                    "conversation_id": conversation.conversation_id,
                    "max_iterations": max_iterations,
                    "total_messages": len(conversation.messages),
                    "note": "Use this conversation_id in your next request to continue the conversation"
                }
            )
            yield f"data: {json.dumps(max_iter_event.model_dump())}\n\n"

    def _create_conversation(self, conversation_id: str) -> ConversationState:
        """Create a new conversation state."""
        conversation = ConversationState(
            conversation_id=conversation_id,
            messages=[],
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            metadata={}
        )
        self.conversations[conversation_id] = conversation
        return conversation

    def _convert_messages_for_anthropic(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Convert internal messages to Anthropic API format."""
        anthropic_messages = []
        
        for msg in messages:
            if msg.role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": str(msg.content)
                })
            elif msg.role == "assistant":
                anthropic_messages.append({
                    "role": "assistant", 
                    "content": msg.content
                })
            elif msg.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": str(msg.content)
                        }
                    ]
                })
        
        return anthropic_messages

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call."""
        try:
            # Get tool from registry
            tool_instance = self.tool_registry.get_tool(tool_call.name)
            if not tool_instance:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    result=f"Tool '{tool_call.name}' not found in registry",
                    success=False,
                    error=f"Tool '{tool_call.name}' not found"
                )

            # Execute tool
            result = await tool_instance.execute(tool_call.input)
            
            return ToolResult(
                tool_call_id=tool_call.id,
                result=result,
                success=True,
                error=None
            )

        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            await self._log_error("tool_execution", error_msg)
            
            return ToolResult(
                tool_call_id=tool_call.id,
                result=error_msg,
                success=False,
                error=str(e)
            )

    async def get_conversation(self, conversation_id: str) -> Optional[ConversationState]:
        """Get conversation by ID."""
        return self.conversations.get(conversation_id)

    async def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation."""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            return True
        return False

    async def list_conversations(self) -> List[str]:
        """List all conversation IDs."""
        return list(self.conversations.keys())

    async def _log_error(self, tool_name: str, error_message: str) -> None:
        """Log error to the error repository."""
        try:
            error_data = {
                "tool_name": tool_name,
                "error_message": error_message,
            }
            error = Error(**error_data)
            await self.error_repo.insert_error(error)
        except Exception:
            # Silent fail for error logging to prevent cascading failures
            logger.error(f"Failed to log error: {error_message}")
