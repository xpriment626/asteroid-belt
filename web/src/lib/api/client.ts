const BASE = '/api/v1';

export async function api<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`);
  return (await r.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on POST ${path}`);
  return (await r.json()) as T;
}

export type PoolSummary = {
  address: string;
  name: string | null;
  bin_step: number | null;
  bars_count: number;
};

export type PoolDetail = PoolSummary & {
  meta: Record<string, unknown>;
};

export type Bar = {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume_x: number;
  volume_y: number;
};

// --- Trial / iteration / run types ---

export type TrialSummary = {
  trial: string;
  iteration_count: number;
  success_count: number;
  error_count: number;
  degenerate_count: number;
  best_iteration: number | null;
  best_score: number | null;
  score_metric: string | null;
  started_at: number | null;
  last_updated: number | null;
};

export type IterationSummary = {
  iteration: number;
  timestamp: number;
  code_hash: string;
  score: number | null;
  score_metric: string;
  rebalance_count: number;
  error: string | null;
  has_trajectory: boolean;
  primitives: Record<string, number>;
};

export type TrialDetail = TrialSummary & {
  iterations: IterationSummary[];
};

export type IterationDetail = {
  iteration: number;
  timestamp: number;
  code_hash: string;
  score: number | null;
  score_metric: string;
  rebalance_count: number;
  error: string | null;
  has_trajectory: boolean;
  primitives: Record<string, number>;
  strategy_code: string;
};

export type TrajectoryRow = {
  ts: number;
  price: number;
  active_bin: number;
  position_value_usd: number;
  hodl_value_usd: number;
  fees_value_usd: number;
  il_cumulative: number;
  in_range: boolean;
  capital_idle_usd: number;
};

export type RunStatus = {
  run_id: string;
  trial: string;
  state: 'running' | 'done' | 'failed';
  iterations_completed: number;
  budget: number;
  started_at: number;
  ended_at: number | null;
  error: string | null;
};

export type RunStartRequest = {
  pool: string;
  trial: string;
  budget?: number;
  objective?: string;
  initial_x?: number;
  initial_y?: number;
};
