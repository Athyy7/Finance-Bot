# Streaming Agentic Chatbot API

This document provides examples and usage instructions for the streaming agentic chatbot API.

## Overview

The Finance Bot provides a streaming chat API with tool calling capabilities. The bot can:
- Stream responses in real-time
- Execute tools (e.g., calculator, financial analysis)
- Maintain conversation context
- Handle multiple concurrent conversations

## API Endpoints

### 1. Stream Chat
**Endpoint:** `POST /api/chat/stream`

**Description:** Start a streaming chat conversation

**Request Body:**
```json
{
  "message": "What is 15% of $1000?",
  "conversation_id": "optional-uuid-for-continuing-conversation",
  "max_tokens": 4096,
  "temperature": 0.0,
  "include_tools": true,
  "system_prompt": "Optional custom system prompt"
}
```

**⚠️ IMPORTANT - Conversation Memory:**
- **First message**: Don't include `conversation_id` 
- **Subsequent messages**: Use the `conversation_id` from the `message_complete` event
- If you don't provide `conversation_id`, each message starts a new conversation

**Response:** Server-Sent Events (SSE) stream

**Example Stream Events:**
```
data: {"type": "message_start", "data": {"conversation_id": "abc-123", "iteration": 1}}

data: {"type": "text_delta", "data": {"text": "I'll help you calculate 15% of $1000.", "conversation_id": "abc-123"}}

data: {"type": "tool_call", "data": {"tool_name": "calculator", "tool_id": "tool_xyz", "conversation_id": "abc-123"}}

data: {"type": "tool_result", "data": {"tool_name": "calculator", "tool_id": "tool_xyz", "success": true, "conversation_id": "abc-123"}}

data: {"type": "text_delta", "data": {"text": " The result is $150.", "conversation_id": "abc-123"}}

data: {"type": "message_complete", "data": {"conversation_id": "abc-123", "iterations_used": 1}}
```

### 2. Get Conversation
**Endpoint:** `GET /api/chat/conversations/{conversation_id}`

**Description:** Retrieve conversation history

**Response:**
```json
{
  "success": true,
  "conversation": {
    "conversation_id": "abc-123",
    "messages": [
      {
        "role": "user",
        "content": "What is 15% of $1000?",
        "tool_calls": null,
        "tool_call_id": null
      },
      {
        "role": "assistant",
        "content": [
          {"type": "text", "text": "I'll help you calculate 15% of $1000."},
          {"type": "tool_use", "id": "tool_xyz", "name": "calculator", "input": {"expression": "1000 * 0.15"}}
        ],
        "tool_calls": [{"id": "tool_xyz", "name": "calculator", "input": {"expression": "1000 * 0.15"}}],
        "tool_call_id": null
      },
      {
        "role": "tool",
        "content": "{\"success\": true, \"result\": 150.0, \"formatted_result\": \"1000 * 0.15 = 150.0\"}",
        "tool_calls": null,
        "tool_call_id": "tool_xyz"
      }
    ],
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-01T10:01:00Z",
    "metadata": {}
  }
}
```

### 3. List Conversations
**Endpoint:** `GET /api/chat/conversations`

**Response:**
```json
{
  "success": true,
  "conversations": ["abc-123", "def-456", "ghi-789"],
  "count": 3
}
```

### 4. Clear Conversation
**Endpoint:** `DELETE /api/chat/conversations/{conversation_id}`

**Response:**
```json
{
  "success": true,
  "message": "Conversation abc-123 cleared successfully",
  "conversation_id": "abc-123"
}
```

### 5. Conversation Summary
**Endpoint:** `GET /api/chat/conversations/{conversation_id}/summary`

**Response:**
```json
{
  "success": true,
  "conversation_id": "abc-123",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:01:00Z",
  "statistics": {
    "total_messages": 5,
    "user_messages": 2,
    "assistant_messages": 2,
    "tool_messages": 1,
    "total_tool_calls": 1
  },
  "metadata": {}
}
```

## Frontend Integration Examples

### JavaScript/TypeScript (Browser)

```javascript
// Global variable to store current conversation ID
let currentConversationId = null;

// Function to handle streaming chat with proper conversation memory
async function streamChat(message, useConversation = true) {
  const requestBody = {
    message: message,
    max_tokens: 4096,
    temperature: 0.0,
    include_tools: true
  };

  // Include conversation_id if we have one and want to continue conversation
  if (useConversation && currentConversationId) {
    requestBody.conversation_id = currentConversationId;
  }

  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody)
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        handleStreamEvent(data);
      }
    }
  }
}

function handleStreamEvent(event) {
  switch (event.type) {
    case 'stream_start':
      // Capture conversation_id for future messages
      currentConversationId = event.data.conversation_id;
      console.log('Conversation ID:', currentConversationId);
      console.log('Message count:', event.data.message_count);
      break;
      
    case 'text_delta':
      appendToChat(event.data.text);
      break;
      
    case 'tool_call':
      showToolExecution(event.data.tool_name);
      break;
      
    case 'tool_result':
      showToolResult(event.data.success, event.data.result);
      break;
      
    case 'message_complete':
      console.log('Chat completed. Total messages:', event.data.total_messages);
      console.log('Use conversation_id for next message:', event.data.conversation_id);
      break;
      
    case 'error':
      console.error('Chat error:', event.data.error);
      break;
  }
}

function appendToChat(text) {
  const chatContainer = document.getElementById('chat');
  chatContainer.textContent += text;
}

function showToolExecution(toolName) {
  console.log(`🔧 Executing tool: ${toolName}`);
}

function showToolResult(success, result) {
  console.log(`Tool result: ${success ? '✅' : '❌'}`, result);
}

// Example usage - conversation memory
async function chatExample() {
  // First message (new conversation)
  await streamChat("Hello, I'm planning to invest $10,000");
  
  // Second message (continues same conversation)  
  await streamChat("What's 15% of that amount?");
  
  // Third message (still same conversation)
  await streamChat("What was my original investment amount?");
  
  // Start new conversation
  currentConversationId = null; // Reset
  await streamChat("Hi, different topic now");
}

// Simple usage
streamChat("Calculate 15% of $2500");
```

### Python Client

```python
import requests
import json

class FinanceBotClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.conversation_id = None
    
    def stream_chat(self, message, start_new_conversation=False):
        """Send a message and handle streaming response with conversation memory."""
        url = f"{self.base_url}/api/v1/chat/stream"
        
        data = {
            "message": message,
            "max_tokens": 4096,
            "temperature": 0.0,
            "include_tools": True
        }
        
        # Include conversation_id unless starting new conversation
        if not start_new_conversation and self.conversation_id:
            data["conversation_id"] = self.conversation_id
        
        response = requests.post(url, json=data, stream=True)
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    event = json.loads(line[6:])
                    self.handle_stream_event(event)
    
    def handle_stream_event(self, event):
        event_type = event['type']
        data = event['data']
        
        if event_type == 'stream_start':
            # Capture conversation_id from response
            self.conversation_id = data['conversation_id']
            print(f"💬 Conversation: {self.conversation_id} ({data['message_count']} messages)")
            
        elif event_type == 'text_delta':
            print(data['text'], end='', flush=True)
            
        elif event_type == 'tool_call':
            print(f"\n🔧 Executing {data['tool_name']}...", flush=True)
            
        elif event_type == 'tool_result':
            success = data['success']
            result = data.get('result', {})
            if success and isinstance(result, dict) and 'formatted_result' in result:
                print(f"✅ {result['formatted_result']}")
            else:
                print(f"{'✅' if success else '❌'} Tool completed")
                
        elif event_type == 'message_complete':
            print(f"\n📊 Total messages: {data['total_messages']}")
            
        elif event_type == 'error':
            print(f"\n❌ Error: {data['error']}")
    
    def start_new_conversation(self):
        """Start a fresh conversation."""
        self.conversation_id = None
        print("🔄 Starting new conversation")

# Example usage with conversation memory
bot = FinanceBotClient()

print("=== Conversation 1 ===")
bot.stream_chat("Hello, I want to invest $50,000")
bot.stream_chat("What's 10% of that amount?") 
bot.stream_chat("What was my original investment amount?")

print("\n=== New Conversation ===")
bot.start_new_conversation()
bot.stream_chat("Hi, different question now")

# Simple one-off usage
simple_bot = FinanceBotClient()
simple_bot.stream_chat("Calculate compound interest on $5000 at 3% annually for 5 years")
```

### cURL Example

```bash
# Start a streaming chat
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the square root of 144?",
    "max_tokens": 2048,
    "temperature": 0.0,
    "include_tools": true
  }' \
  --no-buffer

# Get conversation history
curl -X GET http://localhost:8000/api/chat/conversations/abc-123

# Clear conversation
curl -X DELETE http://localhost:8000/api/chat/conversations/abc-123

# List conversations
curl -X GET http://localhost:8000/api/chat/conversations
```

## Available Tools

### Calculator Tool
**Name:** `calculator`
**Description:** Perform basic mathematical calculations
**Input:** 
- `expression`: Mathematical expression (e.g., "2 + 3", "100 * 0.15")

**Example Usage:**
- "What's 15% of $1000?"
- "Calculate 25 * 4 + 10"
- "What's (100 + 50) / 3?"

## Running the Server

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start the server:
```bash
python backend/main.py
```

3. Access the API documentation:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Error Handling

The API provides comprehensive error handling:

### Stream Errors
```json
{
  "type": "error",
  "data": {
    "error": "Error message",
    "conversation_id": "abc-123"
  }
}
```

### HTTP Errors
```json
{
  "success": false,
  "message": "Error description",
  "error": "Detailed error message"
}
```

## Configuration

The chatbot can be configured with:
- Custom system prompts
- Temperature settings
- Token limits
- Tool inclusion/exclusion
- Max iterations for tool calling

## Performance Considerations

- Conversations are stored in memory (use Redis for production)
- Tool execution is sequential (not parallel)
- Stream events are sent in real-time
- Conversation history persists until cleared

## Security Notes

- Input validation is performed on all requests
- Calculator tool only allows safe mathematical operations
- CORS is configured (adjust for production)
- No authentication is implemented (add as needed)
