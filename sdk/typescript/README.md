# @jwalanetra/sdk

Zero-dependency TypeScript client for the JwalaNetra v2 Forest Fire Early Warning System Portal API.

Requires Node.js 18+ or any modern browser (uses the global `fetch`). No axios, no schema validators, no runtime dependencies.

## Install

The SDK is private (`"private": true`). Reference it directly from the monorepo:

```jsonc
// In your consumer's package.json
{
  "dependencies": {
    "@jwalanetra/sdk": "file:../../sdk/typescript"
  }
}
```

## Usage

```ts
import { Client, ApiError } from "@jwalanetra/sdk";

// Default base URL: http://localhost:8790
const api = new Client();

// Custom base URL (e.g. production reverse proxy)
const prod = new Client({ baseUrl: "https://fire.mpforest.gov.in" });
```

### Paginated ignition alerts

```ts
const page = await api.ignitionV17({ limit: 500 });
console.log(page.meta.total, "alerts");

// Page through all results
let cursor: string | undefined;
do {
  const p = await api.ignitionV17({ limit: 500, cursor });
  process(p.data);
  cursor = p.meta.next_cursor ?? undefined;
} while (p.meta.has_next);
```

### Division overview

```ts
const { data: divisions } = await api.divisionOverview();
const critical = divisions.filter((d) => (d.critical ?? 0) > 0);
```

### VIIRS fire detections

```ts
const result = await api.viirsFiresRaw({ from: "2026-04-01", to: "2026-04-07" });
console.log(result.meta?.n_clipped, "forest-beat fires");
```

### Record operator response

```ts
const created = await api.createFieldResponse({
  cell_id: "r0173_c0343",
  action: "dispatch",
  operator: "DFO-Guna",
  notes: "Fire confirmed at 24.4N / 77.1E",
});
console.log("Created at:", created.location);
```

### Health check

```ts
const health = await api.healthz();
if (!health.data?.ok) throw new Error("Backend unhealthy");
```

## Error handling

All methods throw `ApiError` on non-2xx responses:

```ts
import { ApiError } from "@jwalanetra/sdk";

try {
  await api.ignitionV17({ cursor: "stale-token" });
} catch (err) {
  if (err instanceof ApiError) {
    console.error(err.code, err.message, err.status);
    // e.g. "invalid_cursor" / "Cursor has expired" / 400
  }
}
```

## API surface

| Method | Endpoint | Notes |
|---|---|---|
| `ignitionV17(params?)` | `GET /api/v2/ignition-v17` | Cursor-paginated, up to 2 600 cells/day |
| `divisionOverview()` | `GET /api/v2/division-overview` | 87 divisions + trust tiers |
| `seasonValidation()` | `GET /api/v2/season-validation` | Rolling recall vs observed fires |
| `validationLog()` | `GET /api/v2/validation-log` | Returns `unknown` (schema not defined) |
| `modelTransparency()` | `GET /api/v2/model-transparency` | v17.5 metrics + feature importance |
| `blindSpots()` | `GET /api/v2/blind-spots` | Returns `unknown` (schema not defined) |
| `latestAlert()` | `GET /api/v2/latest-alert` | Returns `unknown` (schema not defined) |
| `viirsFiresRaw(params?)` | `GET /api/v2/viirs-fires` | Date-range filter, 1.35 M rows |
| `beatsBoundary()` | `GET /api/v2/beats-boundary` | ~179 MB — cache client-side |
| `operationalAlerts(params?)` | `GET /api/v2/operational-alerts` | Returns `unknown` (schema not defined) |
| `divisionBriefings()` | `GET /api/v2/division-briefings` | Returns `unknown` (schema not defined) |
| `fieldResponses()` | `GET /api/v2/field-responses` | Returns `unknown` (schema not defined) |
| `createFieldResponse(input)` | `POST /api/v2/field-responses` | 201 + Location header |
| `healthz()` | `GET /api/v2/healthz` | Liveness + cache flags |
