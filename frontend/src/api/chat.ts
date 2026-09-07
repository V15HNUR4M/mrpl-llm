import { fetchClient, API_BASE_URL, getAuthToken } from './client';

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

export interface GeneratedFileMetadata {
  file_id: string;
  filename: string;
  size_bytes?: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  agent_id?: string;
  created_at: string;
  metadata?: Record<string, any>;
  metadata_?: Record<string, any>;
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
  
  deleteConversation: (id: string): Promise<void> =>
    fetchClient<void>(`/conversations/${id}`, {
      method: 'DELETE',
    }),
  
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
    }),

  downloadGeneratedFile: async (fileId: string, filename: string): Promise<void> => {
    const token = getAuthToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(`${API_BASE_URL}/files/download/${fileId}`, { headers });
    if (!res.ok) {
      throw new Error(`Failed to download file: ${res.statusText}`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }
};
