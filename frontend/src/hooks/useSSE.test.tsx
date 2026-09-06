import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { useSSE } from './useSSE';
import React from 'react';

// A simple test component to consume the hook
const TestComponent = () => {
  const { isStreaming, startStream, stopStream } = useSSE();
  const [events, setEvents] = React.useState<any[]>([]);

  return (
    <div>
      <div data-testid="status">{isStreaming ? 'streaming' : 'idle'}</div>
      <button onClick={() => startStream('agent1', 'conv1', 'Hello', (e) => setEvents(prev => [...prev, e]))}>Start</button>
      <button onClick={stopStream}>Stop</button>
      <ul data-testid="messages">
        {events.map((m, i) => (
          <li key={i}>{JSON.stringify(m)}</li>
        ))}
      </ul>
    </div>
  );
};

describe('useSSE Hook', () => {
  let mockFetch: any;
  let mockReader: any;

  beforeEach(() => {
    // Setup fetch mock
    mockReader = {
      read: vi.fn(),
      cancel: vi.fn(),
    };
    mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => mockReader,
      },
    });
    vi.stubGlobal('fetch', mockFetch);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('handles normal event parsing', async () => {
    const encoder = new TextEncoder();
    mockReader.read
      .mockResolvedValueOnce({
        done: false,
        value: encoder.encode('data: {"type": "state_changed", "state": "running"}\n\n'),
      })
      .mockResolvedValueOnce({
        done: true,
      });

    render(<TestComponent />);
    
    await act(async () => {
      screen.getByText('Start').click();
    });

    expect(await screen.findByText('{"type":"state_changed","state":"running"}')).toBeInTheDocument();
    expect(screen.getByTestId('status')).toHaveTextContent('idle');
  });

  it('handles chunk boundaries splitting an event', async () => {
    const encoder = new TextEncoder();
    // Event split across two chunks
    mockReader.read
      .mockResolvedValueOnce({
        done: false,
        value: encoder.encode('data: {"type": "text_de'),
      })
      .mockResolvedValueOnce({
        done: false,
        value: encoder.encode('lta", "text": "hello"}\n\n'),
      })
      .mockResolvedValueOnce({
        done: true,
      });

    render(<TestComponent />);
    
    await act(async () => {
      screen.getByText('Start').click();
    });

    expect(await screen.findByText('{"type":"text_delta","text":"hello"}')).toBeInTheDocument();
  });

  it('handles multiple SSE events in a single chunk', async () => {
    const encoder = new TextEncoder();
    mockReader.read
      .mockResolvedValueOnce({
        done: false,
        value: encoder.encode('data: {"type": "event1"}\n\ndata: {"type": "event2"}\n\n'),
      })
      .mockResolvedValueOnce({
        done: true,
      });

    render(<TestComponent />);
    
    await act(async () => {
      screen.getByText('Start').click();
    });

    expect(await screen.findByText('{"type":"event1"}')).toBeInTheDocument();
    expect(await screen.findByText('{"type":"event2"}')).toBeInTheDocument();
  });
  
  it('handles errors gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Bad Request' }),
    });

    render(<TestComponent />);
    
    await act(async () => {
      screen.getByText('Start').click();
    });

    expect(screen.getByTestId('status')).toHaveTextContent('idle');
    expect(await screen.findByText('{"type":"error","error":"Connection failed"}')).toBeInTheDocument();
  });
});
