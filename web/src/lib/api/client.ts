const BASE = '/api/v1';

export async function api<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`);
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
