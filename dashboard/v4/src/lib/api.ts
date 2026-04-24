// Typed fetchers for the v3 Python backend, v2 API namespace.
// Every v2 response is `{ data, meta, links? }`; errors are
// `{ error: { code, message, details? } }` with semantic HTTP status.
// See dashboard/v3/openapi.yaml for the full contract.
//
// Canonical schema types come from apiSchema.ts (auto-generated from the
// OpenAPI spec via `npm run codegen`, wired as prebuild). We re-export a
// few under their historic names for incremental migration; new code
// should prefer `schemas['V17Cell']` etc. directly.

import type { components } from './apiSchema';

type Schemas = components['schemas'];

/** Re-exports of the canonical OpenAPI-generated schemas. Keeping the
 *  aliases lets the rest of the codebase upgrade incrementally. */
export type V17CellSchema = Schemas['V17Cell'];
export type DivisionSummarySchema = Schemas['DivisionSummary'];
export type ValidationRowSchema = Schemas['ValidationRow'];
export type ModelTransparencySchema = Schemas['ModelTransparency'];
export type ViirsFireSchema = Schemas['ViirsFire'];
export type PaginationLinksSchema = Schemas['PaginationLinks'];
export type ApiErrorSchema = Schemas['ApiError']['error'];

export interface V17Cell {
  cell_id: string | number;
  lat: number;
  lon: number;
  band: 'CRITICAL' | 'ALERT' | 'WATCH' | string;
  risk_score?: number;
  ignition_risk?: number;
  calibrated_risk?: number;
  rank?: number;
  trust_tier?: 'HIGH' | 'MEDIUM' | 'LOW';
  stage_a_risk?: number;
  division?: string;
  hawkes_lambda?: number;
  hawkes_n_recent_10km_7d?: number;
  [key: string]: unknown;
}

export interface V17Meta {
  total?: number;
  limit?: number;
  offset?: number;
  has_next?: boolean;
  next_cursor?: string | null;
  prediction_date?: string;
  model?: string;
  generated_at?: string;
}

export interface PaginationLinks {
  self?: string;
  next?: string;
  prev?: string;
  last?: string;
}

export interface Envelope<T, M = Record<string, unknown>> {
  data: T;
  meta?: M;
  links?: PaginationLinks;
}

export interface ApiErrorShape {
  code: string;
  message: string;
  details?: Array<{ field?: string; message?: string; code?: string }>;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: ApiErrorShape['details'];
  constructor(status: number, shape: ApiErrorShape) {
    super(shape.message || `HTTP ${status}`);
    this.status = status;
    this.code = shape.code;
    this.details = shape.details;
  }
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
  time?: string;
  brightness?: number;
  confidence?: string;
  satellite?: string;
  source?: string;
  division?: string;
  range?: string;
  beat?: string;
  frp?: number;
}

export interface ViirsMeta {
  total?: number;
  n_before_clip?: number;
  n_clipped?: number;
  latest_date?: string;
  date_range?: { from?: string; to?: string };
}

export type GeoJSONFeatureCollection = {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    properties?: Record<string, unknown>;
    geometry: unknown;
  }>;
};

async function getEnvelope<T, M = Record<string, unknown>>(
  path: string,
  signal?: AbortSignal,
): Promise<Envelope<T, M>> {
  const res = await fetch(path, { signal });
  const text = await res.text();
  let parsed: unknown;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    throw new ApiError(res.status, {
      code: 'invalid_json_response',
      message: `Non-JSON body from ${path} (HTTP ${res.status})`,
    });
  }
  if (!res.ok) {
    const body = parsed as { error?: ApiErrorShape } | null;
    const shape: ApiErrorShape = body?.error ?? {
      code: 'http_error',
      message: `HTTP ${res.status}`,
    };
    throw new ApiError(res.status, shape);
  }
  return parsed as Envelope<T, M>;
}

/** Lower-level fetcher that returns the raw envelope (data + meta + links). */
export async function getV2<T, M = Record<string, unknown>>(
  path: string,
  signal?: AbortSignal,
): Promise<Envelope<T, M>> {
  return getEnvelope<T, M>(path, signal);
}

/** Convenience wrapper that unwraps .data for callers who don't need meta. */
async function getData<T, M = Record<string, unknown>>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const env = await getEnvelope<T, M>(path, signal);
  return env.data;
}

export const api = {
  /**
   * Paginated v17 banded alerts.
   * @param date  Optional `YYYY-MM-DD`. Omit for latest.
   * @param limit 1-2000, default 500.
   * @param cursor Opaque cursor from a previous response's `meta.next_cursor`.
   */
  ignitionV17: (
    date?: string,
    opts?: { limit?: number; cursor?: string; signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    if (date) qs.set('date', date);
    if (opts?.limit) qs.set('limit', String(opts.limit));
    if (opts?.cursor) qs.set('cursor', opts.cursor);
    return getV2<V17Cell[], V17Meta>(
      `/api/v2/ignition-v17?${qs.toString()}`,
      opts?.signal,
    );
  },

  /** Load ALL v17 banded alerts by walking cursors. Use sparingly — ~2,600
   *  cells, ~350 KB on the wire. */
  async ignitionV17All(date?: string, signal?: AbortSignal): Promise<V17Cell[]> {
    const out: V17Cell[] = [];
    let cursor: string | undefined;
    for (;;) {
      const page = await api.ignitionV17(date, { limit: 2000, cursor, signal });
      out.push(...page.data);
      const next = page.meta?.next_cursor;
      if (!next) break;
      cursor = next;
    }
    return out;
  },

  divisionOverview: (signal?: AbortSignal) =>
    getData<DivisionSummary[]>('/api/v2/division-overview', signal),

  seasonValidation: (signal?: AbortSignal) =>
    getData<ValidationRow[]>('/api/v2/season-validation', signal),

  modelTransparency: (signal?: AbortSignal) =>
    getData<ModelTransparency>('/api/v2/model-transparency', signal),

  viirsFires: (from?: string, to?: string, signal?: AbortSignal) => {
    const qs = new URLSearchParams();
    if (from) qs.set('from', from);
    if (to) qs.set('to', to);
    return getV2<ViirsFire[], ViirsMeta>(
      `/api/v2/viirs-fires?${qs.toString()}`,
      signal,
    );
  },

  healthz: (signal?: AbortSignal) =>
    getData<{ ok: boolean } & Record<string, unknown>>(
      '/api/v2/healthz',
      signal,
    ),

  beatsBoundary: (signal?: AbortSignal) =>
    getData<GeoJSONFeatureCollection>('/api/v2/beats-boundary', signal),
};
