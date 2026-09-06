import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { chatApi } from './chat';

describe('chatApi paginated response transformation', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.setItem('token', 'fake-test-token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('correctly extracts Conversation[] from paginated conversation envelope', async () => {
    const mockConversations = [
      {
        id: 'conv-1',
        title: 'Conversation 1',
        created_at: '2026-09-06T12:00:00Z',
        updated_at: '2026-09-06T12:00:00Z'
      },
      {
        id: 'conv-2',
        title: 'Conversation 2',
        created_at: '2026-09-06T12:05:00Z',
        updated_at: '2026-09-06T12:05:00Z'
      }
    ];

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: mockConversations,
        pagination: { limit: 20, offset: 0, total: 2 }
      })
    });

    globalThis.fetch = fetchMock;

    const result = await chatApi.getConversations();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl] = fetchMock.mock.calls[0];
    expect(calledUrl).toContain('/conversations?limit=20&offset=0');
    expect(result).toEqual(mockConversations);
    expect(Array.isArray(result)).toBe(true);
  });

  it('correctly extracts Message[] from paginated messages envelope', async () => {
    const mockMessages = [
      {
        id: 'msg-1',
        conversation_id: 'conv-1',
        role: 'user' as const,
        content: 'Hello AI',
        created_at: '2026-09-06T12:00:00Z'
      },
      {
        id: 'msg-2',
        conversation_id: 'conv-1',
        role: 'assistant' as const,
        content: 'Hello! How can I help you?',
        created_at: '2026-09-06T12:00:05Z'
      }
    ];

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: mockMessages,
        pagination: { limit: 50, offset: 0, total: 2 }
      })
    });

    globalThis.fetch = fetchMock;

    const result = await chatApi.getMessages('conv-1');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl] = fetchMock.mock.calls[0];
    expect(calledUrl).toContain('/conversations/conv-1/messages?limit=50&offset=0');
    expect(result).toEqual(mockMessages);
    expect(Array.isArray(result)).toBe(true);
  });

  it('throws an error on malformed conversation response missing items array', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        invalid_structure: true
      })
    });

    globalThis.fetch = fetchMock;

    await expect(chatApi.getConversations()).rejects.toThrow(
      /Malformed API response: expected paginated items array for conversations/
    );
  });

  it('throws an error on malformed messages response missing items array', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        invalid_structure: true
      })
    });

    globalThis.fetch = fetchMock;

    await expect(chatApi.getMessages('conv-1')).rejects.toThrow(
      /Malformed API response: expected paginated items array for messages/
    );
  });
});
