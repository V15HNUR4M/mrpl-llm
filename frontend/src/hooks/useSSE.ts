import { useState, useCallback, useRef } from 'react';
import { agentsApi } from '../api/agents';

export type StreamingEvent = 
  | { type: 'session_created', session_id: string }
  | { type: 'state_changed', state: string }
  | { type: 'context_assembled', token_budget: number }
  | { type: 'text_delta', text: string }
  | { type: 'tool_execution_started', tool: string, arguments: any }
  | { type: 'tool_completed', tool: string, result: any, status: string }
  | { type: 'context_candidate', candidate: any }
  | { type: 'completed', final_answer: string }
  | { type: 'error', error: string };

export function useSSE() {
  const [isStreaming, setIsStreaming] = useState(false);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  const startStream = useCallback(async (
    agentId: string, 
    conversationId: string, 
    message: string, 
    onEvent: (event: StreamingEvent) => void
  ) => {
    setIsStreaming(true);
    
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
        buffer = lines.pop() || ''; // Keep the last incomplete line in the buffer
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr.trim()) {
              try {
                const event = JSON.parse(dataStr) as StreamingEvent;
                onEvent(event);
                
                if (event.type === 'completed' || event.type === 'error') {
                  // We could choose to break here, but we'll let the stream close naturally
                }
              } catch (e) {
                console.error('Failed to parse SSE JSON', e, dataStr);
              }
            }
          }
        }
      }
    } catch (err) {
      console.error('Stream error:', err);
      onEvent({ type: 'error', error: 'Connection failed' });
    } finally {
      setIsStreaming(false);
      readerRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    if (readerRef.current) {
      readerRef.current.cancel();
      readerRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  return { isStreaming, startStream, stopStream };
}
