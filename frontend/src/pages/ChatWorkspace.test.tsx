import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatWorkspace } from './ChatWorkspace';

// Mock the SSE hook
vi.mock('../hooks/useSSE', () => ({
  useSSE: vi.fn(() => ({
    isStreaming: false,
    startStream: vi.fn(),
    stopStream: vi.fn(),
  })),
}));

import { useSSE } from '../hooks/useSSE';

vi.mock('../api/chat', () => ({
  chatApi: {
    getConversations: vi.fn().mockResolvedValue([]),
    createConversation: vi.fn().mockResolvedValue({ id: 'c1', title: 'New Chat' }),
    getMessages: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../api/agents', () => ({
  agentsApi: {
    getAgents: vi.fn().mockResolvedValue([{ agent_id: 'a1', name: 'General Agent', description: 'Test', status: 'enabled' }]),
  },
}));

describe('ChatWorkspace UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders chat interface and agent selection', async () => {
    const user = userEvent.setup();
    render(<ChatWorkspace />);
    
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /new chat/i }));
    });

    expect(await screen.findByText(/General Agent/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ask mrpl ai workbench/i)).toBeInTheDocument();
  });

  it('can send a message and start stream', async () => {
    const mockStartStream = vi.fn();
    (useSSE as any).mockReturnValue({
      isStreaming: false,
      startStream: mockStartStream,
      stopStream: vi.fn(),
    });

    const user = userEvent.setup();
    render(<ChatWorkspace />);
    
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /new chat/i }));
    });
    
    // Wait for agents to load and be selected
    await screen.findByText(/General Agent/i);
    
    const input = screen.getByPlaceholderText(/ask mrpl ai workbench/i);
    await act(async () => {
      await user.type(input, 'Hello agent{enter}');
    });

    expect(mockStartStream).toHaveBeenCalledWith(
      'a1',
      expect.any(String), // conversation id
      'Hello agent',
      expect.any(Function)
    );
  });

  it('renders streaming state correctly', async () => {
    let mockIsStreaming = false;
    (useSSE as any).mockImplementation(() => ({
      isStreaming: mockIsStreaming,
      startStream: vi.fn(async (_agentId, _convId, _msg, onEvent) => {
        mockIsStreaming = true;
        onEvent({ type: 'state_changed', state: 'CONTEXT_BUILDING' });
      }),
      stopStream: vi.fn(),
    }));

    const user = userEvent.setup();
    render(<ChatWorkspace />);
    
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /new chat/i }));
    });
    
    await screen.findByText(/General Agent/i);
    
    const input = screen.getByPlaceholderText(/ask mrpl ai workbench/i);
    await act(async () => {
      await user.type(input, 'Hello agent{enter}');
    });
    
    expect(await screen.findByText('Preparing context...')).toBeInTheDocument();
  });

  it('renders conversations list successfully without crashing on .map()', async () => {
    const { chatApi } = await import('../api/chat');
    vi.mocked(chatApi.getConversations).mockResolvedValueOnce([
      { id: 'c-100', title: 'Refinery Yield Optimization', created_at: '', updated_at: '' },
      { id: 'c-101', title: 'Catalyst Replacement Schedule', created_at: '', updated_at: '' }
    ]);

    render(<ChatWorkspace />);

    expect(await screen.findByText('Refinery Yield Optimization')).toBeInTheDocument();
    expect(await screen.findByText('Catalyst Replacement Schedule')).toBeInTheDocument();
  });

  it('renders user-visible error when SSE stream emits an error event', async () => {
    (useSSE as any).mockImplementation(() => ({
      isStreaming: false,
      startStream: vi.fn(async (_agentId, _convId, _msg, onEvent) => {
        onEvent({ type: 'error', error: 'Model execution failed: model not found' });
      }),
      stopStream: vi.fn(),
    }));

    const user = userEvent.setup();
    render(<ChatWorkspace />);
    
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /new chat/i }));
    });
    
    await screen.findByText(/General Agent/i);
    
    const input = screen.getByPlaceholderText(/ask mrpl ai workbench/i);
    await act(async () => {
      await user.type(input, 'Hello agent{enter}');
    });
    
    expect(await screen.findByText(/⚠️ Error: Model execution failed: model not found/i)).toBeInTheDocument();
  });
});
