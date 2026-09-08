import { fetchClient } from './client';

export interface UserItem {
  id: string;
  username: string;
  email?: string | null;
  display_name?: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

export interface PaginatedUsers {
  items: UserItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateUserPayload {
  username: string;
  email?: string;
  display_name?: string;
  password: string;
  role: string;
  is_active?: boolean;
}

export interface UpdateUserPayload {
  email?: string;
  display_name?: string;
  role?: string;
  is_active?: boolean;
  password?: string;
}

export interface UserQueryParams {
  limit?: number;
  offset?: number;
  role?: string;
  is_active?: boolean;
  search?: string;
}

export const usersApi = {
  listUsers: (params?: UserQueryParams): Promise<PaginatedUsers> => {
    const searchParams = new URLSearchParams();
    if (params?.limit !== undefined) searchParams.append('limit', String(params.limit));
    if (params?.offset !== undefined) searchParams.append('offset', String(params.offset));
    if (params?.role) searchParams.append('role', params.role);
    if (params?.is_active !== undefined) searchParams.append('is_active', String(params.is_active));
    if (params?.search) searchParams.append('search', params.search);

    const query = searchParams.toString();
    return fetchClient<PaginatedUsers>(`/users${query ? `?${query}` : ''}`);
  },

  createUser: (payload: CreateUserPayload): Promise<UserItem> =>
    fetchClient<UserItem>('/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getUser: (userId: string): Promise<UserItem> =>
    fetchClient<UserItem>(`/users/${userId}`),

  updateUser: (userId: string, payload: UpdateUserPayload): Promise<UserItem> =>
    fetchClient<UserItem>(`/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deactivateUser: (userId: string): Promise<UserItem> =>
    fetchClient<UserItem>(`/users/${userId}`, {
      method: 'DELETE',
    }),
};
