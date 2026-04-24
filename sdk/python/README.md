# jwalanetra-sdk

Minimal Python client for the **JwalaNetra v2 Portal API** — MP Forest Fire Early Warning System.

Zero runtime dependencies. Uses `urllib.request` from the standard library.

## Install

```bash
# from the repo root
pip install -e sdk/python
```

## Usage

```python
from jwalanetra import Client, ApiError

client = Client("http://localhost:8790")

# Liveness check
health = client.healthz()
assert health["data"]["ok"] is True

# First page of ignition alerts
page1 = client.ignition_v17(limit=5)
cells = page1["data"]        # list of V17Cell dicts
meta  = page1["meta"]        # PaginationMeta dict

# Walk pages with cursor
cursor = meta["next_cursor"]
if cursor:
    page2 = client.ignition_v17(limit=5, cursor=cursor)

# Division overview
overview = client.division_overview()
divisions = overview["data"]["divisions"]  # list of DivisionSummary

# VIIRS fires for a date range
fires = client.viirs_fires(from_date="2026-04-07", to_date="2026-04-07")
print(fires["meta"]["n_before_clip"], "raw detections ->",
      fires["meta"]["total"], "after forest clip")

# Model card
card = client.model_transparency()
model_name = card["data"].get("model") or card["data"].get("model_version")

# Error handling
try:
    client.ignition_v17(limit=0)  # out of range
except ApiError as exc:
    print(exc.code, exc.status)   # e.g. "invalid_limit", 400
```

## API coverage

| Method                  | Endpoint                        |
|-------------------------|---------------------------------|
| `healthz()`             | `GET /api/v2/healthz`           |
| `ignition_v17(...)`     | `GET /api/v2/ignition-v17`      |
| `division_overview()`   | `GET /api/v2/division-overview` |
| `season_validation()`   | `GET /api/v2/season-validation` |
| `model_transparency()`  | `GET /api/v2/model-transparency`|
| `viirs_fires(...)`      | `GET /api/v2/viirs-fires`       |
| `beats_boundary()`      | `GET /api/v2/beats-boundary`    |

## Known spec drift

The OpenAPI spec and live server disagree on two shapes; both are documented in the TypedDicts:

- `/division-overview`: spec says `data` is a list; live server returns `data` as a dict with key `divisions` containing the list.
- `/model-transparency`: spec says `data.model_version`; live server returns `data.model`.
- `/season-validation`: spec says `data` is a flat list of `ValidationRow`; live server returns `data` as a dict with keys `summary`, `per_day`, `per_trust_tier`, `per_division`.
- `/viirs-fires`: spec says `meta.date_range` is an object `{from, to}`; live server returns it as a plain string `"YYYY-MM-DD to YYYY-MM-DD"`.
