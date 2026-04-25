# Multi-Backend Audit Plan — Surgical Hardening of Historical-Burn Endpoints

**Created:** 2026-04-25
**Workflow:** `/everything-claude-code:multi-backend` (Codex unavailable due to OpenAI account quota; substituted with parallel `security-auditor` + `code-reviewer-pro` subagents for the second-opinion gate per user election.)
**Scope:** endpoint-only hardening of `/api/v2/historical-burn-priors` and `/api/v2/historical-burn-density`. No project-wide changes.

## Drivers

Two new GET endpoints shipped in commit `b6bdc29a` to support Mitigations 2+3 from `docs/edge_bias_brutal_analysis.md`. Independent review surfaced the issue list below; user picked the smallest blast-radius package.

## Findings (from Phase 2 agent reviews)

Convergent (both agents flagged):
1. Cold-load on every request (~50–150 ms JSON parse, no cache)
2. Silent param clamp on `min_seasons` (violates fail-fast)
3. No tests

Security-only (in scope):
- MEDIUM: Info disclosure via `str(exc)` and `path.name` in error bodies
- MEDIUM: No `Cache-Control` / `ETag`
- LOW: Multiple `?min_seasons` params silently coalesce
- LOW: Untrusted metadata spread into response envelope
- INFO: Missing `X-Content-Type-Options: nosniff`

Out of scope (project-wide / orthogonal — separate PRs):
- HIGH: X-Forwarded-For trusted unconditionally (whole-server change)
- HIGH: Memory amplification on full-file path (mitigated indirectly by ETag/cache; full fix is to drop in-memory filter, deferred)
- MEDIUM: CORS wildcard (policy decision)
- LOW: No gzip (transport)
- Frontend filter dedup in `LiveMapTab.tsx` (cosmetic)

## Files

| Path | Change |
|---|---|
| `dashboard/v3/serve.py` | Add module-level `_load_cached_json` helper. Extend `_send_json` with optional `extra_headers` param + always-on nosniff. Rewrite `_serve_v2_historical_priors` (validation, cache, ETag/304, scrubbed errors, whitelisted metadata). Rewrite `_serve_v2_historical_density` (cache, ETag/304, scrubbed errors). |
| `tests/test_v3_priors.py` | New file. 7 pytest cases: filter at min_seasons=3, filter at min_seasons=5, 400 on bad input (4 variants), 404 with no path/exc leakage, ETag → 304 on priors, ETag → 304 on density, cache hit skips parse. |

## Test plan

```bash
# After implementation:
python -m pytest tests/test_v3_priors.py -v
# Restart backend, smoke verify endpoints still work
curl -i http://localhost:8790/api/v2/historical-burn-priors?min_seasons=3 | head -20
curl -i http://localhost:8790/api/v2/historical-burn-priors?min_seasons=foo | head -8   # expect 400
curl -i -H "If-None-Match: <etag from prev response>" http://localhost:8790/api/v2/historical-burn-priors?min_seasons=3 | head -3   # expect 304
```

## Risk

- Behavior change: silent clamp → 400. v4 portal only ever sends `min_seasons=3`, so impact is zero on shipping clients.
- Cache correctness: mtime_ns key invalidates on every legitimate rewrite by the build script.
- ETag stability: deterministic across restarts (mtime_ns + size + min_seasons).

## Rollback

Single commit, single file pair. `git revert` works cleanly.
