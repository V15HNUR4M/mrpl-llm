import { fetchClient, API_BASE_URL, getAuthToken } from './client';

export interface Agent {
  agent_id: string;
  name: string;
  description: string;
  version: string;
  status: 'enabled' | 'disabled';
}

export const agentsApi = {
  getAgents: (): Promise<Agent[]> => fetchClient<Agent[]>('/agents'),
  
  // Custom fetch to handle streaming explicitly from React hooks
  createStreamEventSource: (agentId: string, conversationId: string, message: string): Promise<Response> => {
    return fetch(`${API_BASE_URL}/agents/${agentId}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      body: JSON.stringify({ conversation_id: conversationId, message })
    });
  },

  getActiveGeneration: (conversationId?: string): Promise<{ active: boolean; generation: any; events?: any[] }> => {
    let url = '/agents/generations/active';
    if (conversationId) {
      url += `?conversation_id=${encodeURIComponent(conversationId)}`;
    }
    return fetchClient<{ active: boolean; generation: any; events?: any[] }>(url);
  },

  stopGeneration: (generationId: string): Promise<{ status: string; message: string }> => {
    return fetchClient<{ status: string; message: string }>(`/agents/generations/${generationId}/stop`, {
      method: 'POST'
    });
  }
};
