/**
 * @module @jwalanetra/sdk
 * @description Zero-dependency TypeScript client for the JwalaNetra v2 Portal API.
 *
 * Uses the global `fetch` available in Node.js 18+ and all modern browsers.
 * Every method unwraps the `{ data, meta, links? }` envelope and throws a typed
 * {@link ApiError} on any non-2xx response.
 */

import type { components, paths } from "./types.js";

// ---------------------------------------------------------------------------
// Re-exported domain types
// ---------------------------------------------------------------------------

export type V17Cell = components["schemas"]["V17Cell"];
export type DivisionSummary = components["schemas"]["DivisionSummary"];
export type ValidationRow = components["schemas"]["ValidationRow"];
export type ModelTransparency = components["schemas"]["ModelTransparency"];
export type ViirsFire = components["schemas"]["ViirsFire"];
export type FieldResponseInput = components["schemas"]["FieldResponseInput"];
export type FieldResponse = components["schemas"]["FieldResponse"];
export type GeoJSONFeatureCollection =
  components["schemas"]["GeoJSONFeatureCollection"];
export type PaginationLinks = components["schemas"]["PaginationLinks"];

// ---------------------------------------------------------------------------
// Envelope + pagination helpers derived from the generated path types
// ---------------------------------------------------------------------------

/** Unwrapped response for paginated {@link Client.ignitionV17}. */
export interface IgnitionV17Page {
  data: V17Cell[];
  meta: NonNullable<
    paths["/api/v2/ignition-v17"]["get"]["responses"][200]["content"]["application/json"]["meta"]
  >;
  links?: PaginationLinks;
}

/** Unwrapped response for {@link Client.divisionOverview}. */
export interface DivisionOverviewResult {
  data: DivisionSummary[];
  meta?: { total?: number };
}

/** Unwrapped response for {@link Client.seasonValidation}. */
export interface SeasonValidationResult {
  data?: ValidationRow[];
  meta?: { total?: number };
}

/** Unwrapped response for {@link Client.viirsFiresRaw}. */
export interface ViirsFiresResult {
  data?: ViirsFire[];
  meta?: {
    total?: number;
    n_before_clip?: number;
    n_clipped?: number;
    latest_date?: string;
    date_range?: { from?: string; to?: string };
  };
}

/** Unwrapped response for {@link Client.beatsBoundary}. */
export interface BeatsBoundaryResult {
  data?: GeoJSONFeatureCollection;
  meta?: { n_features?: number };
}

/** Unwrapped response for {@link Client.modelTransparency}. */
export interface ModelTransparencyResult {
  data?: ModelTransparency;
}

/** Unwrapped response for {@link Client.healthz}. */
export interface HealthzResult {
  data?: {
    ok?: boolean;
    portal_uptime_s?: number;
    beat_polygons_loaded?: boolean;
    firms_nrt_age_hours?: number;
    firms_nrt_max_date?: string;
  };
}

/** Unwrapped response for {@link Client.createFieldResponse}. */
export interface CreateFieldResponseResult {
  data?: FieldResponse;
  meta?: { created_at?: string };
  /**
   * Relative URI returned in the `Location` header.
   * `undefined` when the server omits the header (non-conformant responses).
   */
  location?: string | undefined;
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

/**
 * Thrown whenever the API returns a non-2xx HTTP status code.
 *
 * The `code` and `message` fields are extracted from the standardised error
 * envelope `{ error: { code, message, details? } }`.  When the server returns
 * an unparseable body the `code` is `"network_error"` and `message` contains
 * the raw status text.
 */
export class ApiError extends Error {
  /** Snake-case machine code from the API error envelope. */
  readonly code: string;
  /** HTTP status code. */
  readonly status: number;
  /** Field-level validation details, if present. */
  readonly details?: Array<{ field?: string; message?: string; code?: string }>;

  constructor(
    code: string,
    message: string,
    status: number,
    details?: Array<{ field?: string; message?: string; code?: string }>,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    // Conditional assignment avoids writing explicit `undefined` to an
    // optional property, which exactOptionalPropertyTypes disallows.
    if (details !== undefined) {
      this.details = details;
    }
  }
}

// ---------------------------------------------------------------------------
// Client configuration
// ---------------------------------------------------------------------------

/** Options accepted by the {@link Client} constructor. */
export interface ClientOptions {
  /**
   * Base URL of the JwalaNetra portal backend.
   * @default "http://localhost:8790"
   */
  baseUrl?: string;

  /**
   * Default headers merged into every request.
   * Useful for passing an `Authorization` token when the portal is
   * deployed behind an authenticating reverse proxy.
   */
  defaultHeaders?: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Build a URL string, appending only the params that are defined. */
function buildUrl(
  base: string,
  path: string,
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const url = new URL(path, base.endsWith("/") ? base : base + "/");
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

/** Parse a response, throwing {@link ApiError} on non-2xx. */
async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    // 204 No Content and similar
    const text = await response.text();
    return (text ? (JSON.parse(text) as T) : undefined) as T;
  }

  // Attempt to parse the standardised error envelope
  let code = "http_error";
  let message = `HTTP ${response.status}: ${response.statusText}`;
  let details: ApiError["details"];

  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: ApiError["details"] };
    };
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    // body was not JSON — keep the defaults
  }

  throw new ApiError(code, message, response.status, details);
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/**
 * JwalaNetra v2 Portal API client.
 *
 * All methods are `async` and return typed, unwrapped response objects.
 * Non-2xx responses throw a {@link ApiError}.
 *
 * @example
 * ```ts
 * import { Client } from "@jwalanetra/sdk";
 *
 * const api = new Client();
 * const page = await api.ignitionV17({ limit: 500 });
 * console.log(page.meta.total, "alerts");
 * ```
 */
export class Client {
  private readonly baseUrl: string;
  private readonly defaultHeaders: Record<string, string>;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "http://localhost:8790";
    this.defaultHeaders = {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...options.defaultHeaders,
    };
  }

  // -------------------------------------------------------------------------
  // Private fetch helper
  // -------------------------------------------------------------------------

  private async request<T>(
    path: string,
    init?: RequestInit,
    queryParams: Record<string, string | number | boolean | undefined | null> = {},
  ): Promise<T> {
    const url = buildUrl(this.baseUrl, path, queryParams);
    const response = await fetch(url, {
      ...init,
      headers: {
        ...this.defaultHeaders,
        ...((init?.headers as Record<string, string>) ?? {}),
      },
    });
    return parseResponse<T>(response);
  }

  // -------------------------------------------------------------------------
  // /api/v2/ignition-v17
  // -------------------------------------------------------------------------

  /**
   * Fetch paginated v17 banded fire-ignition alerts.
   *
   * The v17.5 model produces ~2,600 ranked cells per day (CRITICAL / ALERT /
   * WATCH).  Use `cursor` from `meta.next_cursor` to page through results.
   *
   * @param params - Optional query parameters.
   * @returns An envelope with `data`, `meta`, and optional `links`.
   *
   * @throws {@link ApiError} on 400 or any non-2xx response.
   *
   * @example
   * ```ts
   * let cursor: string | undefined;
   * do {
   *   const page = await api.ignitionV17({ limit: 500, cursor });
   *   process(page.data);
   *   cursor = page.meta.next_cursor ?? undefined;
   * } while (page.meta.has_next);
   * ```
   */
  async ignitionV17(params?: {
    /** Prediction date (YYYY-MM-DD). Defaults to latest available. */
    date?: string;
    /** Max rows to return (1–2000, default 500). */
    limit?: number;
    /** Opaque cursor from a previous page's `meta.next_cursor`. */
    cursor?: string;
  }): Promise<IgnitionV17Page> {
    return this.request<IgnitionV17Page>("/api/v2/ignition-v17", undefined, {
      date: params?.date,
      limit: params?.limit,
      cursor: params?.cursor,
    });
  }

  // -------------------------------------------------------------------------
  // /api/v2/division-overview
  // -------------------------------------------------------------------------

  /**
   * Fetch alert counts and trust tier for all 87 MP forest divisions.
   *
   * @returns Envelope with `data` array of {@link DivisionSummary}.
   * @throws {@link ApiError} on non-2xx.
   */
  async divisionOverview(): Promise<DivisionOverviewResult> {
    return this.request<DivisionOverviewResult>("/api/v2/division-overview");
  }

  // -------------------------------------------------------------------------
  // /api/v2/season-validation
  // -------------------------------------------------------------------------

  /**
   * Fetch rolling 2026 season recall metrics vs observed fires.
   *
   * @returns Envelope with `data` array of {@link ValidationRow}.
   * @throws {@link ApiError} on non-2xx.
   */
  async seasonValidation(): Promise<SeasonValidationResult> {
    return this.request<SeasonValidationResult>("/api/v2/season-validation");
  }

  // -------------------------------------------------------------------------
  // /api/v2/validation-log
  // -------------------------------------------------------------------------

  /**
   * Fetch the field validation log (operator actions vs model predictions).
   *
   * The spec does not define a response schema for this endpoint; the raw
   * parsed JSON is returned as `unknown`.  Consumers should narrow the type
   * themselves.
   *
   * @returns Raw parsed JSON body.
   * @throws {@link ApiError} on non-2xx.
   */
  async validationLog(): Promise<unknown> {
    return this.request<unknown>("/api/v2/validation-log");
  }

  // -------------------------------------------------------------------------
  // /api/v2/model-transparency
  // -------------------------------------------------------------------------

  /**
   * Fetch the v17.5 model card: metrics, feature importance, and trust tiers.
   *
   * @returns Envelope with `data` of type {@link ModelTransparency}.
   * @throws {@link ApiError} on non-2xx.
   */
  async modelTransparency(): Promise<ModelTransparencyResult> {
    return this.request<ModelTransparencyResult>("/api/v2/model-transparency");
  }

  // -------------------------------------------------------------------------
  // /api/v2/blind-spots
  // -------------------------------------------------------------------------

  /**
   * Fetch the per-division blind-spot analysis (where model recall drops).
   *
   * The spec does not define a response schema for this endpoint; the raw
   * parsed JSON is returned as `unknown`.
   *
   * @returns Raw parsed JSON body.
   * @throws {@link ApiError} on non-2xx.
   */
  async blindSpots(): Promise<unknown> {
    return this.request<unknown>("/api/v2/blind-spots");
  }

  // -------------------------------------------------------------------------
  // /api/v2/latest-alert
  // -------------------------------------------------------------------------

  /**
   * Fetch the most recent NRT detection bundle.
   *
   * The spec does not define a response schema for this endpoint; the raw
   * parsed JSON is returned as `unknown`.
   *
   * @returns Raw parsed JSON body.
   * @throws {@link ApiError} on non-2xx.
   */
  async latestAlert(): Promise<unknown> {
    return this.request<unknown>("/api/v2/latest-alert");
  }

  // -------------------------------------------------------------------------
  // /api/v2/viirs-fires
  // -------------------------------------------------------------------------

  /**
   * Fetch forest-clipped FIRMS VIIRS active-fire detections.
   *
   * Detections are spatially joined to MP beat polygons; ~75% of raw VIIRS
   * pixels are excluded as non-forest.  1.35 M historical rows indexed by date.
   *
   * @param params - Optional date-range filter (both inclusive, YYYY-MM-DD).
   * @returns Envelope with `data` array of {@link ViirsFire} and clip counts.
   * @throws {@link ApiError} on non-2xx.
   *
   * @example
   * ```ts
   * const result = await api.viirsFiresRaw({ from: "2026-04-01", to: "2026-04-07" });
   * console.log(result.meta?.n_clipped, "detections clipped to forest beats");
   * ```
   */
  async viirsFiresRaw(params?: {
    /** Start date (YYYY-MM-DD, inclusive). */
    from?: string;
    /** End date (YYYY-MM-DD, inclusive). */
    to?: string;
  }): Promise<ViirsFiresResult> {
    return this.request<ViirsFiresResult>("/api/v2/viirs-fires", undefined, {
      from: params?.from,
      to: params?.to,
    });
  }

  // -------------------------------------------------------------------------
  // /api/v2/beats-boundary
  // -------------------------------------------------------------------------

  /**
   * Fetch all 8,973 MP forest-beat MultiPolygon boundaries as a GeoJSON
   * FeatureCollection.
   *
   * Warning: the response is large (~179 MB).  Fetch once and cache
   * client-side; avoid calling this on every render cycle.
   *
   * @returns Envelope with `data` as a {@link GeoJSONFeatureCollection}.
   * @throws {@link ApiError} on 404 (file missing) or 500 (server error).
   */
  async beatsBoundary(): Promise<BeatsBoundaryResult> {
    return this.request<BeatsBoundaryResult>("/api/v2/beats-boundary");
  }

  // -------------------------------------------------------------------------
  // /api/v2/operational-alerts
  // -------------------------------------------------------------------------

  /**
   * Fetch decorated alerts with coverage floor and climatology corrections applied.
   *
   * The spec does not define a response schema for this endpoint; the raw
   * parsed JSON is returned as `unknown`.
   *
   * @param params - Optional date filter (YYYY-MM-DD).
   * @returns Raw parsed JSON body.
   * @throws {@link ApiError} on non-2xx.
   */
  async operationalAlerts(params?: { date?: string }): Promise<unknown> {
    return this.request<unknown>(
      "/api/v2/operational-alerts",
      undefined,
      { date: params?.date },
    );
  }

  // -------------------------------------------------------------------------
  // /api/v2/division-briefings
  // -------------------------------------------------------------------------

  /**
   * Fetch per-division human-readable briefings.
   *
   * The spec does not define a response schema for this endpoint; the raw
   * parsed JSON is returned as `unknown`.
   *
   * @returns Raw parsed JSON body.
   * @throws {@link ApiError} on non-2xx.
   */
  async divisionBriefings(): Promise<unknown> {
    return this.request<unknown>("/api/v2/division-briefings");
  }

  // -------------------------------------------------------------------------
  // /api/v2/field-responses
  // -------------------------------------------------------------------------

  /**
   * Fetch the operator response rollup (GET).
   *
   * The spec does not define a response schema for this endpoint; the raw
   * parsed JSON is returned as `unknown`.
   *
   * @returns Raw parsed JSON body.
   * @throws {@link ApiError} on non-2xx.
   */
  async fieldResponses(): Promise<unknown> {
    return this.request<unknown>("/api/v2/field-responses");
  }

  /**
   * Record an operator response to an alert (POST).
   *
   * Returns 201 Created with a `Location` header and the created
   * {@link FieldResponse} in the envelope body.
   *
   * @param input - The response payload to create.
   * @returns Envelope with `data` of type {@link FieldResponse}, optional
   *   `meta.created_at`, and the `location` URI from the response header.
   * @throws {@link ApiError} on 422 (validation failure) or any other non-2xx.
   *
   * @example
   * ```ts
   * const result = await api.createFieldResponse({
   *   cell_id: "r0173_c0343",
   *   action: "dispatch",
   *   operator: "DFO-Guna",
   *   notes: "Fire confirmed at grid ref 24.4N/77.1E",
   * });
   * console.log("Created:", result.location);
   * ```
   */
  async createFieldResponse(
    input: FieldResponseInput,
  ): Promise<CreateFieldResponseResult> {
    // We need the raw Response to extract the Location header, so we cannot go
    // through the generic request() helper here.
    const url = buildUrl(this.baseUrl, "/api/v2/field-responses", {});
    const response = await fetch(url, {
      method: "POST",
      headers: this.defaultHeaders,
      body: JSON.stringify(input),
    });

    const parsed = await parseResponse<{
      data?: FieldResponse;
      meta?: { created_at?: string };
    }>(response);

    return {
      ...parsed,
      location: response.headers.get("Location") ?? undefined,
    };
  }

  // -------------------------------------------------------------------------
  // /api/v2/healthz
  // -------------------------------------------------------------------------

  /**
   * Fetch liveness and cache-warmup status.
   *
   * Use this endpoint to check whether the portal backend is running and has
   * loaded the beat polygons + NRT fire detections.
   *
   * @returns Envelope with a `data` object containing `ok`, uptime, and cache
   *   flags.
   * @throws {@link ApiError} on non-2xx.
   *
   * @example
   * ```ts
   * const health = await api.healthz();
   * if (!health.data?.ok) throw new Error("Portal backend is unhealthy");
   * ```
   */
  async healthz(): Promise<HealthzResult> {
    return this.request<HealthzResult>("/api/v2/healthz");
  }
}
