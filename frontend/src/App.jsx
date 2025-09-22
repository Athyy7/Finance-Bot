import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

const App = () => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState(null); // Store conversation ID
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleStreamingResponse = async (response) => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulatedContent = '';

    // Add initial bot message
    const botMessageId = Date.now();
    setMessages(prev => [...prev, {
      id: botMessageId,
      type: 'bot',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    }]);

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (trimmedLine) {
            try {
              let jsonData;
              
              // Handle Server-Sent Events format with "data: " prefix
              if (trimmedLine.startsWith('data: ')) {
                const jsonStr = trimmedLine.slice(6); // Remove "data: " prefix
                jsonData = JSON.parse(jsonStr);
              } else {
                // Try parsing as direct JSON (fallback)
                jsonData = JSON.parse(trimmedLine);
              }
              
              // Handle different message types from your API
              if (jsonData.type === 'text_delta' && jsonData.data && jsonData.data.text) {
                accumulatedContent += jsonData.data.text;
                setMessages(prev => prev.map(msg => 
                  msg.id === botMessageId 
                    ? { ...msg, content: accumulatedContent }
                    : msg
                ));
              } else if (jsonData.type === 'stream_start') {
                // CAPTURE CONVERSATION ID for memory
                const newConversationId = jsonData.data.conversation_id;
                setConversationId(newConversationId);
                console.log('Stream started:', {
                  conversation_id: newConversationId,
                  message_count: jsonData.data.message_count,
                  is_new: jsonData.data.is_new_conversation
                });
              } else if (jsonData.type === 'message_start') {
                console.log('Message iteration started:', jsonData.data.iteration);
              } else if (jsonData.type === 'connection_test') {
                console.log('Connection test:', jsonData);
              } else if (jsonData.type === 'tool_call') {
                console.log('🔧 Tool executing:', jsonData.data.tool_name);
                // Show tool execution indicator in chat
                setMessages(prev => prev.map(msg => 
                  msg.id === botMessageId 
                    ? { ...msg, content: accumulatedContent + `\n\n🔧 *Using ${jsonData.data.tool_name} tool...*` }
                    : msg
                ));
              } else if (jsonData.type === 'tool_result') {
                console.log('🔧 Tool result:', {
                  tool: jsonData.data.tool_name,
                  success: jsonData.data.success,
                  result: jsonData.data.result
                });
                // Remove tool indicator since result is coming
                setMessages(prev => prev.map(msg => 
                  msg.id === botMessageId 
                    ? { ...msg, content: accumulatedContent }
                    : msg
                ));
              } else if (jsonData.type === 'message_complete') {
                console.log('Message completed:', {
                  conversation_id: jsonData.data.conversation_id,
                  total_messages: jsonData.data.total_messages,
                  iterations: jsonData.data.iterations_used
                });
                // Message is complete, stop streaming
                setIsStreaming(false);
                setMessages(prev => prev.map(msg => 
                  msg.id === botMessageId 
                    ? { ...msg, isStreaming: false }
                    : msg
                ));
                return;
              } else if (jsonData.type === 'error') {
                console.error('Stream error:', jsonData.data.error);
                setMessages(prev => prev.map(msg => 
                  msg.id === botMessageId 
                    ? { ...msg, content: accumulatedContent || `Error: ${jsonData.data.error}`, isStreaming: false }
                    : msg
                ));
                return;
              }
            } catch (parseError) {
              // Handle non-JSON lines like "Connected to..." or "•"
              if (!trimmedLine.startsWith('Connected to') && 
                  !trimmedLine.startsWith('Code snippet') && 
                  !trimmedLine.startsWith('cURL') && 
                  !trimmedLine.match(/^\d+$/) &&
                  trimmedLine !== '•' &&
                  trimmedLine !== 'Online' &&
                  !trimmedLine.startsWith('data: ')) {
                console.log('Parse error for line:', trimmedLine, parseError);
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error);
      setMessages(prev => prev.map(msg => 
        msg.id === botMessageId 
          ? { ...msg, content: accumulatedContent || 'Error occurred while streaming response.', isStreaming: false }
          : msg
      ));
    } finally {
      setIsStreaming(false);
      setMessages(prev => prev.map(msg => 
        msg.id === botMessageId 
          ? { ...msg, isStreaming: false }
          : msg
      ));
    }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    
    if (!inputValue.trim() || isLoading || isStreaming) return;

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setIsStreaming(true);

    try {
      // Prepare request body with conversation_id if we have one
      const requestBody = {
        message: inputValue,
        max_tokens: 4096,
        temperature: 0.0,
        include_tools: true
      };

      // Include conversation_id if we have one (for conversation memory)
      if (conversationId) {
        requestBody.conversation_id = conversationId;
        console.log('🔗 Continuing conversation:', conversationId);
      } else {
        console.log('🆕 Starting new conversation');
      }

      const response = await fetch('http://localhost:8000/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      await handleStreamingResponse(response);
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        content: 'Sorry, there was an error processing your request. Please try again.',
        timestamp: new Date(),
        isError: true
      }]);
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(e);
    }
  };

  const startNewConversation = () => {
    setConversationId(null);
    setMessages([]);
    console.log('🔄 Started new conversation');
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <div className="logo-container">
            <Bot className="logo-icon" />
            <h1 className="app-title gradient-text">Finance Agent</h1>
          </div>
          <div className="header-actions">
            {conversationId && messages.length > 0 && (
              <button 
                className="new-conversation-button"
                onClick={startNewConversation}
                disabled={isLoading || isStreaming}
              >
                New Chat
              </button>
            )}
            <div className="status-indicator">
              <div className={`status-dot ${isStreaming ? 'streaming' : 'idle'}`}></div>
              <span className="status-text">
                {isStreaming ? 'Thinking...' : 'Ready'}
              </span>
              {conversationId && messages.length > 0 && (
                <span className="conversation-id">
                  💬 {Math.ceil(messages.length / 2)} exchanges
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="chat-container">
        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="welcome-screen">
              <div className="welcome-content">
                <Bot className="welcome-icon" />
                <h2 className="welcome-title gradient-text">Welcome to Finance Agent</h2>
                <p className="welcome-subtitle">
                  Your intelligent financial assistant powered by AI. Ask me anything about finance, investments, or market analysis.
                </p>
                <div className="suggested-questions">
                  <button 
                    className="suggestion-chip"
                    onClick={() => setInputValue("What's 15% of $5000?")}
                  >
                    💰 Quick Calculation
                  </button>
                  <button 
                    className="suggestion-chip"
                    onClick={() => setInputValue("Calculate compound interest on $10,000 at 5% for 10 years")}
                  >
                    📈 Investment Growth
                  </button>
                  <button 
                    className="suggestion-chip"
                    onClick={() => setInputValue("What's the monthly payment for a $300,000 mortgage at 6% for 30 years?")}
                  >
                    🏠 Mortgage Calculator
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="messages-list">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`message ${message.type} ${message.isError ? 'error' : ''} fade-in`}
                >
                  <div className="message-avatar">
                    {message.type === 'user' ? (
                      <User className="avatar-icon" />
                    ) : (
                      <Bot className="avatar-icon" />
                    )}
                  </div>
                  <div className="message-content">
                    <div className="message-header">
                      <span className="message-sender">
                        {message.type === 'user' ? 'You' : 'Finance Bot'}
                      </span>
                      <span className="message-timestamp">
                        {message.timestamp.toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="message-text">
                      {message.type === 'bot' ? (
                        <div className="markdown-content">
                          <ReactMarkdown 
                            remarkPlugins={[remarkGfm]}
                            components={{
                              // Custom components for styling
                              p: ({children}) => <p style={{margin: '0.5em 0', lineHeight: '1.6'}}>{children}</p>,
                              strong: ({children}) => <strong style={{color: 'var(--light-silver)', fontWeight: '700'}}>{children}</strong>,
                              ul: ({children}) => <ul style={{margin: '0.5em 0', paddingLeft: '1.5em'}}>{children}</ul>,
                              ol: ({children}) => <ol style={{margin: '0.5em 0', paddingLeft: '1.5em'}}>{children}</ol>,
                              li: ({children}) => <li style={{margin: '0.25em 0', lineHeight: '1.5'}}>{children}</li>,
                              code: ({children}) => (
                                <code style={{
                                  background: 'rgba(192, 192, 192, 0.1)',
                                  border: '1px solid rgba(192, 192, 192, 0.2)',
                                  borderRadius: '4px',
                                  padding: '2px 6px',
                                  fontFamily: 'SF Mono, Monaco, Cascadia Code, Roboto Mono, Consolas, Courier New, monospace',
                                  fontSize: '0.9em',
                                  color: 'var(--light-silver)'
                                }}>
                                  {children}
                                </code>
                              ),
                              pre: ({children}) => (
                                <pre style={{
                                  background: 'rgba(10, 10, 10, 0.8)',
                                  border: '1px solid rgba(192, 192, 192, 0.2)',
                                  borderRadius: 'var(--radius-md)',
                                  padding: '1em',
                                  margin: '1em 0',
                                  overflowX: 'auto'
                                }}>
                                  {children}
                                </pre>
                              )
                            }}
                          >
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        message.content
                      )}
                      {message.isStreaming && (
                        <span className="typing-indicator">
                          <span></span>
                          <span></span>
                          <span></span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <form className="input-container" onSubmit={sendMessage}>
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask me to make money..."
              className="message-input"
              rows="1"
              disabled={isLoading || isStreaming}
            />
            <button
              type="submit"
              className={`send-button ${(!inputValue.trim() || isLoading || isStreaming) ? 'disabled' : ''}`}
              disabled={!inputValue.trim() || isLoading || isStreaming}
            >
              {isLoading || isStreaming ? (
                <Loader2 className="send-icon spinning" />
              ) : (
                <Send className="send-icon" />
              )}
            </button>
          </div>
          <div className="input-footer">
            <span className="input-hint">Press Enter to send • Shift + Enter for new line</span>
          </div>
        </form>
      </main>
    </div>
  );
};

export default App;