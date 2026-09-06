import { fetchClient } from './client';

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
  getConversations: (): Promise<Conversation[]> => fetchClient<Conversation[]>('/conversations'),
  
  createConversation: (title: string): Promise<Conversation> => 
    fetchClient<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title })
    }),
    
  getConversation: (id: string): Promise<Conversation> => fetchClient<Conversation>(`/conversations/${id}`),
  
  getMessages: (conversationId: string): Promise<Message[]> => 
    fetchClient<Message[]>(`/conversations/${conversationId}/messages`),
    
  addMessage: (conversationId: string, role: string, content: string): Promise<Message> =>
    fetchClient<Message>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ role, content })
    })
};
