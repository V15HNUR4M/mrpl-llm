import React, { useState, useEffect } from 'react';
import { 
  Bot, 
  RefreshCw, 
  Cpu, 
  CheckCircle2, 
  PlayCircle, 
  AlertCircle, 
  XCircle, 
  Wrench, 
  FileSpreadsheet, 
  FileText, 
  GitFork 
} from 'lucide-react';
import { agentsApi, type Agent, type AgentActivity } from '../api/agents';
import styles from './Agents.module.css';

export const Agents: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activity, setActivity] = useState<AgentActivity[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [agentsData, activityData] = await Promise.all([
        agentsApi.getAgents().catch(() => []),
        agentsApi.getActivity(20).catch(() => [])
      ]);
      setAgents(agentsData);
      setActivity(activityData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const getAgentIcon = (agentId: string) => {
    if (agentId === 'excel_agent') return <FileSpreadsheet size={20} color="#10b981" />;
    if (agentId === 'document_agent') return <FileText size={20} color="#3b82f6" />;
    if (agentId === 'task_router') return <GitFork size={20} color="#8b5cf6" />;
    return <Bot size={20} color="#6366f1" />;
  };

  const getStatusBadge = (status: string) => {
    const s = (status || '').toLowerCase();
    if (s === 'running') {
      return (
        <span className={`${styles.badge} ${styles.badgeRunning}`}>
          <PlayCircle size={12} /> Running
        </span>
      );
    }
    if (s === 'ready' || s === 'enabled') {
      return (
        <span className={`${styles.badge} ${styles.badgeReady}`}>
          <CheckCircle2 size={12} /> Ready
        </span>
      );
    }
    if (s === 'disabled') {
      return (
        <span className={`${styles.badge} ${styles.badgeDisabled}`}>
          <XCircle size={12} /> Disabled
        </span>
      );
    }
    return (
      <span className={`${styles.badge} ${styles.badgeError}`}>
        <AlertCircle size={12} /> {status}
      </span>
    );
  };

  const readyCount = agents.filter(a => a.status === 'ready' || (a.is_enabled && a.status !== 'running' && a.status !== 'disabled')).length;
  const runningCount = agents.filter(a => a.status === 'running').length;
  const disabledCount = agents.filter(a => a.status === 'disabled' || a.is_enabled === false).length;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Cpu size={26} color="#3b82f6" />
          <h1>Agents Management & Orchestration</h1>
        </div>
        <button className={styles.refreshBtn} onClick={fetchData} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'spinner' : ''} />
          Refresh
        </button>
      </div>

      {/* Stats Summary */}
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Registered Components</span>
          <span className={styles.statValue}>{agents.length}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Ready Agents</span>
          <span className={styles.statValue} style={{ color: '#10b981' }}>{readyCount}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Active Executions</span>
          <span className={styles.statValue} style={{ color: runningCount > 0 ? '#3b82f6' : 'inherit' }}>
            {runningCount}
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Disabled Components</span>
          <span className={styles.statValue} style={{ color: disabledCount > 0 ? '#9ca3af' : 'inherit' }}>
            {disabledCount}
          </span>
        </div>
      </div>

      {/* Registered Agents Grid */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>Active Agents & Orchestrators</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
            Showing {agents.length} verified system components
          </span>
        </div>

        <div className={styles.agentsGrid}>
          {agents.map((agent) => (
            <div key={agent.agent_id} className={styles.agentCard}>
              <div className={styles.agentCardHeader}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  {getAgentIcon(agent.agent_id)}
                  <div className={styles.agentTitleArea}>
                    <h3 className={styles.agentName}>{agent.name}</h3>
                    <span className={styles.agentId}>{agent.agent_id} • v{agent.version}</span>
                  </div>
                </div>
                {getStatusBadge(agent.status)}
              </div>

              <p className={styles.agentDescription}>{agent.description}</p>

              <div className={styles.badgesRow}>
                <span className={`${styles.badge} ${styles.badgeType}`}>
                  {agent.type || 'Specialist'}
                </span>
                {agent.capabilities?.map((cap) => (
                  <span key={cap} className={styles.badge} style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6' }}>
                    {cap.replace('_', ' ')}
                  </span>
                ))}
              </div>

              <div className={styles.modelProviderInfo}>
                <div className={styles.modelRow}>
                  <span>Target Model:</span>
                  <strong>{agent.model || 'System Local Model'}</strong>
                </div>
                <div className={styles.modelRow}>
                  <span>Gateway Provider:</span>
                  <span style={{ textTransform: 'uppercase', fontSize: '0.75rem' }}>
                    {agent.provider || 'Local Gateway'}
                  </span>
                </div>
              </div>

              {agent.tools && agent.tools.length > 0 && (
                <div className={styles.toolsSection}>
                  <span className={styles.toolsLabel}>
                    <Wrench size={12} style={{ display: 'inline', marginRight: 4 }} />
                    Available Tools ({agent.tools.length})
                  </span>
                  <div className={styles.toolsList}>
                    {agent.tools.map((tool) => (
                      <span key={tool} className={styles.toolChip}>
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Recent Agent Activity */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>Recent Agent Executions</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
            Showing latest {activity.length} real executions from telemetry
          </span>
        </div>

        <table className={styles.activityTable}>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Agent</th>
              <th>Task</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Correlation / Request</th>
            </tr>
          </thead>
          <tbody>
            {activity.length === 0 ? (
              <tr>
                <td colSpan={6} className={styles.emptyState}>
                  No recent agent executions recorded yet.
                </td>
              </tr>
            ) : (
              activity.map((item) => (
                <tr key={item.id}>
                  <td style={{ color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                    {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <td>
                    <strong>{item.agent}</strong>
                  </td>
                  <td>{item.task}</td>
                  <td>
                    <span className={`${styles.badge} ${
                      item.status === 'completed' ? styles.badgeReady :
                      item.status === 'running' ? styles.badgeRunning :
                      item.status === 'denied' ? styles.badgeDisabled : styles.badgeError
                    }`}>
                      {item.status}
                    </span>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {item.duration_ms !== undefined && item.duration_ms !== null ? `${item.duration_ms} ms` : '—'}
                  </td>
                  <td>
                    <span className={styles.corrCode}>
                      {item.correlation_id ? item.correlation_id.substring(0, 16) : '—'}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
