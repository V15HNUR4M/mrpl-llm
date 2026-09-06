export const API_BASE_URL = 'http://localhost:8000/api/v1';

export class APIError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'APIError';
    this.status = status;
  }
}

export const getAuthToken = () => localStorage.getItem('token');
export const setAuthToken = (token: string) => localStorage.setItem('token', token);
export const removeAuthToken = () => localStorage.removeItem('token');

export async function fetchClient<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  
  const headers = new Headers(options.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = 'An error occurred';
    try {
      const errorData = await response.json();
      message = errorData.detail || message;
    } catch {
      message = response.statusText;
    }
    
    if (response.status === 401) {
      removeAuthToken();
      window.dispatchEvent(new Event('unauthorized'));
    }
    
    throw new APIError(response.status, message);
  }

  if (response.status === 204) {
    return {} as T;
  }
  return response.json();
}
