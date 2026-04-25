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

/** Legacy shape — kept for any callers outside DivisionsTab. */
export interface DivisionSummary {
  division: string;
  critical: number;
  alert: number;
  watch: number;
  beats?: number;
  hawkes_lambda?: number;
  trust_tier?: 'HIGH' | 'MEDIUM' | 'LOW';
}

/** Real shape returned by GET /api/v2/division-overview → .data.divisions */
export interface DivisionDetail {
  name: string;
  critical: number;
  alert: number;
  watch: number;
  total: number;
  mean_risk: number;
  max_risk: number;
  hawkes_high_pct: number;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  center_lat: number;
  center_lon: number;
  silent_in_danger: boolean;
  n_critical_organic: number;
  n_critical_floor_promoted: number;
  n_cold_start: number;
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

/** Historical-burn priors aggregated per v17 cell over the last 5 fire
 *  seasons (2021-2025). Used by Mitigation 2 (coverage diagnostic) +
 *  Mitigation 3 (interior-monitor override). See
 *  `docs/edge_bias_brutal_analysis.md`. */
export interface HistoricalBurnPrior {
  cell_id: string;
  lat: number;
  lon: number;
  total_fires_5y: number;
  n_seasons_burned: number;
  seasons_burned: number[];
}

export interface HistoricalBurnPriorMeta {
  seasons?: number[];
  served_min_seasons?: number;
  served_records?: number;
  source_file?: string;
  n_cells_3plus_seasons?: number;
  n_cells_5_seasons?: number;
}

/** Density-friendly point cloud for HeatmapLayer: `[lat, lon, weight]`
 *  per cell that had >=2 fire-season VIIRS detections in last 5y. */
export interface HistoricalBurnPoint {
  lat: number;
  lon: number;
  /** Weight = total fire-season VIIRS detections over 5y. */
  w: number;
}

export interface HistoricalBurnDensityMeta {
  seasons?: number[];
  filter?: string;
  n_points?: number;
  source_file?: string;
}

/** Per-cell fuel-load record from `/api/v2/fuel-load`. Derived from
 *  ESA WorldCover × Reddy et al (2019) reference loads (kg/m² × 10).
 *  Coarse approximation, NOT field-validated per cell. */
export interface FuelLoadRecord {
  cell_id: string;
  lat: number;
  lon: number;
  fuel_load_t_per_ha: number;
  sb40_dominant: string;        // "TL2", "GR1", "GR2", "SH2", "NB1", ...
  canopy_frac: number;          // 0-1
  water_frac: number;           // 0-1 (non-burnable fraction)
}

export interface FuelLoadMeta {
  served_records?: number;
  source_file?: string;
  source_class_mapping?: string;
  sb40_reference?: string;
  fuel_load_summary_t_per_ha?: { min: number; max: number; mean: number; p50: number };
  n_records?: number;
}

/** Result of POST /api/v2/burn-prediction. Each spread_Xh sub-dict is
 *  a SpreadPredictor.predict() horizon entry. */
export interface BurnHorizon {
  polygon: GeoJSONFeatureCollection;
  area_ha: number;
  max_ros_m_min: number;
  byram_intensity_kw_m?: number;
  flame_length_m?: number;
  mode?: string;
}

export interface BurnPrediction {
  spread_6h: BurnHorizon | null;
  spread_12h: BurnHorizon | null;
  spread_24h: BurnHorizon | null;
}

export interface BurnPredictionMeta {
  cached?: boolean;
  cache_age_s?: number;
  elapsed_s?: number;
  fire_detection?: { fire_lat: number; fire_lon: number; frp_mw: number };
  weather_used?: { wind_kmh: number; temp_c: number; rh_pct: number; fwi: number; wind_dir_deg?: number };
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

  divisionOverview: async (signal?: AbortSignal): Promise<DivisionDetail[]> => {
    const env = await getEnvelope<{ divisions: DivisionDetail[] }>(
      '/api/v2/division-overview',
      signal,
    );
    return env.data.divisions;
  },

  /** Live season-validation source returns a wrapper object —
   *  { summary, per_day, per_division, per_trust_tier }. We unwrap
   *  `per_day` and map the live `recall_any_band` field to the
   *  `recall_pct` name the v4 ValidationTab expects. */
  seasonValidation: async (signal?: AbortSignal): Promise<ValidationRow[]> => {
    interface PerDayRaw {
      date: string;
      n_critical_alerts?: number;
      n_events?: number;
      n_caught_any_band?: number;
      n_caught_critical?: number;
      recall_any_band?: number | null;
      recall_critical?: number | null;
    }
    const env = await getEnvelope<{ per_day?: PerDayRaw[] }>(
      '/api/v2/season-validation',
      signal,
    );
    const rows = env.data?.per_day ?? [];
    return rows.map((r) => ({
      date: r.date,
      predicted: Number(r.n_critical_alerts ?? 0),
      observed: Number(r.n_events ?? 0),
      caught: Number(r.n_caught_any_band ?? 0),
      // recall_any_band is fraction (0-1) on live data; coerce to %
      recall_pct:
        typeof r.recall_any_band === 'number'
          ? r.recall_any_band <= 1
            ? r.recall_any_band * 100
            : r.recall_any_band
          : 0,
      trust:
        (r.recall_any_band ?? 0) >= 0.30
          ? 'HIGH'
          : (r.recall_any_band ?? 0) >= 0.15
            ? 'MEDIUM'
            : 'LOW',
    }));
  },

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

  /** Per-cell historical burn counts (5-year, fire-season VIIRS). Default
   *  filter is `min_seasons=3` (~27k records) — those are the
   *  Mitigation 3 promotion candidates. */
  historicalBurnPriors: async (
    minSeasons = 3,
    signal?: AbortSignal,
  ): Promise<{ records: HistoricalBurnPrior[]; meta: HistoricalBurnPriorMeta }> => {
    const env = await getEnvelope<{ records: HistoricalBurnPrior[] }, HistoricalBurnPriorMeta>(
      `/api/v2/historical-burn-priors?min_seasons=${minSeasons}`,
      signal,
    );
    return { records: env.data?.records ?? [], meta: env.meta ?? {} };
  },

  /** Per-cell fuel-load (t/ha) over the entire MP v17 grid.
   *  Used by the v4 portal "Fuel load" sidebar toggle. */
  fuelLoad: async (
    signal?: AbortSignal,
  ): Promise<{ records: FuelLoadRecord[]; meta: FuelLoadMeta }> => {
    const env = await getEnvelope<{ records: FuelLoadRecord[] }, FuelLoadMeta>(
      '/api/v2/fuel-load',
      signal,
    );
    return { records: env.data?.records ?? [], meta: env.meta ?? {} };
  },

  /** Synchronous burn-area prediction at an ignition point.
   *  Slow (1-30 s); the backend rate-limits to 4 req/min/IP. Returns
   *  spread_6h / spread_12h / spread_24h with polygon + area_ha. */
  burnPrediction: async (
    body: { lat: number; lon: number; frp_mw?: number; weather?: Record<string, number> },
    signal?: AbortSignal,
  ): Promise<{ prediction: BurnPrediction; meta: BurnPredictionMeta }> => {
    const res = await fetch('/api/v2/burn-prediction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
    const text = await res.text();
    let parsed: unknown;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      throw new ApiError(res.status, {
        code: 'invalid_json_response',
        message: `Non-JSON body from burn-prediction (HTTP ${res.status})`,
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
    const env = parsed as Envelope<BurnPrediction, BurnPredictionMeta>;
    return { prediction: env.data, meta: env.meta ?? {} };
  },

  /** Density-friendly point cloud for the burn-density HeatmapLayer.
   *  Each point is `{lat, lon, w}` for a cell with >=2 fires in 5y. */
  historicalBurnDensity: async (
    signal?: AbortSignal,
  ): Promise<{ points: HistoricalBurnPoint[]; meta: HistoricalBurnDensityMeta }> => {
    const env = await getEnvelope<{ points: HistoricalBurnPoint[] }, HistoricalBurnDensityMeta>(
      '/api/v2/historical-burn-density',
      signal,
    );
    return { points: env.data?.points ?? [], meta: env.meta ?? {} };
  },

  /** Dissolved MP division polygons. Much smaller (~8 MB ultra, ~17 MB high)
   *  than /api/v2/beats-boundary (~187 MB). Default resolution is `ultra` —
   *  good for state-level overview at zoom 5-8. */
  divisionBoundaries: (
    resolution: 'ultra' | 'high' = 'ultra',
    signal?: AbortSignal,
  ) =>
    getData<GeoJSONFeatureCollection>(
      `/api/v2/division-boundaries?resolution=${resolution}`,
      signal,
    ),
};
