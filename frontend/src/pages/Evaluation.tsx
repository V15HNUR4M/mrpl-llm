import React, { useState, useEffect } from 'react';
import { RefreshCw, Play, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';
import { evaluationApi, type EvaluationSummary } from '../api/evaluation';
import { useAuth } from '../context/AuthContext';
import styles from './Evaluation.module.css';

export const Evaluation: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLatest = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await evaluationApi.getLatest();
      setSummary(res.summary);
    } catch (err: any) {
      setError(err?.message || 'Failed to load evaluation results');
    } finally {
      setLoading(false);
    }
  };

  const handleRunBenchmark = async () => {
    if (!isAdmin || running) return;
    try {
      setRunning(true);
      setError(null);
      const result = await evaluationApi.runBenchmark();
      setSummary(result);
    } catch (err: any) {
      setError(err?.message || 'Failed to execute benchmark run');
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    fetchLatest();
  }, []);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1>Testing & Evaluation</h1>
          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginTop: 4 }}>
            Deterministic benchmark suite measuring grounding, citations, security, and hallucination refusal.
          </div>
        </div>
        <div className={styles.actionRow}>
          <button className={styles.refreshBtn} onClick={fetchLatest} disabled={loading || running}>
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
            Refresh
          </button>
          {isAdmin && (
            <button className={styles.runBtn} onClick={handleRunBenchmark} disabled={running}>
              <Play size={14} />
              {running ? 'Running Benchmark...' : 'Run Benchmark'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ padding: 'var(--spacing-3)', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)' }}>
          {error}
        </div>
      )}

      {summary ? (
        <>
          <div className={styles.summaryBanner}>
            <div>
              <div className={styles.summaryTitle}>
                Benchmark Run: <code>{summary.run_id}</code>
              </div>
              <div className={styles.summarySub}>
                Dataset: {summary.dataset_version} • Model: {summary.model || 'llama3.2:latest'} • Provider: {summary.provider || 'ollama'} • {new Date(summary.timestamp).toLocaleString()}
              </div>
            </div>
            <div>
              <span className={`${styles.badge} ${summary.pass_rate >= 0.9 && summary.error_cases === 0 ? styles.badgePass : styles.badgeFail}`}>
                {summary.pass_rate >= 0.9 && summary.error_cases === 0 ? 'BENCHMARK PASS' : 'BENCHMARK FAIL'}
              </span>
            </div>
          </div>

          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Total Cases</span>
              <span className={styles.statValue}>{summary.total_cases}</span>
              <span className={styles.statSub}>10 Categories</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Pass Rate</span>
              <span className={styles.statValue}>{Math.round(summary.pass_rate * 100)}%</span>
              <span className={styles.statSub}>{summary.passed_cases} passed / {summary.failed_cases} failed</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Latency p50</span>
              <span className={styles.statValue}>{summary.latency_p50_ms} ms</span>
              <span className={styles.statSub}>Median turnaround</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Latency p95</span>
              <span className={styles.statValue}>{summary.latency_p95_ms} ms</span>
              <span className={styles.statSub}>95th percentile</span>
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Category Breakdown</h2>
            <div className={styles.tableContainer}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Cases</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Pass Rate</th>
                    <th>Avg Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.category_summaries || {}).map(([cat, data]) => (
                    <tr key={cat}>
                      <td style={{ fontWeight: 500 }}>{cat}</td>
                      <td>{data.total}</td>
                      <td>{data.passed}</td>
                      <td>{data.failed}</td>
                      <td>
                        <span className={`${styles.badge} ${data.pass_rate >= 0.9 ? styles.badgePass : styles.badgeFail}`}>
                          {Math.round(data.pass_rate * 100)}%
                        </span>
                      </td>
                      <td>{data.avg_latency_ms} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Deterministic Metrics</h2>
            <div className={styles.tableContainer}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Measured Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.metrics || {}).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ fontFamily: 'monospace' }}>{k}</td>
                      <td style={{ fontWeight: 600 }}>{typeof v === 'number' ? v.toFixed(4) : v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Threshold Violations</h2>
            {summary.threshold_violations && summary.threshold_violations.length > 0 ? (
              <ul className={styles.violationsList}>
                {summary.threshold_violations.map((v, i) => (
                  <li key={i} className={styles.violationItem}>
                    <AlertTriangle size={16} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }} />
                    {v}
                  </li>
                ))}
              </ul>
            ) : (
              <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
                <CheckCircle2 size={16} color="#22c55e" style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }} />
                No threshold violations detected.
              </div>
            )}
          </div>
        </>
      ) : (
        <div className={styles.emptyState}>
          <ShieldCheck size={36} style={{ marginBottom: 8, opacity: 0.5 }} />
          <h3>No Evaluation Runs Found</h3>
          <p>Click "Run Benchmark" (Admin required) to execute the MRPL Benchmark V1 suite.</p>
        </div>
      )}
    </div>
  );
};
