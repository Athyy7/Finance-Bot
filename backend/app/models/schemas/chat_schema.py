from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Individual chat message schema"""
    role: str = Field(..., description="Message role: user, assistant, tool")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="Message content")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls in this message")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID if this is a tool result")


class ChatRequest(BaseModel):
    """Chat request schema for streaming agentic chatbot"""
    message: str = Field(..., description="User message content")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for maintaining context")
    max_tokens: Optional[int] = Field(4096, description="Maximum tokens for response")
    temperature: Optional[float] = Field(0.0, description="Temperature for response generation")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt override")
    include_tools: Optional[bool] = Field(True, description="Whether to include tool calling capabilities")


class StreamEvent(BaseModel):
    """Stream event schema for SSE"""
    type: str = Field(..., description="Event type")
    data: Dict[str, Any] = Field(..., description="Event data")


class ChatResponse(BaseModel):
    """Non-streaming chat response schema (for reference)"""
    success: bool = Field(..., description="Whether the chat was successful")
    conversation_id: str = Field(..., description="Conversation ID")
    message: str = Field(..., description="Assistant response message")
    tool_calls_used: int = Field(0, description="Number of tool calls executed")
    total_tokens: Optional[int] = Field(None, description="Total tokens used")
    error: Optional[str] = Field(None, description="Error message if any")


class ConversationState(BaseModel):
    """Conversation state schema for managing chat history"""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    messages: List[ChatMessage] = Field(default_factory=list, description="Chat message history")
    created_at: str = Field(..., description="Conversation creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ToolCall(BaseModel):
    """Tool call schema for agent interactions"""
    id: str = Field(..., description="Unique tool call identifier")
    name: str = Field(..., description="Tool name")
    input: Dict[str, Any] = Field(..., description="Tool input parameters")


class ToolResult(BaseModel):
    """Tool result schema for agent interactions"""
    tool_call_id: str = Field(..., description="Associated tool call ID")
    result: Any = Field(..., description="Tool execution result")
    success: bool = Field(..., description="Whether tool execution was successful")
    error: Optional[str] = Field(None, description="Error message if tool failed")