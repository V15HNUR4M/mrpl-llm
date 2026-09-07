import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Send, User, Bot, Plus, MessageSquare, Square, Download, Trash2, ChevronDown, Shield, Cpu } from 'lucide-react';
import { chatApi } from '../api/chat';
import type { Conversation, Message } from '../api/chat';
import { agentsApi } from '../api/agents';
import type { Agent } from '../api/agents';
import { useGeneration } from '../context/GenerationContext';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import styles from './ChatWorkspace.module.css';

interface ConversationGroup {
  label: string;
  items: Conversation[];
}

const getAgentIcon = (id: string = '', name: string = '') => {
  const lower = (id + ' ' + name).toLowerCase();
  if (lower.includes('excel')) return '📊';
  if (lower.includes('document')) return '📄';
  if (lower.includes('analysis')) return '🔍';
  return '🧠';
};

const groupConversations = (list: Conversation[]): ConversationGroup[] => {
  const today: Conversation[] = [];
  const yesterday: Conversation[] = [];
  const earlier: Conversation[] = [];

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;

  list.forEach(conv => {
    const dateStr = conv.updated_at || conv.created_at;
    if (!dateStr) {
      earlier.push(conv);
      return;
    }
    const convTime = new Date(dateStr).getTime();
    if (isNaN(convTime)) {
      earlier.push(conv);
    } else if (convTime >= startOfToday) {
      today.push(conv);
    } else if (convTime >= startOfYesterday) {
      yesterday.push(conv);
    } else {
      earlier.push(conv);
    }
  });

  const groups: ConversationGroup[] = [];
  if (today.length > 0) groups.push({ label: 'Today', items: today });
  if (yesterday.length > 0) groups.push({ label: 'Yesterday', items: yesterday });
  if (earlier.length > 0) groups.push({ label: 'Earlier', items: earlier });
  if (groups.length === 0 && list.length > 0) {
    groups.push({ label: 'Conversations', items: list });
  }
  return groups;
};

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
  const [convToDelete, setConvToDelete] = useState<Conversation | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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

  useEffect(() => {
    if (latestTitleUpdate) {
      setConversations(prev => prev.map(c => 
        c.id === latestTitleUpdate.conversationId 
          ? { ...c, title: latestTitleUpdate.title } 
          : c
      ));
    }
  }, [latestTitleUpdate]);

  useEffect(() => {
    if (activeConversationId) {
      loadMessages(activeConversationId);
    } else {
      setMessages([]);
    }
  }, [activeConversationId]);

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

  const handleDeleteConversation = async () => {
    if (!convToDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await chatApi.deleteConversation(convToDelete.id);
      const remaining = conversations.filter(c => c.id !== convToDelete.id);
      setConversations(remaining);

      if (activeConversationId === convToDelete.id) {
        if (remaining.length > 0) {
          setActiveConversationId(remaining[0].id);
        } else {
          setActiveConversationId(null);
          setMessages([]);
        }
      }
      setConvToDelete(null);
    } catch (err: any) {
      console.error('Failed to delete conversation:', err);
      setDeleteError(err.message || 'Failed to delete conversation. Please try again.');
    } finally {
      setIsDeleting(false);
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
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
    
    const userMsg: Message = {
      id: Date.now().toString(),
      conversation_id: convId,
      role: 'user',
      content: userText,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);

    await startGeneration(
      selectedAgentId,
      convId,
      userText,
      (finalAnswer, sources, generatedFile) => {
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
    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
  };

  const isCurrentConvStreaming = isStreaming && streamingConversationId === activeConversationId;
  const currentAgent = useMemo(() => {
    return agents.find(a => a.agent_id === selectedAgentId) || agents[0];
  }, [agents, selectedAgentId]);

  const groupedConversations = useMemo(() => {
    return groupConversations(conversations);
  }, [conversations]);

  return (
    <div className={styles.workspace}>
      <aside className={styles.sidebar} aria-label="Chat History">
        <div className={styles.sidebarHeader}>
          <button 
            type="button" 
            className={styles.newChatBtn} 
            onClick={handleCreateNew}
            aria-label="New Chat"
          >
            <Plus size={16} />
            <span>New Chat</span>
          </button>
        </div>

        <div className={styles.conversationList}>
          {groupedConversations.map(group => (
            <div key={group.label} className={styles.convGroup}>
              <div className={styles.groupLabel}>{group.label}</div>
              {group.items.map(conv => (
                <div 
                  key={conv.id}
                  className={`${styles.conversationItem} ${activeConversationId === conv.id ? styles.conversationItemActive : ''}`}
                  onClick={() => setActiveConversationId(conv.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      setActiveConversationId(conv.id);
                    }
                  }}
                >
                  <MessageSquare size={15} className={styles.conversationIcon} />
                  <span className={styles.conversationTitle} title={conv.title}>{conv.title}</span>
                  <button
                    type="button"
                    className={styles.deleteConvBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteError(null);
                      setConvToDelete(conv);
                    }}
                    aria-label="Delete conversation"
                    title="Delete conversation"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          ))}

          {conversations.length === 0 && (
            <div className={styles.emptyHistoryNotice}>
              <span>No chat history</span>
            </div>
          )}
        </div>
      </aside>

      <div className={styles.chatArea}>
        {activeConversationId ? (
          <>
            <header className={styles.chatHeader}>
              <div className={styles.agentSelector}>
                <div className={styles.agentSelectorLabel}>
                  <span className={styles.agentTag}>Agent</span>
                  <span className={styles.agentStatusPill}>
                    <span className={styles.statusDot}></span> Ready
                  </span>
                </div>
                <div className={styles.agentControlWrap}>
                  <span className={styles.agentEmoji}>
                    {currentAgent ? getAgentIcon(currentAgent.agent_id, currentAgent.name) : '🧠'}
                  </span>
                  <select 
                    className={styles.agentSelect}
                    value={selectedAgentId} 
                    onChange={e => setSelectedAgentId(e.target.value)}
                    disabled={isStreaming}
                    aria-label="Select Agent"
                  >
                    {agents.map(a => (
                      <option key={a.agent_id} value={a.agent_id}>
                        {a.name} ({a.version || 'v1.0'})
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} className={styles.selectChevron} />
                </div>
              </div>

              <div className={styles.headerSecurityBadges}>
                <div className={styles.securityBadge}>
                  <Shield size={12} className={styles.securityIcon} />
                  <span>On-Premise Llama 3.2</span>
                </div>
                <div className={styles.securityBadge}>
                  <Cpu size={12} className={styles.securityIcon} />
                  <span>Deterministic Audit</span>
                </div>
              </div>
            </header>
            
            <div className={styles.messageList}>
              <div className={styles.messageListInner}>
                {messages.map((msg, i) => {
                  const isUser = msg.role === 'user';
                  if (isUser) {
                    return (
                      <div key={msg.id || i} className={styles.messageRowUser}>
                        <div className={styles.messageUserBubble}>
                          <div className={styles.messageContentUser}>
                            {msg.content}
                          </div>
                          <div className={styles.avatarUser}>
                            <User size={13} />
                          </div>
                        </div>
                      </div>
                    );
                  }

                  const genFile = msg.metadata?.generated_file || (msg as any).metadata_?.generated_file;
                  const agentName = msg.agent_id 
                    ? (agents.find(a => a.agent_id === msg.agent_id)?.name || msg.agent_id.replace(/_/g, ' '))
                    : (currentAgent?.name || 'General Agent');

                  return (
                    <div key={msg.id || i} className={styles.messageRowAssistant}>
                      <div className={styles.avatarAssistant}>
                        <Bot size={16} />
                      </div>
                      <div className={styles.messageAssistantCard}>
                        <div className={styles.assistantHeader}>
                          <span className={styles.assistantAgentBadge}>
                            {getAgentIcon(msg.agent_id || '', agentName)} {agentName}
                          </span>
                        </div>
                        <div className={styles.messageContent}>
                          <MarkdownRenderer content={msg.content} />
                          
                          {genFile && (() => {
                            const card = getFileCardDetails(genFile.filename, genFile.file_type);
                            return (
                              <div className={styles.fileCard}>
                                <div className={styles.fileIconWrap}>
                                  <span className={styles.fileIcon}>{card.icon}</span>
                                </div>
                                <div className={styles.fileInfo}>
                                  <span className={styles.fileName} title={genFile.filename}>{genFile.filename}</span>
                                  <span className={styles.fileMeta}>
                                    {card.label} • {genFile.size_bytes ? `${Math.round(genFile.size_bytes / 1024 * 10) / 10 || 1} KB` : 'Ready'}
                                  </span>
                                </div>
                                <button 
                                  type="button"
                                  className={styles.downloadBtn}
                                  onClick={() => handleDownload(genFile.file_id, genFile.filename)}
                                  title={card.btnText}
                                  aria-label={card.btnText}
                                >
                                  <Download size={14} />
                                  <span>{card.btnText}</span>
                                </button>
                              </div>
                            );
                          })()}

                          {msg.metadata?.sources && msg.metadata.sources.length > 0 && (
                            <div className={styles.sources}>
                              <div className={styles.sourcesTitle}>EVIDENCE CITATIONS</div>
                              <div className={styles.sourcesList}>
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
                                    <div key={idx} className={styles.sourceChip} title={filename}>
                                      <span className={styles.sourceIcon}>📄</span>
                                      <span className={styles.sourceDoc}>{filename}</span>
                                      {section && <span className={styles.sourceScore}>§ {section}</span>}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                
                {isCurrentConvStreaming && (
                  <div className={styles.messageRowAssistant}>
                    <div className={`${styles.avatarAssistant} ${styles.avatarStreaming}`}>
                      <Bot size={16} />
                    </div>
                    <div className={styles.messageAssistantCard}>
                      <div className={styles.assistantHeader}>
                        <span className={styles.assistantAgentBadge}>
                          {getAgentIcon(selectedAgentId, currentAgent?.name)} {currentAgent?.name || 'General Agent'}
                        </span>
                        <span className={styles.streamingIndicatorBadge}>
                          <span className={styles.pulsingDot}></span> Streaming
                        </span>
                      </div>
                      <div className={styles.messageContent}>
                        {streamingText ? (
                          <MarkdownRenderer content={streamingText} />
                        ) : null}

                        {streamingFile && (() => {
                          const card = getFileCardDetails(streamingFile.filename, streamingFile.file_type);
                          return (
                            <div className={styles.fileCard}>
                              <div className={styles.fileIconWrap}>
                                <span className={styles.fileIcon}>{card.icon}</span>
                              </div>
                              <div className={styles.fileInfo}>
                                <span className={styles.fileName} title={streamingFile.filename}>{streamingFile.filename}</span>
                                <span className={styles.fileMeta}>
                                  {card.label} • {streamingFile.size_bytes ? `${Math.round(streamingFile.size_bytes / 1024 * 10) / 10 || 1} KB` : 'Ready'}
                                </span>
                              </div>
                              <button 
                                type="button"
                                className={styles.downloadBtn}
                                onClick={() => handleDownload(streamingFile.file_id, streamingFile.filename)}
                                title={card.btnText}
                                aria-label={card.btnText}
                              >
                                <Download size={14} />
                                <span>{card.btnText}</span>
                              </button>
                            </div>
                          );
                        })()}

                        {(!streamingText || agentState) && (
                          <div className={styles.agentState}>
                            <div className="spinner dark" style={{ width: 12, height: 12, borderWidth: 2 }}></div>
                            <span>{agentState}</span>
                          </div>
                        )}

                        {streamingSources.length > 0 && (
                          <div className={styles.sources}>
                            <div className={styles.sourcesTitle}>RETRIEVED SOURCES</div>
                            <div className={styles.sourcesList}>
                              {streamingSources.map((s, idx) => {
                                let parsed: any = null;
                                if (typeof s.content === 'string') {
                                  try { parsed = JSON.parse(s.content); } catch (e) {}
                                } else if (typeof s.content === 'object') {
                                  parsed = s.content;
                                }
                                const filename = s.metadata?.filename || (parsed && parsed.filename) || s.source || 'Document';
                                return (
                                  <div key={idx} className={styles.sourceChip} title={filename}>
                                    <span className={styles.sourceIcon}>📄</span>
                                    <span className={styles.sourceDoc}>{filename}</span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
                
                <div ref={messagesEndRef} />
              </div>
            </div>

            <div className={styles.composerWrapper}>
              <div className={styles.composerCard}>
                <textarea
                  ref={inputRef}
                  className={styles.composerInput}
                  placeholder={isStreaming ? "Generating response..." : "Ask MRPL AI Workbench..."}
                  value={inputValue}
                  onChange={handleInput}
                  onKeyDown={handleKeyDown}
                  disabled={isStreaming}
                  rows={1}
                  aria-label="Ask MRPL AI Workbench"
                />
                <div className={styles.composerActions}>
                  <div className={styles.composerHint}>
                    <span>↵ Send</span>
                    <span className={styles.hintDot}>•</span>
                    <span>Shift+↵ New line</span>
                  </div>
                  {isStreaming ? (
                    <button 
                      type="button"
                      className={styles.stopBtn}
                      onClick={stopGeneration}
                      title="Stop Generation"
                      aria-label="Stop Generation"
                    >
                      <Square size={13} fill="currentColor" />
                      <span>Stop</span>
                    </button>
                  ) : (
                    <button 
                      type="button"
                      className={styles.sendBtn} 
                      onClick={handleSend}
                      disabled={!inputValue.trim()}
                      title="Send message"
                      aria-label="Send message"
                    >
                      <Send size={15} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className={styles.emptyState}>
            <div className={styles.emptyHero}>
              <div className={styles.emptyIconWrap}>
                <Bot size={42} className={styles.emptyIcon} />
              </div>
              <h2>Welcome to MRPL AI Workbench</h2>
              <p className={styles.emptySub}>Sovereign, On-Premise Industrial AI Assistant</p>
              
              <div className={styles.emptyCapabilities}>
                <div className={styles.capPill}>
                  <span>🏭 Refinery Procedures</span>
                </div>
                <div className={styles.capPill}>
                  <span>📊 Crude Oil Spreadsheets</span>
                </div>
                <div className={styles.capPill}>
                  <span>📄 Technical Manuals</span>
                </div>
                <div className={styles.capPill}>
                  <span>⚙️ Equipment Maintenance</span>
                </div>
              </div>

              <button 
                type="button"
                className={`btn btn-primary ${styles.emptyStartBtn}`}
                onClick={handleCreateNew}
              >
                <Plus size={16} /> Start a New Conversation
              </button>
            </div>
          </div>
        )}
      </div>

      {convToDelete && (
        <div className={styles.modalOverlay} onClick={() => !isDeleting && setConvToDelete(null)}>
          <div 
            className={styles.modal} 
            onClick={e => e.stopPropagation()} 
            role="dialog" 
            aria-modal="true" 
            aria-labelledby="delete-dialog-title"
          >
            <div className={styles.modalHeader}>
              <h3 id="delete-dialog-title" className={styles.modalTitle}>Delete this conversation?</h3>
            </div>
            <div className={styles.modalBody}>
              <p className={styles.modalText}>
                Are you sure you want to delete <strong>"{convToDelete.title}"</strong>? This will permanently remove all messages in this conversation.
              </p>
              {deleteError && (
                <div className={styles.deleteErrorMessage} role="alert">
                  {deleteError}
                </div>
              )}
            </div>
            <div className={styles.modalActions}>
              <button 
                type="button"
                className="btn btn-outline"
                onClick={() => { setConvToDelete(null); setDeleteError(null); }}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button 
                type="button"
                className="btn btn-danger"
                onClick={handleDeleteConversation}
                disabled={isDeleting}
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
