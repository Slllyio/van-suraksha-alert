// Typed fetchers for the v3 Python backend (proxied via Vite to :8790).
// Keep payload shapes loose — v3 JSON schemas occasionally drift; only extract
// the fields each component actually uses.

export interface V17Cell {
  cell_id: string | number;
  lat: number;
  lon: number;
  band: 'CRITICAL' | 'ALERT' | 'WATCH' | string;
  risk_score?: number;
  trust_tier?: 'HIGH' | 'MEDIUM' | 'LOW';
  stage_a_risk?: number;
  division?: string;
  hawkes_lambda?: number;
  [key: string]: unknown;
}

export interface V17Payload {
  target_date?: string;
  generated_at?: string;
  cells: V17Cell[];
  meta?: Record<string, unknown>;
}

export interface DivisionSummary {
  division: string;
  critical: number;
  alert: number;
  watch: number;
  beats?: number;
  hawkes_lambda?: number;
  trust_tier?: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface ValidationRow {
  date: string;
  predicted: number;
  observed: number;
  caught: number;
  recall_pct: number;
  trust?: 'HIGH' | 'MEDIUM' | 'LOW';
  notes?: string;
}

export interface ModelTransparency {
  model_version: string;
  recall_top5_pct?: number;
  precision_critical_pct?: number;
  per_division_coverage?: { covered: number; total: number };
  feature_importance?: { name: string; gain: number }[];
  trust_tiers?: { tier: string; description: string }[];
  weaknesses?: string[];
}

export interface ViirsFire {
  lat: number;
  lon: number;
  date: string;
  brightness?: number;
  confidence?: string;
  frp?: number;
}

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal });
  if (!res.ok) {
    throw new Error(`GET ${path} → HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  ignitionV17: (date?: string, signal?: AbortSignal) =>
    getJSON<V17Payload>(
      `/api/ignition-v17${date ? `?date=${encodeURIComponent(date)}` : ''}`,
      signal,
    ),

  divisionOverview: (signal?: AbortSignal) =>
    getJSON<DivisionSummary[]>('/api/division-overview', signal),

  seasonValidation: (signal?: AbortSignal) =>
    getJSON<ValidationRow[]>('/api/season-validation', signal),

  modelTransparency: (signal?: AbortSignal) =>
    getJSON<ModelTransparency>('/api/model-transparency', signal),

  viirsFires: (from?: string, to?: string, signal?: AbortSignal) => {
    const qs = new URLSearchParams();
    if (from) qs.set('from', from);
    if (to) qs.set('to', to);
    return getJSON<ViirsFire[]>(`/api/viirs-fires?${qs.toString()}`, signal);
  },

  healthz: (signal?: AbortSignal) =>
    getJSON<{ ok: boolean; checks?: Record<string, unknown> }>('/api/healthz', signal),
};

// Generic hook-friendly wrapper
export function fetchWithTimeout<T>(
  promise: Promise<T>,
  ms = 15000,
): Promise<T> {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), ms);
  return promise.finally(() => clearTimeout(t));
}
