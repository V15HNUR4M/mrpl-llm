import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatWorkspace } from './ChatWorkspace';

let mockState = {
  activeConversationId: 'c1',
  setActiveConversationId: vi.fn(),
  isStreaming: false,
  streamingConversationId: null as string | null,
  streamingText: '',
  agentState: '',
  streamingSources: [] as any[],
  startGeneration: vi.fn(),
  stopGeneration: vi.fn(),
  generationCompletedAt: 0,
};

vi.mock('../context/GenerationContext', () => ({
  useGeneration: vi.fn(() => mockState),
  GenerationProvider: ({ children }: any) => children,
}));

import { useGeneration } from '../context/GenerationContext';

vi.mock('../api/chat', () => ({
  chatApi: {
    getConversations: vi.fn().mockResolvedValue([{ id: 'c1', title: 'New Chat' }]),
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
    mockState = {
      activeConversationId: 'c1',
      setActiveConversationId: vi.fn(),
      isStreaming: false,
      streamingConversationId: null,
      streamingText: '',
      agentState: '',
      streamingSources: [],
      startGeneration: vi.fn(),
      stopGeneration: vi.fn(),
      generationCompletedAt: 0,
    };
    (useGeneration as any).mockImplementation(() => mockState);
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

  it('can send a message and trigger startGeneration', async () => {
    const mockStartGen = vi.fn();
    mockState.startGeneration = mockStartGen;

    const user = userEvent.setup();
    render(<ChatWorkspace />);
    
    await screen.findByText(/General Agent/i);
    
    const input = screen.getByPlaceholderText(/ask mrpl ai workbench/i);
    await act(async () => {
      await user.type(input, 'Hello agent{enter}');
    });

    expect(mockStartGen).toHaveBeenCalledWith(
      'a1',
      'c1',
      'Hello agent',
      expect.any(Function)
    );
  });

  it('renders streaming state, partial text, and stop button when isStreaming is active', async () => {
    const mockStop = vi.fn();
    mockState.isStreaming = true;
    mockState.streamingConversationId = 'c1';
    mockState.streamingText = '# Streaming Header\n\n- point one';
    mockState.agentState = 'Generating response...';
    mockState.stopGeneration = mockStop;

    const user = userEvent.setup();
    render(<ChatWorkspace />);
    
    expect(await screen.findByRole('heading', { level: 1, name: 'Streaming Header' })).toBeInTheDocument();
    expect(screen.getByText('point one')).toBeInTheDocument();
    expect(screen.getByText('Generating response...')).toBeInTheDocument();

    const stopBtn = screen.getByTitle(/stop generation/i);
    expect(stopBtn).toBeInTheDocument();

    await act(async () => {
      await user.click(stopBtn);
    });
    expect(mockStop).toHaveBeenCalledTimes(1);
  });

  it('renders conversations list successfully', async () => {
    const { chatApi } = await import('../api/chat');
    vi.mocked(chatApi.getConversations).mockResolvedValueOnce([
      { id: 'c-100', title: 'Refinery Yield Optimization', created_at: '', updated_at: '' },
      { id: 'c-101', title: 'Catalyst Replacement Schedule', created_at: '', updated_at: '' }
    ]);

    render(<ChatWorkspace />);

    expect(await screen.findByText('Refinery Yield Optimization')).toBeInTheDocument();
    expect(await screen.findByText('Catalyst Replacement Schedule')).toBeInTheDocument();
  });

  it('renders assistant messages with Markdown formatted elements', async () => {
    const { chatApi } = await import('../api/chat');
    vi.mocked(chatApi.getMessages).mockResolvedValueOnce([
      {
        id: 'm1',
        conversation_id: 'c1',
        role: 'assistant',
        content: '## Executive Summary\n\n1. First item\n2. Second item\n\n```python\nprint(42)\n```',
        created_at: new Date().toISOString()
      }
    ]);

    render(<ChatWorkspace />);

    expect(await screen.findByRole('heading', { level: 2, name: 'Executive Summary' })).toBeInTheDocument();
    expect(screen.getByText('First item')).toBeInTheDocument();
    expect(screen.getByText('Second item')).toBeInTheDocument();
    expect(screen.getByText('print(42)')).toBeInTheDocument();
  });

  it('renders downloadable markdown file card when message contains generated_file', async () => {
    const { chatApi } = await import('../api/chat');
    vi.mocked(chatApi.getMessages).mockResolvedValueOnce([
      {
        id: 'm2',
        conversation_id: 'c1',
        role: 'assistant',
        content: 'Here is your generated infrastructure report.',
        created_at: new Date().toISOString(),
        metadata: {
          generated_file: {
            file_id: 'file-xyz-123',
            filename: 'infrastructure-report.md',
            size_bytes: 4096
          }
        }
      }
    ]);

    render(<ChatWorkspace />);

    expect(await screen.findByText('infrastructure-report.md')).toBeInTheDocument();
    const downloadBtn = screen.getByRole('button', { name: /download markdown/i });
    expect(downloadBtn).toBeInTheDocument();
  });
});
