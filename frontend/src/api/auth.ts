import { fetchClient, setAuthToken, removeAuthToken } from './client';

export interface User {
  id: string;
  username?: string;
  email?: string | null;
  is_active: boolean;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export const authApi = {
  login: async (username: string, password: string): Promise<AuthResponse> => {
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);

    const tokenResponse = await fetchClient<TokenResponse>('/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });

    setAuthToken(tokenResponse.access_token);
    try {
      const user = await authApi.me(tokenResponse.access_token);
      return {
        access_token: tokenResponse.access_token,
        token_type: tokenResponse.token_type,
        user,
      };
    } catch (err) {
      removeAuthToken();
      throw err;
    }
  },
    
  register: (email: string, password: string): Promise<AuthResponse> =>
    fetchClient<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    }),
    
  me: (token?: string): Promise<User> =>
    fetchClient<User>('/auth/me', token ? {
      headers: { Authorization: `Bearer ${token}` }
    } : {})
};
