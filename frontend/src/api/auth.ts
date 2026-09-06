import { fetchClient } from './client';

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  role: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export const authApi = {
  login: (email: string, password: string): Promise<AuthResponse> => 
    fetchClient<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    }),
    
  register: (email: string, password: string): Promise<AuthResponse> =>
    fetchClient<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    }),
    
  me: (): Promise<User> => fetchClient<User>('/auth/me')
};
