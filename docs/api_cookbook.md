# JwalaNetra v2 API Cookbook

## TL;DR

JwalaNetra v2 is the REST API for Madhya Pradesh forest fire EWS (87 divisions, ~2,600 alerts/day). Base URL: `http://localhost:8790/api/v2/`. All responses follow `{ data, meta, links? }` envelope on success; `{ error: { code, message, details? } }` on failure. No authentication required (local deployment). The API serves production v17.5 ignition model (LightGBM + hurdle two-stage blend, R@5%=23.55% DBSCAN).

---

## Response Envelope Contract

**Success (2xx):**
```json
{
  "data": [...],
  "meta": {
    "total": 2128,
    "limit": 500,
    "offset": 0,
    "has_next": true,
    "next_cursor": "eyJvZmZzZXQiOiA1MDB9"
  },
  "links": {
    "self": "/api/v2/ignition-v17?limit=500",
    "next": "/api/v2/ignition-v17?cursor=eyJvZmZzZXQiOiA1MDB9"
  }
}
```

**Error (4xx/5xx):**
```json
{
  "error": {
    "code": "invalid_date",
    "message": "date must be YYYY-MM-DD",
    "details": [
      {
        "field": "date",
        "message": "invalid ISO 8601 format",
        "code": "format_error"
      }
    ]
  }
}
```

---

## API Endpoints

| Path | Method | Purpose | Key Params |
|------|--------|---------|-----------|
| `/ignition-v17` | GET | Paginated v17.5 alerts (CRITICAL/ALERT/WATCH bands) | `date`, `limit` (max 2000), `cursor` |
| `/division-overview` | GET | 87 divisions + alert counts + trust tiers | `date` |
| `/viirs-fires` | GET | Forest-clipped FIRMS detections (1.35M historical) | `from`, `to` (date range) |
| `/model-transparency` | GET | v17.5 honest metrics, feature importance, weaknesses | — |
| `/season-validation` | GET | Rolling 2026 season recall vs observed | — |
| `/validation-log` | GET | Field operator responses + outcomes | — |
| `/blind-spots` | GET | Per-division recall dropout analysis | — |
| `/beats-boundary` | GET | 8,973 forest-beat GeoJSON MultiPolygons (179 MB) | — |
| `/operational-alerts` | GET | Decorated alerts (coverage floor + climatology applied) | `date` |
| `/division-briefings` | GET | Human-readable per-division briefings | — |
| `/field-responses` | GET | Operator response rollup | — |
| `/field-responses` | POST | Record operator response (dispatch/monitor/awareness) | body: `cell_id`, `action`, `operator?`, `notes?` |
| `/latest-alert` | GET | Most recent NRT detection bundle | — |
| `/healthz` | GET | Liveness + cache warmup (FIRMS age, beat polygons loaded) | — |

See [openapi.yaml](../dashboard/v3/openapi.yaml) for full schemas and detailed descriptions.

---

## Pagination Cookbook

**Scenario:** Walk all ~2,128 cells from `/api/v2/ignition-v17` in pages of 500.

### cURL (3 pages)
```bash
# Page 1
curl -s "http://localhost:8790/api/v2/ignition-v17?limit=500" | jq '.data | length, .[0]'

# Page 2: use next_cursor from Page 1
CURSOR=$(curl -s "http://localhost:8790/api/v2/ignition-v17?limit=500" | jq -r '.meta.next_cursor')
curl -s "http://localhost:8790/api/v2/ignition-v17?limit=500&cursor=$CURSOR" | jq '.data | length'

# Page 3: repeat with new cursor
CURSOR=$(curl -s "http://localhost:8790/api/v2/ignition-v17?limit=500&cursor=$CURSOR" | jq -r '.meta.next_cursor')
curl -s "http://localhost:8790/api/v2/ignition-v17?limit=500&cursor=$CURSOR" | jq '.meta.has_next'
```

### Python (urllib, no deps)
```python
import json, urllib.request

url = "http://localhost:8790/api/v2/ignition-v17?limit=500"
page = 0

while url:
    with urllib.request.urlopen(url) as resp:
        body = json.loads(resp.read())
    
    data = body['data']
    meta = body['meta']
    print(f"Page {page}: {len(data)} cells, has_next={meta['has_next']}")
    
    # cursor is opaque base64; pass it as-is
    if meta['has_next'] and meta.get('next_cursor'):
        url = f"http://localhost:8790/api/v2/ignition-v17?limit=500&cursor={meta['next_cursor']}"
        page += 1
    else:
        url = None
```

### TypeScript (fetch)
```typescript
async function walkPages() {
  let url = "http://localhost:8790/api/v2/ignition-v17?limit=500";
  let page = 0;

  while (url) {
    const resp = await fetch(url);
    const body = await resp.json();
    const { data, meta } = body;
    
    console.log(`Page ${page}: ${data.length} cells`);
    
    // next_cursor is opaque; treat as string
    if (meta.has_next && meta.next_cursor) {
      url = `http://localhost:8790/api/v2/ignition-v17?limit=500&cursor=${meta.next_cursor}`;
      page++;
    } else {
      url = null;
    }
  }
}
```

---

## Error Handling Cookbook

### Example: Invalid date parameter (400)
```bash
curl -s "http://localhost:8790/api/v2/ignition-v17?date=2026-13-01" | jq '.'
```
```json
{
  "error": {
    "code": "invalid_date",
    "message": "date must be YYYY-MM-DD and ≤ latest prediction",
    "details": [{"field": "date", "code": "format_error"}]
  }
}
```

### Example: Invalid POST payload (422)
```bash
curl -X POST http://localhost:8790/api/v2/field-responses \
  -H "Content-Type: application/json" \
  -d '{"cell_id": "r0173_c0343", "action": "invalid_action"}'
```
```json
{
  "error": {
    "code": "validation_error",
    "message": "validation failed",
    "details": [
      {"field": "action", "message": "must be one of: dispatch, monitor, awareness", "code": "enum_error"}
    ]
  }
}
```

### Python (urllib)
```python
try:
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())
except urllib.error.HTTPError as e:
    error_body = json.loads(e.read())
    code = error_body['error']['code']
    msg = error_body['error']['message']
    print(f"API error [{code}]: {msg}")
    # details are in error_body['error'].get('details')
```

### TypeScript (fetch)
```typescript
const resp = await fetch(url);
if (!resp.ok) {
  const { error } = await resp.json();
  throw new Error(`${error.code}: ${error.message}`);
}
```

---

## Common Recipes

**Get today's CRITICAL alerts only**
```python
resp = urllib.request.urlopen("http://localhost:8790/api/v2/ignition-v17")
body = json.loads(resp.read())
critical = [c for c in body['data'] if c['band'] == 'CRITICAL']
print(f"{len(critical)} CRITICAL alerts")
```

**FIRMS forest-clip ratio**
```bash
curl -s "http://localhost:8790/api/v2/viirs-fires?from=2026-04-01&to=2026-04-07" | jq '{
  n_raw: .meta.n_before_clip,
  n_forest: .meta.n_clipped,
  ratio_kept: (.meta.n_clipped / .meta.n_before_clip * 100 | round)
}'
# Output: {"n_raw": 1199, "n_forest": 297, "ratio_kept": 25}  (75% filtered as non-forest)
```

**Check backend health before batch job**
```python
health = json.loads(urllib.request.urlopen("http://localhost:8790/api/v2/healthz").read())
firms_age = health['data']['firms_nrt_age_hours']
if firms_age > 24:
    print(f"WARNING: FIRMS data {firms_age}h old, consider delay")
```

**Download and cache beat polygons (179 MB)**
Store locally once; reference for spatial joins. Python example:
```python
import json
resp = urllib.request.urlopen("http://localhost:8790/api/v2/beats-boundary")
fc = json.loads(resp.read())['data']
with open("beats.geojson", "w") as f:
    json.dump(fc, f)
# Later: load from disk
with open("beats.geojson") as f:
    beats = json.load(f)
print(f"Loaded {len(beats['features'])} beat polygons")
```

TypeScript with IndexedDB:
```typescript
// Store once
const resp = await fetch("http://localhost:8790/api/v2/beats-boundary");
const fc = (await resp.json()).data;
const db = await openDB('jwala');
await db.put('cache', fc, 'beats');

// Later: retrieve
const beats = await db.get('cache', 'beats');
```

---

## Rate Limits & Quotas

No rate limits or authentication today. The API is designed for local deployment and departmental LAN use. Page-size cap: `limit` ≤ 2000 cells on `/ignition-v17`.

---

## Versioning

- **`/api/v2/*`** — Public contract. Documented in [openapi.yaml](../dashboard/v3/openapi.yaml). Stable across deployments.
- **`/api/*` (unversioned)** — Legacy v3 portal endpoints. Will be removed when the v3 portal is retired. Do not depend on these for new integrations.

---

## SDKs

Prebuilt clients for common languages:
- **Python**: `sdk/python/` — Full type hints, automatic serialization
- **TypeScript**: `sdk/typescript/` — ESM modules, generated from OpenAPI

For other languages, generate from the OpenAPI spec using `openapi-generator` or equivalent.

---

## Reference

- [Full OpenAPI Spec](../dashboard/v3/openapi.yaml)
- [Backend Router](../dashboard/v3/serve.py#L895) — actual route dispatch
- [Project Overview](../CLAUDE.md) — v17.5 model context (MP, 87 divisions, 2026-04-19 ship)
