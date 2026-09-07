import { fetchClient, API_BASE_URL, getAuthToken } from './client';

export interface Agent {
  agent_id: string;
  name: string;
  description: string;
  version: string;
  status: string; // 'ready' | 'running' | 'disabled' | 'error' | 'unavailable' | 'enabled'
  is_enabled?: boolean;
  type?: string;
  capabilities?: string[];
  tools?: string[];
  model?: string;
  provider?: string;
  context_policy?: Record<string, any>;
}

export interface AgentActivity {
  id: string;
  timestamp: string;
  agent: string;
  agent_id: string;
  task: string;
  status: string;
  duration_ms?: number;
  correlation_id?: string;
  details?: Record<string, any>;
}

export const agentsApi = {
  getAgents: (): Promise<Agent[]> => fetchClient<Agent[]>('/agents'),
  getActivity: (limit: number = 20): Promise<AgentActivity[]> => 
    fetchClient<AgentActivity[]>(`/agents/activity?limit=${limit}`),
  
  // Custom fetch to handle streaming explicitly from React hooks
  createStreamEventSource: (
    agentId: string,
    conversationId: string,
    message: string,
    fileId?: string,
    fileType?: string,
    filename?: string
  ): Promise<Response> => {
    return fetch(`${API_BASE_URL}/agents/${agentId}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
        file_id: fileId,
        file_type: fileType,
        filename: filename
      })
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
