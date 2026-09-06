import { fetchClient } from './client';

export interface DependencyHealth {
  status: string;
  latency_ms?: number;
  details?: Record<string, any>;
}

export interface HealthStatus {
  status: string;
  liveness: boolean;
  readiness: boolean;
  timestamp: string;
  dependencies: Record<string, DependencyHealth>;
}

export interface MetricsResponse {
  counters: Record<string, number>;
  gauges: Record<string, number>;
  average_latencies_ms: Record<string, number>;
}

export interface TelemetryEvent {
  id: string;
  timestamp: string;
  event_type: string;
  component: string;
  severity: string;
  user_id?: string;
  request_id?: string;
  correlation_id?: string;
  session_id?: string;
  span_id?: string;
  trace_id?: string;
  duration_ms?: number;
  status?: string;
  error_type?: string;
  metadata?: Record<string, any>;
}

export const observabilityApi = {
  getHealth: (): Promise<HealthStatus> => 
    fetchClient<HealthStatus>('/observability/health'),

  getMetrics: (): Promise<MetricsResponse> => 
    fetchClient<MetricsResponse>('/observability/metrics'),

  getEvents: (limit: number = 20, component?: string): Promise<TelemetryEvent[]> => {
    let url = `/observability/events?limit=${limit}`;
    if (component) {
      url += `&component=${encodeURIComponent(component)}`;
    }
    return fetchClient<TelemetryEvent[]>(url);
  },

  getEventById: (id: string): Promise<TelemetryEvent> =>
    fetchClient<TelemetryEvent>(`/observability/events/${id}`),
};
