import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Observability } from './Observability';
import * as obsApiModule from '../api/observability';

vi.mock('../api/observability', () => ({
  observabilityApi: {
    getHealth: vi.fn(),
    getMetrics: vi.fn(),
    getEvents: vi.fn(),
    getEventById: vi.fn(),
  },
}));

describe('Observability UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders health banner and status', async () => {
    vi.spyOn(obsApiModule.observabilityApi, 'getHealth').mockResolvedValue({
      status: 'healthy',
      liveness: true,
      readiness: true,
      timestamp: new Date().toISOString(),
      dependencies: { database: { status: 'healthy', latency_ms: 1.2 } },
    });
    vi.spyOn(obsApiModule.observabilityApi, 'getMetrics').mockResolvedValue({
      counters: { model_requests_total: 10, persisted_events_total: 25 },
      gauges: {},
      average_latencies_ms: { model_gateway_latency_ms: 120.5 },
    });
    vi.spyOn(obsApiModule.observabilityApi, 'getEvents').mockResolvedValue([]);

    render(<Observability />);

    expect(await screen.findByText(/Observability & Telemetry/i)).toBeInTheDocument();
    expect(await screen.findByText(/System Status: HEALTHY/i)).toBeInTheDocument();
    expect(screen.getByText('120.5 ms')).toBeInTheDocument();
  });

  it('renders events list with telemetry records', async () => {
    vi.spyOn(obsApiModule.observabilityApi, 'getHealth').mockResolvedValue({
      status: 'healthy',
      liveness: true,
      readiness: true,
      timestamp: new Date().toISOString(),
      dependencies: {},
    });
    vi.spyOn(obsApiModule.observabilityApi, 'getMetrics').mockResolvedValue({
      counters: {},
      gauges: {},
      average_latencies_ms: {},
    });
    vi.spyOn(obsApiModule.observabilityApi, 'getEvents').mockResolvedValue([
      {
        id: 'evt-1',
        timestamp: new Date().toISOString(),
        event_type: 'model.generation.completed',
        component: 'model_gateway',
        severity: 'INFO',
        status: 'success',
        duration_ms: 350,
        correlation_id: 'corr-xyz-123',
      },
    ]);

    render(<Observability />);

    expect(await screen.findByText('model.generation.completed')).toBeInTheDocument();
    expect(screen.getByText('model_gateway')).toBeInTheDocument();
    expect(screen.getByText('350 ms')).toBeInTheDocument();
    expect(screen.getByText('corr-xyz-123')).toBeInTheDocument();
  });
});
