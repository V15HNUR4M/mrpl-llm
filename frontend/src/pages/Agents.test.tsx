import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Agents } from './Agents';
import * as agentsApiModule from '../api/agents';

vi.mock('../api/agents', () => ({
  agentsApi: {
    getAgents: vi.fn(),
    getActivity: vi.fn(),
  },
}));

describe('Agents Management UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders registered agents, tools, models and status badges', async () => {
    vi.spyOn(agentsApiModule.agentsApi, 'getAgents').mockResolvedValue([
      {
        agent_id: 'general_agent',
        name: 'General Agent',
        description: 'Plant system assistant',
        version: '1.0',
        status: 'ready',
        is_enabled: true,
        type: 'general',
        capabilities: ['text_generation', 'rag_retrieval'],
        tools: ['search_documents', 'get_document'],
        model: 'llama3.2:latest',
        provider: 'ollama',
      },
      {
        agent_id: 'excel_agent',
        name: 'Excel Agent',
        description: 'Deterministic spreadsheet specialist',
        version: '1.0',
        status: 'running',
        is_enabled: true,
        type: 'specialist',
        capabilities: ['text_generation', 'excel_operations'],
        tools: ['read_workbook', 'write_cells', 'create_workbook'],
        model: 'llama3.2:latest',
        provider: 'ollama',
      },
      {
        agent_id: 'task_router',
        name: 'Task Router',
        description: 'Deterministic query classifier',
        version: '1.0',
        status: 'ready',
        is_enabled: true,
        type: 'orchestrator',
        capabilities: ['intent_classification'],
        tools: ['route_agent'],
        model: 'Deterministic Rule Engine',
        provider: 'system',
      },
      {
        agent_id: 'disabled_agent',
        name: 'Disabled Agent',
        description: 'Disabled component',
        version: '1.0',
        status: 'disabled',
        is_enabled: false,
        type: 'specialist',
        capabilities: ['text_generation'],
        tools: [],
        model: 'llama3.2:latest',
        provider: 'ollama',
      }
    ]);

    vi.spyOn(agentsApiModule.agentsApi, 'getActivity').mockResolvedValue([
      {
        id: 'act-1',
        timestamp: new Date().toISOString(),
        agent: 'Excel Agent',
        agent_id: 'excel_agent',
        task: 'Spreadsheet generation',
        status: 'completed',
        duration_ms: 245,
        correlation_id: 'corr-excel-123',
      }
    ]);

    render(<Agents />);

    // Check header
    expect(await screen.findByText(/Agents Management & Orchestration/i)).toBeInTheDocument();

    // Check agents rendered
    expect(screen.getByText('General Agent')).toBeInTheDocument();
    expect(screen.getAllByText('Excel Agent').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Task Router')).toBeInTheDocument();
    expect(screen.getByText('Disabled Agent')).toBeInTheDocument();

    // Check tools rendered
    expect(screen.getByText('read_workbook')).toBeInTheDocument();
    expect(screen.getByText('search_documents')).toBeInTheDocument();

    // Check status badges
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Disabled')).toBeInTheDocument();

    // Check activity table row
    expect(screen.getByText('Spreadsheet generation')).toBeInTheDocument();
    expect(screen.getByText('245 ms')).toBeInTheDocument();
    expect(screen.getByText('corr-excel-123')).toBeInTheDocument();
  });

  it('handles empty activity feed and triggers refresh', async () => {
    vi.spyOn(agentsApiModule.agentsApi, 'getAgents').mockResolvedValue([]);
    vi.spyOn(agentsApiModule.agentsApi, 'getActivity').mockResolvedValue([]);

    render(<Agents />);

    expect(await screen.findByText(/No recent agent executions recorded yet/i)).toBeInTheDocument();

    const refreshBtn = screen.getByRole('button', { name: /refresh/i });
    fireEvent.click(refreshBtn);

    expect(agentsApiModule.agentsApi.getAgents).toHaveBeenCalledTimes(2);
  });
});
