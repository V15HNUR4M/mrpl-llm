import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { API_BASE_URL, fetchClient } from './client';

describe('client API configuration', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('uses 127.0.0.1:8000/api/v1 as API_BASE_URL for backend consistency', () => {
    expect(API_BASE_URL).toBe('http://127.0.0.1:8000/api/v1');
  });

  it('prefixes requests with API_BASE_URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true })
    });
    globalThis.fetch = fetchMock;

    await fetchClient('/test-endpoint');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/test-endpoint',
      expect.objectContaining({
        headers: expect.any(Headers)
      })
    );
  });
});
