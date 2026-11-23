# App robustness audit, 20 Oct 2026

Four audits, each with repros and a "Fixes applied" table at the end: `runner.md`, `ingest.md`, `field.md`, `officials.md`.

| Part | Found (crit/high/med/low) | Fixed | Left |
|---|---|---|---|
| Evening cloud runner | 3 / 8 / 8 / 7 | all critical and high, most medium | live-age test, calibration text |
| Live fire ingest | 1 / 6 / 9 / 12 | 21 of 28 | M-2, L-3, L-11 (decisions), L-6/L-7 (landcover/geo), L-12 (deploy machine) |
| Field visits and eNetra | 3 / 9 / 10 / 10 | 30 of 32 | L7, L8 (decisions) |
| Officials' layers | 1 / 4 / 8 / 9 | 19 of 22 | L6 wording; L7, L8 notes |

Worst problems found and fixed:
- Guards' reports and phone positions failed (500) while a poll held the database during a WorldCover read. Now the read happens first; writes retry and give 503, and the phone keeps the report.
- The phone dropped a refused report silently. Now it keeps it with the reason.
- PIN guessing was unlimited, empty PINs worked, and the staff list was open. Now there are lockouts, empty PINs are refused and the staff list is admin only.
- Webhooks were never retried. Now there is a durable outbox with event ids.
- One failing hint (arrow, runway, big-fire...) took down the whole alert list. Each hint is now isolated.
- Guards' phones received officials-only fields. They no longer do.
- The runner could issue lists out of season, stop on a GFS hole, or duplicate MODIS days. All fixed. The 5 Apr 2026 replay gives the same list (max score difference 0.002).
- Old alerts reopened as duplicates (+22%). This is now +2%.

New pieces:
- `GET /api/v1/health` is a dead-man check. It covers the freshness of each fire source, the poll heartbeat, and a missing 2-day or watch list after 19:45 IST.
- The nightly wrapper is `scripts/cloud_daily.sh`, run by `deploy/cloud-daily.timer` at 17:15 IST. It retries until 19:15 IST.
- `scripts/run_tests.py` runs each server test on its own fresh database.

Tests (final run): flow, api_v1, pilot and webhook all PASS. daily_list_test PASS on a database that has fires. cause_check_test PASS on a fresh database, as its header says.

For eNetra:
- Verify `X-Signature-Ts`, reject old timestamps, and de-duplicate on `X-Event-Id`.
- A v1 review with no report now returns 400. Send-back works only on visited alerts.
- `check_list` in the brief is now an object with `missing` and `why`.
- The 2-day and watch list endpoints now carry `days_old` and `stale`.

Deployment: the server now refuses to start on a failed migration or a locked database, so it needs a restart policy.
