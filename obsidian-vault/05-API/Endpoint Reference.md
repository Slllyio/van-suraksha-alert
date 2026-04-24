---
title: v2 API Endpoint Reference
namespace: /api/v2
base-url: http://localhost:8790
envelope: { data, meta, links? }
tags: [api, reference]
---

# /api/v2 — Endpoint Reference

Every 2xx response follows the [[Envelope Contract]]; every non-2xx uses [[Error Handling|standardized errors]].

## GET endpoints

| Path | Purpose | Key query params |
|---|---|---|
| `/api/v2/ignition-v17` | [[Pagination Cookbook\|Paginated]] v17 banded alerts | `date`, `limit` 1-2000, `cursor` |
| `/api/v2/division-overview` | 87 divisions with alert counts | — |
| `/api/v2/season-validation` | Rolling 2026 season validation | — |
| `/api/v2/validation-log` | Operator action log | — |
| `/api/v2/blind-spots` | Per-division blind-spot analysis | — |
| `/api/v2/model-transparency` | [[04-Model/Honest Metrics\|Model card data]] | — |
| `/api/v2/viirs-fires` | FIRMS VIIRS fires, forest-clipped | `from`, `to` (YYYY-MM-DD) |
| `/api/v2/beats-boundary` | 8,973 MP beat polygons (187 MB!) | — |
| `/api/v2/operational-alerts` | Decorated alerts (climatology floor applied) | `date` |
| `/api/v2/division-briefings` | Per-division briefings | — |
| `/api/v2/field-responses` | Operator response rollup | — |
| `/api/v2/latest-alert` | Most recent NRT bundle | — |
| `/api/v2/healthz` | Backend health | — |

## POST endpoints

| Path | Purpose | Notes |
|---|---|---|
| `/api/v2/field-responses` | Record operator response | Returns 201 Created with `Location:` header per REST convention. Uses standard 422 envelope on validation failure. |

## SDKs

- TypeScript: `sdk/typescript/` — zero runtime deps, generated types from [[../../dashboard/v3/openapi.yaml|OpenAPI spec]]
- Python: `sdk/python/jwalanetra/` — urllib-only, TypedDict types
- Contract tests: `tests/test_api_v2_contract.py` — 10 passing

## Related

- [[Envelope Contract]]
- [[Pagination Cookbook]]
- [[Error Handling]]
- [[06-Swarm-Reports/OpenAPI Audit]] — flagged 7 schema drifts, all fixed
- Home: [[INDEX]]
