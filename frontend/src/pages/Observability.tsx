import React, { useState, useEffect } from 'react';
import { RefreshCw, Activity, CheckCircle, AlertTriangle } from 'lucide-react';
import { 
  observabilityApi, 
  type HealthStatus, 
  type MetricsResponse, 
  type TelemetryEvent 
} from '../api/observability';
import styles from './Observability.module.css';

export const Observability: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedEvent, setSelectedEvent] = useState<TelemetryEvent | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [h, m, evts] = await Promise.all([
        observabilityApi.getHealth().catch(() => null),
        observabilityApi.getMetrics().catch(() => null),
        observabilityApi.getEvents(25).catch(() => [])
      ]);
      setHealth(h);
      setMetrics(m);
      setEvents(evts);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status?: string, severity?: string) => {
    const st = (status || severity || '').toLowerCase();
    if (st === 'success') return <span className={`${styles.badge} ${styles.badgeSuccess}`}>Success</span>;
    if (st === 'failed' || st === 'error') return <span className={`${styles.badge} ${styles.badgeError}`}>Failed</span>;
    if (st === 'denied' || st === 'warn') return <span className={`${styles.badge} ${styles.badgeWarning}`}>Denied</span>;
    if (st === 'timed_out' || st === 'timeout') return <span className={`${styles.badge} ${styles.badgeWarning}`}>Timeout</span>;
    if (st === 'cancelled') return <span className={`${styles.badge} ${styles.badgeInfo}`}>Cancelled</span>;
    return <span className={`${styles.badge} ${styles.badgeInfo}`}>{status || severity || 'Info'}</span>;
  };

  const getHealthIndicator = () => {
    if (!health) return <div className={`${styles.statusIndicator} ${styles.degraded}`} />;
    if (health.status === 'healthy') return <div className={`${styles.statusIndicator} ${styles.healthy}`} />;
    return <div className={`${styles.statusIndicator} ${styles.degraded}`} />;
  };

  const totalRequests = metrics?.counters?.['total_operations'] ??
                        ((metrics?.counters?.['model_requests_total'] || 0) +
                        (metrics?.counters?.['tool_calls_total'] || 0) +
                        (metrics?.counters?.['workflow_runs_total'] || 0) +
                        (metrics?.counters?.['agent_events_total'] || 0) +
                        (metrics?.counters?.['rag_queries_total'] || 0));

  const totalFailures = metrics?.counters?.['total_failures'] ??
                        ((metrics?.counters?.['model_failures_total'] || 0) +
                        (metrics?.counters?.['tool_failures_total'] || 0) +
                        (metrics?.counters?.['workflow_failures_total'] || 0) +
                        (metrics?.counters?.['agent_failures_total'] || 0));

  const rawLatency = metrics?.average_latencies_ms?.['model_gateway_latency_ms'] ?? 
                     metrics?.average_latencies_ms?.['model_latency_ms'] ?? 0;
  const avgLatency = rawLatency > 0 ? Math.round(rawLatency * 10) / 10 : 0;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Activity size={24} color="#3b82f6" />
          <h1>Observability & Telemetry</h1>
        </div>
        <button className={styles.refreshBtn} onClick={fetchData} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinner' : ''} />
          Refresh
        </button>
      </div>

      {/* Health Overview Banner */}
      <div className={styles.healthBanner}>
        <div className={styles.healthStatus}>
          {getHealthIndicator()}
          <div>
            <strong>System Status: {health?.status?.toUpperCase() || 'CONNECTING...'}</strong>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
              Liveness: {health?.liveness ? 'Active' : 'Down'} | Readiness: {health?.readiness ? 'Ready' : 'Not Ready'}
            </div>
          </div>
        </div>
        <div className={styles.depsList}>
          {health?.dependencies && Object.entries(health.dependencies).map(([k, v]) => (
            <div key={k} className={styles.depItem}>
              {v.status === 'healthy' ? <CheckCircle size={14} color="#10b981" /> : <AlertTriangle size={14} color="#f59e0b" />}
              <span>{k}: {v.status}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Metrics Stat Cards */}
      <div className={styles.grid}>
        <div className={styles.card}>
          <span className={styles.cardLabel}>Total Operations</span>
          <span className={styles.cardValue}>{totalRequests}</span>
        </div>
        <div className={styles.card}>
          <span className={styles.cardLabel}>Failures / Errors</span>
          <span className={styles.cardValue} style={{ color: totalFailures > 0 ? '#ef4444' : 'inherit' }}>
            {totalFailures}
          </span>
        </div>
        <div className={styles.card}>
          <span className={styles.cardLabel}>Avg Model Latency</span>
          <span className={styles.cardValue}>{avgLatency ? `${avgLatency} ms` : '—'}</span>
        </div>
        <div className={styles.card}>
          <span className={styles.cardLabel}>Persisted Events</span>
          <span className={styles.cardValue}>{metrics?.counters?.['persisted_events_total'] ?? events.length}</span>
        </div>
      </div>

      {/* Recent Telemetry Executions Table */}
      <div className={styles.eventsSection}>
        <div className={styles.eventsHeader}>
          <span className={styles.eventsTitle}>Recent Telemetry Events</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
            Showing latest {events.length} records
          </span>
        </div>

        <table className={styles.table}>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Component</th>
              <th>Event Type</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Correlation / Request</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: 32 }}>
                  No telemetry events recorded yet.
                </td>
              </tr>
            ) : (
              events.map((evt) => (
                <tr 
                  key={evt.id} 
                  onClick={() => setSelectedEvent(evt)} 
                  style={{ cursor: 'pointer' }}
                  title="Click to inspect event details"
                >
                  <td>{new Date(evt.timestamp).toLocaleTimeString()}</td>
                  <td><strong>{evt.component}</strong></td>
                  <td><code>{evt.event_type}</code></td>
                  <td>{getStatusBadge(evt.status, evt.severity)}</td>
                  <td>{evt.duration_ms != null ? `${evt.duration_ms} ms` : '—'}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                    {evt.correlation_id || evt.request_id || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Detail Inspector Drawer/Modal */}
      {selectedEvent && (
        <div 
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center',
            zIndex: 1000
          }}
          onClick={() => setSelectedEvent(null)}
        >
          <div 
            style={{
              background: 'var(--color-surface-base)', padding: 24, borderRadius: 12, maxWidth: 600, width: '90%',
              border: '1px solid var(--color-border-subtle)', boxShadow: '0 8px 32px rgba(0,0,0,0.3)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>Event Details</h3>
              <button 
                onClick={() => setSelectedEvent(null)} 
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: 16 }}
              >
                ✕
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '0.9rem' }}>
              <div><strong>ID:</strong> <code>{selectedEvent.id}</code></div>
              <div><strong>Event:</strong> <code>{selectedEvent.event_type}</code></div>
              <div><strong>Component:</strong> {selectedEvent.component}</div>
              <div><strong>Status:</strong> {selectedEvent.status || 'N/A'}</div>
              <div><strong>Duration:</strong> {selectedEvent.duration_ms != null ? `${selectedEvent.duration_ms} ms` : 'N/A'}</div>
              {selectedEvent.error_type && <div><strong>Error Type:</strong> <code>{selectedEvent.error_type}</code></div>}
              <div><strong>Metadata (Sanitized):</strong></div>
              <pre style={{ background: 'var(--color-surface-sunken, #111)', padding: 12, borderRadius: 8, overflowX: 'auto', fontSize: '0.8rem' }}>
                {JSON.stringify(selectedEvent.metadata || {}, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
