import { fetchClient } from './client';

export interface PaginationInfo {
  limit: number;
  offset: number;
  total: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationInfo;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata?: Record<string, any>;
}

export const chatApi = {
  getConversations: async (limit: number = 20, offset: number = 0): Promise<Conversation[]> => {
    const res = await fetchClient<PaginatedResponse<Conversation>>(`/conversations?limit=${limit}&offset=${offset}`);
    if (!res || !Array.isArray(res.items)) {
      throw new Error('Malformed API response: expected paginated items array for conversations');
    }
    return res.items;
  },
  
  createConversation: (title: string): Promise<Conversation> => 
    fetchClient<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title })
    }),
    
  getConversation: (id: string): Promise<Conversation> => fetchClient<Conversation>(`/conversations/${id}`),
  
  getMessages: async (conversationId: string, limit: number = 50, offset: number = 0): Promise<Message[]> => {
    const res = await fetchClient<PaginatedResponse<Message>>(`/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`);
    if (!res || !Array.isArray(res.items)) {
      throw new Error('Malformed API response: expected paginated items array for messages');
    }
    return res.items;
  },
    
  addMessage: (conversationId: string, role: string, content: string): Promise<Message> =>
    fetchClient<Message>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ role, content })
    })
};
