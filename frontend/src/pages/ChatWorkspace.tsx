import React, { useState, useEffect, useRef } from 'react';
import { Send, User, Bot, PlusCircle, MessageSquare } from 'lucide-react';
import { chatApi } from '../api/chat';
import type { Conversation, Message } from '../api/chat';
import { agentsApi } from '../api/agents';
import type { Agent } from '../api/agents';
import { useSSE } from '../hooks/useSSE';
import styles from './ChatWorkspace.module.css';

export const ChatWorkspace: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [inputValue, setInputValue] = useState('');
  
  // Streaming state
  const { isStreaming, startStream } = useSSE();
  const [streamingText, setStreamingText] = useState('');
  const [agentState, setAgentState] = useState('');
  const [streamingSources, setStreamingSources] = useState<any[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const fetchConversations = async () => {
    try {
      const data = await chatApi.getConversations();
      setConversations(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchAgents = async () => {
    try {
      const data = await agentsApi.getAgents();
      setAgents(data);
      if (data.length > 0 && !selectedAgentId) {
        setSelectedAgentId(data[0].agent_id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchConversations();
    fetchAgents();
  }, []);

  useEffect(() => {
    if (activeConversationId) {
      chatApi.getMessages(activeConversationId).then(setMessages).catch(console.error);
    } else {
      setMessages([]);
    }
  }, [activeConversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText, agentState]);

  const handleCreateNew = async () => {
    try {
      const conv = await chatApi.createConversation('New Conversation');
      setConversations([conv, ...conversations]);
      setActiveConversationId(conv.id);
      inputRef.current?.focus();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSend = async () => {
    if (!inputValue.trim() || !activeConversationId || !selectedAgentId || isStreaming) return;

    const userText = inputValue.trim();
    setInputValue('');
    
    // Add optimistic user message
    const userMsg: Message = {
      id: Date.now().toString(),
      conversation_id: activeConversationId,
      role: 'user',
      content: userText,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    
    // Reset streaming state
    setStreamingText('');
    setAgentState('Initializing...');
    setStreamingSources([]);

    await startStream(
      selectedAgentId,
      activeConversationId,
      userText,
      (event) => {
        switch (event.type) {
          case 'state_changed':
            setAgentState(formatAgentState(event.state));
            break;
          case 'text_delta':
            setStreamingText(prev => prev + event.text);
            break;
          case 'context_candidate':
            if (event.candidate && event.candidate.type === 'context' && event.candidate.source === 'search_documents') {
              setStreamingSources(prev => [...prev, event.candidate]);
            }
            break;
          case 'completed':
            // Add the final assistant message to the list
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              conversation_id: activeConversationId,
              role: 'assistant',
              content: event.final_answer || streamingText, // fallback
              created_at: new Date().toISOString(),
              metadata: { sources: streamingSources }
            }]);
            setStreamingText('');
            setAgentState('');
            setStreamingSources([]);
            break;
          case 'error':
            setAgentState(`Error: ${event.error}`);
            break;
        }
      }
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatAgentState = (state: string) => {
    const map: Record<string, string> = {
      'CONTEXT_BUILDING': 'Preparing context...',
      'GENERATING': 'Generating response...',
      'TOOL_EXECUTION': 'Executing tool...',
      'WAITING_FOR_TOOL': 'Processing tools...'
    };
    return map[state] || state;
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
  };

  return (
    <div className={styles.workspace}>
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <button className={`btn btn-outline ${styles.newChatBtn}`} onClick={handleCreateNew}>
            <PlusCircle size={16} /> New Chat
          </button>
        </div>
        <div className={styles.conversationList}>
          {conversations.map(conv => (
            <div 
              key={conv.id}
              className={`${styles.conversationItem} ${activeConversationId === conv.id ? styles.conversationItemActive : ''}`}
              onClick={() => setActiveConversationId(conv.id)}
            >
              <MessageSquare size={16} />
              <span className={styles.conversationTitle}>{conv.title}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.chatArea}>
        {activeConversationId ? (
          <>
            <div className={styles.agentSelector}>
              <span>Agent:</span>
              <select 
                className={styles.agentSelect}
                value={selectedAgentId} 
                onChange={e => setSelectedAgentId(e.target.value)}
                disabled={isStreaming}
              >
                {agents.map(a => (
                  <option key={a.agent_id} value={a.agent_id}>{a.name} ({a.version})</option>
                ))}
              </select>
            </div>
            
            <div className={styles.messageList}>
              {messages.map((msg, i) => (
                <div key={msg.id || i} className={`${styles.messageWrapper}`}>
                  <div className={`${styles.message} ${msg.role === 'user' ? styles.messageUser : ''}`}>
                    <div className={`${styles.avatar} ${msg.role === 'user' ? styles.avatarUser : styles.avatarAssistant}`}>
                      {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
                    </div>
                    <div className={styles.messageContent}>
                      {msg.content}
                      {msg.metadata?.sources && msg.metadata.sources.length > 0 && (
                        <div className={styles.sources}>
                          <div className={styles.sourcesTitle}>Sources</div>
                          {msg.metadata.sources.map((s: any, idx: number) => {
                            const parsedContent = typeof s.content === 'string' ? JSON.parse(s.content) : s.content;
                            return (
                              <div key={idx} className={styles.sourceChip}>
                                <span className={styles.sourceDoc}>{parsedContent.filename || 'Document'}</span>
                                {parsedContent.section && <span className={styles.sourceScore}>Section: {parsedContent.section}</span>}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              
              {isStreaming && (
                <div className={`${styles.messageWrapper}`}>
                  <div className={styles.message}>
                    <div className={`${styles.avatar} ${styles.avatarAssistant}`}>
                      <Bot size={18} />
                    </div>
                    <div className={styles.messageContent}>
                      {streamingText}
                      {(!streamingText || agentState) && (
                        <div className={styles.agentState}>
                          <div className="spinner dark" style={{ width: 12, height: 12, borderWidth: 1 }}></div>
                          {agentState}
                        </div>
                      )}
                      {streamingSources.length > 0 && (
                        <div className={styles.sources}>
                          <div className={styles.sourcesTitle}>Retrieved Sources</div>
                          {streamingSources.map((s, idx) => {
                            let parsed = s.content;
                            if (typeof s.content === 'string') {
                              try { parsed = JSON.parse(s.content); } catch (e) {}
                            }
                            return (
                              <div key={idx} className={styles.sourceChip}>
                                <span className={styles.sourceDoc}>{parsed.filename || 'Document'}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>

            <div className={styles.composer}>
              <div className={styles.composerInner}>
                <textarea
                  ref={inputRef}
                  className={styles.composerInput}
                  placeholder="Ask MRPL AI Workbench..."
                  value={inputValue}
                  onChange={handleInput}
                  onKeyDown={handleKeyDown}
                  disabled={isStreaming}
                  rows={1}
                />
                <button 
                  className={styles.sendBtn} 
                  onClick={handleSend}
                  disabled={!inputValue.trim() || isStreaming}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className={styles.emptyState}>
            <Bot size={48} color="var(--color-border-strong)" style={{ marginBottom: 16 }} />
            <h2>Welcome to MRPL AI Workbench</h2>
            <p>Select or create a new conversation to get started.</p>
          </div>
        )}
      </div>
    </div>
  );
};
