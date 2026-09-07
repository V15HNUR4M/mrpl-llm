import React, { useState, useEffect, useRef } from 'react';
import { Send, User, Bot, PlusCircle, MessageSquare, Square, Download } from 'lucide-react';
import { chatApi } from '../api/chat';
import type { Conversation, Message } from '../api/chat';
import { agentsApi } from '../api/agents';
import type { Agent } from '../api/agents';
import { useGeneration } from '../context/GenerationContext';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import styles from './ChatWorkspace.module.css';

const getFileCardDetails = (filename: string, fileType?: string) => {
  const ext = (fileType || filename.split('.').pop() || 'md').toLowerCase().replace(/^\./, '');
  if (ext === 'docx') {
    return { icon: '📝', label: 'Word Document', btnText: 'Download Word' };
  }
  if (ext === 'pdf') {
    return { icon: '📕', label: 'PDF Document', btnText: 'Download PDF' };
  }
  if (ext === 'xlsx' || ext === 'xls') {
    return { icon: '📊', label: 'Excel Spreadsheet', btnText: 'Download Excel' };
  }
  return { icon: '📄', label: 'Markdown Document', btnText: 'Download Markdown' };
};

export const ChatWorkspace: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [inputValue, setInputValue] = useState('');

  // Use application-level GenerationContext (survives page navigation)
  const {
    activeConversationId,
    setActiveConversationId,
    isStreaming,
    streamingConversationId,
    streamingText,
    agentState,
    streamingSources,
    streamingFile,
    latestTitleUpdate,
    startGeneration,
    stopGeneration,
    generationCompletedAt
  } = useGeneration();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const fetchConversations = async () => {
    try {
      const data = await chatApi.getConversations();
      setConversations(data);
      if (data.length > 0 && !activeConversationId) {
        setActiveConversationId(data[0].id);
      }
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

  const loadMessages = async (convId: string) => {
    try {
      const data = await chatApi.getMessages(convId);
      setMessages(data);
    } catch (e) {
      console.error(e);
    }
  };

  // Real-time title update from streaming events
  useEffect(() => {
    if (latestTitleUpdate) {
      setConversations(prev => prev.map(c => 
        c.id === latestTitleUpdate.conversationId 
          ? { ...c, title: latestTitleUpdate.title } 
          : c
      ));
    }
  }, [latestTitleUpdate]);

  // Load messages when conversation changes
  useEffect(() => {
    if (activeConversationId) {
      loadMessages(activeConversationId);
    } else {
      setMessages([]);
    }
  }, [activeConversationId]);

  // Refresh messages and conversations when generation completes
  useEffect(() => {
    if (generationCompletedAt && activeConversationId) {
      loadMessages(activeConversationId);
      fetchConversations();
    }
  }, [generationCompletedAt]);

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

  const handleDownload = async (fileId: string, filename: string) => {
    try {
      await chatApi.downloadGeneratedFile(fileId, filename);
    } catch (e) {
      console.error('Failed to download generated file:', e);
    }
  };

  const handleSend = async () => {
    if (!inputValue.trim() || !selectedAgentId || isStreaming) return;

    let convId = activeConversationId;
    if (!convId) {
      try {
        const conv = await chatApi.createConversation('New Conversation');
        setConversations(prev => [conv, ...prev]);
        setActiveConversationId(conv.id);
        convId = conv.id;
      } catch (e) {
        console.error('Failed to create new conversation:', e);
        return;
      }
    }

    const userText = inputValue.trim();
    setInputValue('');
    
    // Optimistic user message in UI
    const userMsg: Message = {
      id: Date.now().toString(),
      conversation_id: convId,
      role: 'user',
      content: userText,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);

    // Start generation managed at application level
    await startGeneration(
      selectedAgentId,
      convId,
      userText,
      (finalAnswer, sources, generatedFile) => {
        // Optimistic assistant message upon completion before DB sync
        const meta: any = { sources };
        if (generatedFile) {
          meta.generated_file = generatedFile;
        }
        setMessages(prev => [...prev, {
          id: (Date.now() + 1).toString(),
          conversation_id: convId,
          role: 'assistant',
          content: finalAnswer,
          created_at: new Date().toISOString(),
          metadata: meta
        }]);
      }
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
  };

  const isCurrentConvStreaming = isStreaming && streamingConversationId === activeConversationId;

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
                      {msg.role === 'assistant' ? (
                        <MarkdownRenderer content={msg.content} />
                      ) : (
                        msg.content
                      )}
                      {(() => {
                        const genFile = msg.metadata?.generated_file || (msg as any).metadata_?.generated_file;
                        if (!genFile) return null;
                        const card = getFileCardDetails(genFile.filename, genFile.file_type);
                        return (
                          <div className={styles.fileCard}>
                            <div className={styles.fileInfo}>
                              <span className={styles.fileIcon}>{card.icon}</span>
                              <div className={styles.fileText}>
                                <span className={styles.fileName}>{genFile.filename}</span>
                                {genFile.size_bytes ? (
                                  <span className={styles.fileMeta}>{Math.round(genFile.size_bytes / 1024 * 10) / 10 || 1} KB • {card.label}</span>
                                ) : (
                                  <span className={styles.fileMeta}>{card.label}</span>
                                )}
                              </div>
                            </div>
                            <button 
                              className={styles.downloadBtn}
                              onClick={() => handleDownload(genFile.file_id, genFile.filename)}
                              title={card.btnText}
                            >
                              <Download size={14} /> {card.btnText}
                            </button>
                          </div>
                        );
                      })()}
                      {msg.metadata?.sources && msg.metadata.sources.length > 0 && (
                        <div className={styles.sources}>
                          <div className={styles.sourcesTitle}>Sources</div>
                          {msg.metadata.sources.map((s: any, idx: number) => {
                            let parsed: any = null;
                            if (typeof s.content === 'string') {
                              try { parsed = JSON.parse(s.content); } catch (e) {}
                            } else if (typeof s.content === 'object') {
                              parsed = s.content;
                            }
                            const filename = s.metadata?.filename || (parsed && parsed.filename) || s.source || 'Document';
                            const section = s.metadata?.section || (parsed && parsed.section);
                            return (
                              <div key={idx} className={styles.sourceChip}>
                                <span className={styles.sourceDoc}>{filename}</span>
                                {section && <span className={styles.sourceScore}>Section: {section}</span>}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              
              {isCurrentConvStreaming && (
                <div className={`${styles.messageWrapper}`}>
                  <div className={styles.message}>
                    <div className={`${styles.avatar} ${styles.avatarAssistant}`}>
                      <Bot size={18} />
                    </div>
                    <div className={styles.messageContent}>
                      {streamingText ? (
                        <MarkdownRenderer content={streamingText} />
                      ) : null}
                      {streamingFile && (() => {
                        const card = getFileCardDetails(streamingFile.filename, streamingFile.file_type);
                        return (
                          <div className={styles.fileCard}>
                            <div className={styles.fileInfo}>
                              <span className={styles.fileIcon}>{card.icon}</span>
                              <div className={styles.fileText}>
                                <span className={styles.fileName}>{streamingFile.filename}</span>
                                {streamingFile.size_bytes ? (
                                  <span className={styles.fileMeta}>{Math.round(streamingFile.size_bytes / 1024 * 10) / 10 || 1} KB • {card.label}</span>
                                ) : (
                                  <span className={styles.fileMeta}>{card.label}</span>
                                )}
                              </div>
                            </div>
                            <button 
                              className={styles.downloadBtn}
                              onClick={() => handleDownload(streamingFile.file_id, streamingFile.filename)}
                              title={card.btnText}
                            >
                              <Download size={14} /> {card.btnText}
                            </button>
                          </div>
                        );
                      })()}
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
                            let parsed: any = null;
                            if (typeof s.content === 'string') {
                              try { parsed = JSON.parse(s.content); } catch (e) {}
                            } else if (typeof s.content === 'object') {
                              parsed = s.content;
                            }
                            const filename = s.metadata?.filename || (parsed && parsed.filename) || s.source || 'Document';
                            return (
                              <div key={idx} className={styles.sourceChip}>
                                <span className={styles.sourceDoc}>{filename}</span>
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
                  placeholder={isStreaming ? "Generating response..." : "Ask MRPL AI Workbench..."}
                  value={inputValue}
                  onChange={handleInput}
                  onKeyDown={handleKeyDown}
                  disabled={isStreaming}
                  rows={1}
                />
                {isStreaming ? (
                  <button 
                    className={styles.stopBtn}
                    onClick={stopGeneration}
                    title="Stop Generation"
                    aria-label="Stop Generation"
                  >
                    <Square size={14} fill="currentColor" />
                  </button>
                ) : (
                  <button 
                    className={styles.sendBtn} 
                    onClick={handleSend}
                    disabled={!inputValue.trim()}
                    aria-label="Send message"
                  >
                    <Send size={16} />
                  </button>
                )}
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
