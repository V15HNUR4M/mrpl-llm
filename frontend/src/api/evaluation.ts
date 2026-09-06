import { fetchClient } from './client';

export interface CategorySummary {
  total: number;
  passed: number;
  failed: number;
  error: number;
  pass_rate: number;
  avg_latency_ms: number;
}

export interface EvaluationSummary {
  run_id: string;
  dataset_version: string;
  timestamp: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  error_cases: number;
  pass_rate: number;
  category_summaries: Record<string, CategorySummary>;
  metrics: Record<string, number>;
  latency_p50_ms: number;
  latency_p95_ms: number;
  threshold_violations: string[];
  model?: string;
  provider?: string;
}

export interface LatestEvaluationResponse {
  status: string;
  message?: string;
  summary: EvaluationSummary | null;
}

export interface BenchmarkDatasetInfo {
  dataset_id: string;
  version: string;
  description: string;
  total_cases: number;
  cases: Array<{
    case_id: string;
    category: string;
    name: string;
    description: string;
    is_adversarial: boolean;
  }>;
}

export const evaluationApi = {
  getLatest: (): Promise<LatestEvaluationResponse> =>
    fetchClient<LatestEvaluationResponse>('/evaluation/latest'),

  getDataset: (): Promise<BenchmarkDatasetInfo> =>
    fetchClient<BenchmarkDatasetInfo>('/evaluation/dataset'),

  runBenchmark: (): Promise<EvaluationSummary> =>
    fetchClient<EvaluationSummary>('/evaluation/run', {
      method: 'POST',
    }),
};
