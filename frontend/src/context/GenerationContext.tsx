import React, { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react';
import { agentsApi } from '../api/agents';

export type StreamingEvent = 
  | { type: 'session_created', session_id: string }
  | { type: 'state_changed', state: string }
  | { type: 'context_assembled', token_budget: number }
  | { type: 'text_delta', text: string }
  | { type: 'tool_execution_started', tool: string, arguments: any }
  | { type: 'tool_completed', tool: string, result: any, status: string }
  | { type: 'context_candidate', candidate: any }
  | { type: 'title_updated', title: string, conversation_id: string }
  | { type: 'file_generated', file: any }
  | { type: 'completed', final_answer: string, generated_file?: any }
  | { type: 'error', error: string };

interface GenerationContextType {
  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;
  isStreaming: boolean;
  streamingConversationId: string | null;
  streamingText: string;
  agentState: string;
  streamingSources: any[];
  streamingFile: any | null;
  latestTitleUpdate: { conversationId: string; title: string } | null;
  generationId: string | null;
  startGeneration: (
    agentId: string, 
    conversationId: string, 
    message: string,
    onCompleted?: (finalAnswer: string, sources: any[], generatedFile?: any) => void
  ) => Promise<void>;
  stopGeneration: () => Promise<void>;
  generationCompletedAt: number;
}

const GenerationContext = createContext<GenerationContextType | undefined>(undefined);

const formatAgentState = (state: string) => {
  const map: Record<string, string> = {
    'CONTEXT_BUILDING': 'Preparing context...',
    'GENERATING': 'Generating response...',
    'TOOL_EXECUTION': 'Executing tool...',
    'WAITING_FOR_TOOL': 'Processing tools...'
  };
  return map[state] || state;
};

export const GenerationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingConversationId, setStreamingConversationId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [agentState, setAgentState] = useState('');
  const [streamingSources, setStreamingSources] = useState<any[]>([]);
  const [streamingFile, setStreamingFile] = useState<any | null>(null);
  const [latestTitleUpdate, setLatestTitleUpdate] = useState<{ conversationId: string; title: string } | null>(null);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [generationCompletedAt, setGenerationCompletedAt] = useState<number>(0);

  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const activeGenIdRef = useRef<string | null>(null);

  // Check backend for active generation on mount
  useEffect(() => {
    let isMounted = true;
    const checkActive = async () => {
      try {
        const res = await agentsApi.getActiveGeneration();
        if (!isMounted) return;
        if (res.active && res.generation) {
          const gen = res.generation;
          setGenerationId(gen.generation_id);
          activeGenIdRef.current = gen.generation_id;
          setStreamingConversationId(gen.conversation_id);
          setStreamingText(gen.partial_content || '');
          setIsStreaming(true);
          setAgentState('Generating response...');
        }
      } catch (err) {
        // Not critical if fails
      }
    };
    checkActive();
    return () => { isMounted = false; };
  }, []);

  const stopGeneration = useCallback(async () => {
    const currentGenId = activeGenIdRef.current || generationId;
    if (readerRef.current) {
      try {
        await readerRef.current.cancel();
      } catch (e) {
        // ignore
      }
      readerRef.current = null;
    }

    if (currentGenId) {
      try {
        await agentsApi.stopGeneration(currentGenId);
      } catch (e) {
        console.error('Failed to notify backend of stop generation:', e);
      }
    }

    setIsStreaming(false);
    setAgentState('');
    activeGenIdRef.current = null;
    setGenerationId(null);
    setStreamingConversationId(null);
    setGenerationCompletedAt(Date.now());
  }, [generationId]);

  const startGeneration = useCallback(async (
    agentId: string, 
    conversationId: string, 
    message: string,
    onCompleted?: (finalAnswer: string, sources: any[], generatedFile?: any) => void
  ) => {
    setIsStreaming(true);
    setStreamingConversationId(conversationId);
    setStreamingText('');
    setAgentState('Initializing...');
    setStreamingSources([]);
    setStreamingFile(null);
    const accumulatedSources: any[] = [];
    let accumulatedFile: any = null;
    let fullText = '';

    try {
      const response = await agentsApi.createStreamEventSource(agentId, conversationId, message);
      if (!response.ok || !response.body) {
        throw new Error('Failed to start stream');
      }

      const reader = response.body.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr.trim()) {
              try {
                const event = JSON.parse(dataStr) as StreamingEvent;
                switch (event.type) {
                  case 'session_created':
                    setGenerationId(event.session_id);
                    activeGenIdRef.current = event.session_id;
                    break;
                  case 'state_changed':
                    setAgentState(formatAgentState(event.state));
                    break;
                  case 'text_delta':
                    fullText += event.text;
                    setStreamingText(fullText);
                    break;
                  case 'context_candidate':
                    if (event.candidate && ['rag', 'context', 'document'].includes(event.candidate.type)) {
                      accumulatedSources.push(event.candidate);
                      setStreamingSources([...accumulatedSources]);
                    }
                    break;
                  case 'title_updated':
                    setLatestTitleUpdate({ conversationId: event.conversation_id, title: event.title });
                    break;
                  case 'file_generated':
                    accumulatedFile = event.file;
                    setStreamingFile(event.file);
                    break;
                  case 'completed': {
                    const finalAnswer = event.final_answer || fullText;
                    const finalFile = accumulatedFile || event.generated_file;
                    if (onCompleted) {
                      onCompleted(finalAnswer, accumulatedSources, finalFile);
                    }
                    setGenerationCompletedAt(Date.now());
                    break;
                  }
                  case 'error': {
                    console.error('Stream error event:', event.error);
                    setAgentState(`Error: ${event.error}`);
                    break;
                  }
                }
              } catch (e) {
                console.error('Failed to parse SSE line:', e, dataStr);
              }
            }
          }
        }
      }
    } catch (err) {
      console.error('Generation error:', err);
      setAgentState('Connection failed');
    } finally {
      setIsStreaming(false);
      setStreamingConversationId(null);
      activeGenIdRef.current = null;
      setGenerationId(null);
      readerRef.current = null;
      setGenerationCompletedAt(Date.now());
    }
  }, []);

  return (
    <GenerationContext.Provider value={{
      activeConversationId,
      setActiveConversationId,
      isStreaming,
      streamingConversationId,
      streamingText,
      agentState,
      streamingSources,
      streamingFile,
      latestTitleUpdate,
      generationId,
      startGeneration,
      stopGeneration,
      generationCompletedAt
    }}>
      {children}
    </GenerationContext.Provider>
  );
};

export const useGeneration = () => {
  const context = useContext(GenerationContext);
  if (!context) {
    throw new Error('useGeneration must be used within a GenerationProvider');
  }
  return context;
};
