import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { authApi } from './auth';

describe('authApi client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('sends credentials as application/x-www-form-urlencoded with URLSearchParams and fetches user', async () => {
    const fetchMock = vi.fn();

    // 1st call: /auth/login
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: 'test-token-123',
        token_type: 'bearer',
      }),
    });

    // 2nd call: /auth/me
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        id: 'user-id-1',
        username: 'admin',
        email: null,
        is_active: true,
        role: 'ADMIN',
      }),
    });

    globalThis.fetch = fetchMock;

    const result = await authApi.login('admin', 'admin123');

    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Verify first call to /auth/login
    const [loginUrl, loginOptions] = fetchMock.mock.calls[0];
    expect(loginUrl).toContain('/auth/login');
    expect(loginOptions.method).toBe('POST');
    
    // Check headers
    const headers = new Headers(loginOptions.headers);
    expect(headers.get('Content-Type')).toBe('application/x-www-form-urlencoded');

    // Check body parameters
    const params = new URLSearchParams(loginOptions.body);
    expect(params.get('username')).toBe('admin');
    expect(params.get('password')).toBe('admin123');

    // Verify second call to /auth/me
    const [meUrl, meOptions] = fetchMock.mock.calls[1];
    expect(meUrl).toContain('/auth/me');
    const authHeader = meOptions.headers instanceof Headers 
      ? meOptions.headers.get('Authorization') 
      : (meOptions.headers?.Authorization || meOptions.headers?.authorization || new Headers(meOptions.headers).get('Authorization'));
    expect(authHeader).toBe('Bearer test-token-123');

    // Verify final result
    expect(result).toEqual({
      access_token: 'test-token-123',
      token_type: 'bearer',
      user: {
        id: 'user-id-1',
        username: 'admin',
        email: null,
        is_active: true,
        role: 'ADMIN',
      },
    });
  });
});
