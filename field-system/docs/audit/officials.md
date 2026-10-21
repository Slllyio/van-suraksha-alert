# Audit: officials' layers and alert-card hints

Area: `app/brief.py`, `daily_list.py`, `big_watch_list.py`, `big_fire.py`, `direction.py`, `cdse.py`, `runway.py`, `still_burning.py`, `spread24.py`, `scars.py`, `scar_live.py`, `scar_check.py`, `control_burn.py`, the endpoints that use them in `api_v1.py` and `server.py`, and the background hint threads in `server.py`. I gave today's changes the most attention: the combined new-fire order (`big_fire.order_key`, `big_watch_list.size_at` / `order_value`, the sort in `brief.build`), the big-fire watch layer (`POST /api/v1/big_watch_scores`, `GET /api/v1/big_watch`), and the cloud runner's `POST /api/v1/daily_scores`.

Audited 20 Oct 2026, against the files as they were at 16:00-16:30 UTC. I edited nothing under `/mnt/project-files/field-system` except this report. `scripts/cloud_daily.py` was being rewritten by someone else during the audit (mtime 16:23 UTC). I re-read the new version, and the runner-side notes below refer to it.

**Counts: 1 critical, 4 high, 8 medium, 9 low.**

## How it was tested

- All tests ran in-process with FastAPI's `TestClient`, against copies of the 2026 dry-run database (13,911 alerts, 323k detections), with `FS_DATA_DIR` under `/tmp/claude-0/audit_officials/`. The clock was set to `2026-04-22T10:30Z` (16:00 IST, a peak day). No server process was started, so there is nothing to stop.
- Failure injection: each hint was monkeypatched to raise, then every officials' and guards' endpoint was called. Other runs used a missing grid file, a stalled WorldCover read, a 119 MB unauthenticated body, synthetic 430k-square size-score nights, and 418k-row `daily_scores` bodies.
- The test scripts are in `/tmp/claude-0/audit_officials/t/` (one per finding, named in each section). The proposed patches are `/tmp/claude-0/audit_officials/patch/patches.py`, applied in order by `patch/make.py` to a copy of `app/` at `patch/b/`. **Each repro was run again against the patched copy, and the result is given under "Patched".** The diffs below are cumulative and apply in the order they appear in this report (C1, H1, H3, H4, H5, M1-M8, L1-L5, L9), because later ones use `app/hint.py` from C1 and the `safe()` calls added in H1.
- Project tests:
  - `scripts/daily_list_test.py 2026-04-22`: **ALL PASS** (19 s).
  - `scripts/cause_check_test.py`: **passed** (tagged 60 / random 58 / none 1).
  - `scripts/direction_check.py 12` (live Planetary Computer): 12 of 12 found; within 45° 57% of 7 vs 86% in the research on the same passes. Same scene as the research 71%: the app sometimes picks the same pass on the neighbouring tile (T44QKK vs T43QHE). It also logged `history geometry file read partly: No such file`, so its truth input is incomplete. Treat it as a small-sample signal, not a finding.
  - `scripts/big_fire_season_check.py 2025`: **did not finish**. I stopped it after 32 minutes, still in the ingest step: 185k of 347k points stored, and each 5k batch slowed from 3 s to about 100 s as the database grew. That ingest code (`firms.store`) is outside this area, but the slowdown matters for season replays.
  - `scripts/runway_check.py`: **not run**. It needs `RW_SCRATCH` (`F.parquet`, `events.pkl` from the research scratch), which is not on this machine.

## Findings at a glance

| # | Sev | Where | One line |
|---|-----|-------|----------|
| C1 | critical | big_fire.py:181, 221-224; server.py:233, 277; api_v1.py:84 | If `big_fire.check` raises, the guard's own alert list and card fail with a 500, and so does every eNetra alert call. The new `size_at` adds an unguarded read of `mp_grid.json` on the network mount to that path. |
| H1 | high | server.py:240-248, 279-294; api_v1.py:87-111; brief.py:70-79 | No hint is isolated. One bad row in direction, runway, still-burning, control-burn, scars, spread24 or big-fire returns a 500 for the officials' list, the alert card, every `/api/v1/alerts` page and the brief. |
| H3 | high | api_v1.py:20-23 + every `body: dict` POST; server.py:19 | The JSON body is read and parsed before the X-Api-Key check, with no size limit. A 119 MB body with a wrong key cost 7.4 s and +880 MB RSS before the 401. |
| H4 | high | api_v1.py:86-111, 190, 406 | Guard-facing v1 calls return officials-only fields. The answer to a guard's own report carries cause group and p, big-fire points and items, arrow, runway, still-burning, control-burn and burn scar. |
| H5 | high | big_fire.py:102-115, 197-204; landcover.py:21,35 | Big-fire scoring holds the SQLite write lock while it reads WorldCover over the network. A 35 s read made a concurrent report write fail with "database is locked". A brief with 210 unscored fires took 90.8 s. |
| M1 | medium | big_watch_list.py:32,56,74; api_v1.py:355 | `executescript()` inside `size_at` and `division_view` COMMITs the caller's transaction. A guard's report can return 500 yet already be saved. |
| M2 | medium | runway.py:171-193 | `first_look()` sits outside the try, so one bad fire stops runway hints for all fires on every loop. Transient errors are stored as `error` and never retried. |
| M3 | medium | server.py:78-91 | A failure in `big_fire.score_new` skips `PRAGMA optimize` and the daily scar run in the same poll pass. |
| M4 | medium | brief.py:102-111; daily_list.py:180-183; api_v1.py:331 | The 16:00 brief comes before the runner posts (~17:15 IST), and the 2-day list section silently disappears. The runner's `inputs.stale` is dropped, so officials never see that a list was built on stale inputs. |
| M5 | medium | big_fire.py:181-188, 227-234 | A new fire with no size score always sorts below every fire with one, whatever its points. A missing score is stored for good, so a late runner post never fixes it. Also, the brief says "together with the size score" when none arrived. |
| M6 | medium | static/control.html:118-121; brief.py:185,198 | The control-room "Big-fire watch" still orders by points only, while the brief uses the combined order: officials see two different orders. |
| M7 | medium | big_fire.py:102-115, 186-188 | One failed WorldCover read is stored permanently: that fire never gets its farmland item. |
| M8 | medium | daily_list.py:146-188; api_v1.py:322 | `daily_scores` input checks are missing. Mismatched lengths, out-of-grid cells and duplicate rows give 500s, and a body with no usable rows silently replaces the day with an empty list (200). |
| L1 | low | brief.py:71 | A brief for a past clock uses today's status, so a visit made after the brief shows as "Visited". |
| L2 | low | direction.py:174-186 | `recheck_h()` (2 h when CDSE works) is never used; the recheck is always 6 h. |
| L3 | low | server.py:798-803 | A ranger whose range is not in the beat map gets the statewide brief (77 divisions). |
| L4 | low | server.py:294; server.py:195-204 | The guard's alert card includes `burn_scar` (the guard list hides it), and pilot `arm`, `score` and `model_hash` reach guards. |
| L5 | low | big_watch_list.py:17-18 | `size_score` keeps a rowid table plus a separate PK index: 75 MB for three nights (1.29M rows). |
| L6 | low | big_watch_list.py:65 | The watch-list note says "about 1 in 100 of these squares gets one": a rate for big-fire info, which the owner should check against the rank-only rule. |
| L7 | low | big_fire.py:118 (`_cache`) | The in-memory big-fire cache is never trimmed (read only). |
| L8 | low | scars.py:83-111 | After the scar files change, the outline database is rebuilt inside the next request that needs outlines (read only). |
| L9 | low | brief.py:185 | "And N more new fires with fewer points" is no longer true under the combined order. |

What was checked and found sound is listed at the end.

---

## Critical

### C1 (critical): a big-fire scoring error takes down the guard's alert list and the eNetra alert API

**Where:** `app/big_fire.py:181` (new `size_at` call), `:221-224` (`guard_flag`, no guard), `app/big_watch_list.py:75` → `app/daily_list.py:50-51` (`grid()` opens `FS_MP_GRID` on the network mount, on every call); callers `app/server.py:233` (`/api/incidents`, **also for guards**), `:277` (`/api/incidents/{id}`), `app/api_v1.py:84` (every v1 alert).

**What goes wrong:** `guard_flag()` calls `check()`, and nothing around it catches errors. For any alert not yet stored in `big_fire_score`, `check()` now also runs `size_at()`. That reads `mp_grid.json` from `/mnt/project-files/ratapani/...`, runs `executescript` and builds a pyproj transformer. Any exception on that path fails the whole request. The guard's own beat list then returns 500, so the guard cannot see any of the beat's alerts, and eNetra's `GET /api/v1/alerts` and `/api/v1/alerts/{id}` fail the same way. The same holds for the older parts of `check()`: the points tables in `data/big_fire/` and the detection queries. The officials-only size score should never be able to break a guard path.

**Repro:** `t/t_sizeat_guard.py` (`FS_MP_GRID` pointed at a missing file, one new fire in the guard's beat with its stored score deleted):
```
guard: GET /api/incidents          500
guard: GET /api/incidents/{id}     500
eNetra: GET /api/v1/alerts/{id}    500
FileNotFoundError: ... mp_grid.json   (big_fire.py:181 -> big_watch_list.py:75 -> daily_list.py:51)
```
`t/t_isolation.py`, `big_fire.check` patched to raise: all seven endpoints return 500, guard list included.
**Patched:** all three return 200, and the isolation table is all 200.

<details><summary>Proposed patch</summary>

```diff
--- a/app/big_fire.py
+++ b/app/big_fire.py
@@ -178,7 +178,10 @@
         if ORDER == "combined":
             from . import big_watch_list
             day = (t0 + timedelta(hours=5, minutes=30) - timedelta(days=1)).strftime("%Y-%m-%d")   # the night before
-            size = big_watch_list.size_at(con, [(p["lat"], p["lon"]) for p in first], day)
+            try:
+                size = big_watch_list.size_at(con, [(p["lat"], p["lon"]) for p in first], day)
+            except Exception:             # grid file unreadable, bad row: order by points, never fail the alert
+                size = None
             out["order"] = big_watch_list.order_value(out["points"], size)
             out["order_basis"] = "points + size score" if out["order"] is not None else "points (no size score that night)"
         out["note"] = ("Big-fire points from the first look: the higher, the more likely this fire grows past 200 ha. "
@@ -220,7 +223,8 @@
 
 def guard_flag(con, inc, now_utc):
     """True when guards should be told this alert may become a big fire (they never see the points)."""
-    b = check(con, inc, now_utc)
+    from .hint import safe
+    b = safe(check, con, inc, now_utc)
     return bool(b and b.get("guard_flag"))
 
 
--- a/app/hint.py
+++ b/app/hint.py
@@ -0,0 +1,13 @@
+"""Officials' hints and the guards' big-fire flag must never take an alert list, card or brief down with them."""
+import logging
+
+log = logging.getLogger("hint")
+
+
+def safe(fn, *a, default=None, **k):
+    """fn(*a, **k), or `default` (logged) when it raises: a broken hint is left off the card, the alert is still shown."""
+    try:
+        return fn(*a, **k)
+    except Exception:
+        log.exception("hint %s failed", getattr(fn, "__qualname__", fn))
+        return default
```
</details>

## High

### H1 (high): no hint is isolated; one bad hint returns a 500 for the whole list, card or brief

**Where:** `app/server.py:240-248` (officials' list), `:279-294` (card), `app/api_v1.py:87-111` (`alert_json`, used by every v1 alert call, by webhooks and by the answers to reports), `app/brief.py:70-79`.

**What goes wrong:** each hint is called bare, inside the request. Examples of what makes one raise: a corrupt `fire_direction`/`fire_runway` JSON row, a `spread24` model or AOI file missing or changed (`spread24.py:175` asserts), a scar CSV being rewritten by the nightly run, a shapely error on an odd outline. Any of these turns into a 500 for every alert in the response. The brief has no fallback either.

**Repro:** `t/t_isolation.py`, each hint monkeypatched in turn to raise `RuntimeError` (200 = works, 500 = fails):
```
                       v1/alerts v1/alerts/{id} incidents(guard) incidents(admin) card(guard) api/brief /brief
direction.for_incident    500        500            200             500            200        500      500
runway.for_incident       500        500            200             500            200        500      500
still_burning.check       500        500            200             500            200        500      500
control_burn.check        500        500            200             500            200        200      200
scars.for_points          500        500            200             500            500        200      200
spread24.for_incident     200        500            200             200            200        200      200
big_fire.check            500        500            500             500            500        500      500
```
**Patched:** every cell is 200. The broken hint is logged and left off the card.

<details><summary>Proposed patch</summary>

```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -85,17 +85,18 @@
         out["big_fire_text"] = big_fire.GUARD_TEXT if out["big_fire_flag"] else None
         # officials' view only from here: eNetra should not show these to guards
         out["cause_sample"] = {"group": g, "p": con.execute("SELECT cause_p FROM incidents WHERE id=?", (r["id"],)).fetchone()[0]} if g else None
-        out["control_burn"] = control_burn.check(con, r, firms.iso(now()))
-        out["big_fire"] = big_fire.check(con, r, firms.iso(now()))
+        from .hint import safe
+        out["control_burn"] = safe(control_burn.check, con, r, firms.iso(now()))
+        out["big_fire"] = safe(big_fire.check, con, r, firms.iso(now()))
         from . import direction   # heading from a 30 m scene that caught the fire burning; null when none (hint only)
-        out["direction"] = direction.for_incident(con, r["id"], now())
+        out["direction"] = safe(direction.for_incident, con, r["id"], now())
         from . import still_burning   # chance a fire VIIRS stopped seeing is still burning; null under 6 h dark
-        out["still_burning"] = still_burning.check(con, r["id"], now())
+        out["still_burning"] = safe(still_burning.check, con, r["id"], now())
         from . import runway   # which side of a new fire likely burns farther; null when not scored (hint only)
-        out["runway"] = runway.for_incident(con, r["id"])
+        out["runway"] = safe(runway.for_incident, con, r["id"])
         if full:   # likely burnt ground 24 h after the latest VIIRS look (GeoJSON Feature); null when that look is over 24 h old
             from . import spread24
-            out["spread_24h"] = spread24.for_incident(con, r["id"], now())
+            out["spread_24h"] = safe(spread24.for_incident, con, r["id"], now())
     pts = con.execute("""SELECT source, lat, lon, acq_utc, frp, daynight, fsi_division, fsi_range, fsi_beat, fsi_compartment
                          FROM detections WHERE incident_id=?""", (r["id"],)).fetchall()
     fsi = [x for x in pts if x["fsi_beat"]]
@@ -108,7 +109,8 @@
     out["burn_hint"] = burn_hint(pts)
     # Burn scar from Sentinel-2/Landsat (burn-scar thread). none_visible is NOT a false alert:
     # small, litter-only or under-canopy fires leave no visible scar. Support for the visit only.
-    out["burn_scar"] = scars.for_points(pts, with_geometry=full)   # outline (GeoJSON) only on the detail call
+    from .hint import safe
+    out["burn_scar"] = safe(scars.for_points, pts, with_geometry=full)   # outline (GeoJSON) only on the detail call
     # Fire spreads into nearby unburned forest over the next days: in Ratapani 93% of first burns in
     # never-burned cells had a fire within 1 km in the 7 days before (FSI scouting, cold_start_cells.md).
     # watch_nearby: keep forest within 1 km on watch for 7 days. near_recent: earlier alerts within
--- a/app/brief.py
+++ b/app/brief.py
@@ -7,6 +7,7 @@
 from datetime import datetime, timedelta, timezone
 
 from . import big_fire, config, direction, firms, runway, still_burning
+from .hint import safe
 
 BRIEF_HOUR_IST = 16
 IST = timedelta(hours=5, minutes=30)
@@ -67,16 +68,16 @@
         if not r["seen_last"] or r["seen_last"] < lo72:
             continue
         p = beats.by_uid.get(r["beat_uid"], {})
-        b = big_fire.check(con, r, nu)
+        b = safe(big_fire.check, con, r, nu)
         visited = r["status"] in ("visited", "verified") or (r["first_report_utc"] or "9") <= nu
         fires.append({
             "id": r["id"], "beat": p.get("beat", r["beat_uid"]), "range": p.get("range", ""), "lat": r["lat"], "lon": r["lon"],
             "first_seen_utc": r["first_seen_utc"], "seen_last_utc": r["seen_last"], "new": r["first_seen_utc"] >= lo24,
             "visited": visited, "overdue": not visited and r["due_utc"] < nu,
             "big_fire": b, "points": b["points"] if b and b.get("new_fire") else None, "guard_flag": bool(b and b.get("guard_flag")),
-            "_order": big_fire.order_key(con, r, nu),
-            "runway": runway.for_incident(con, r["id"]), "direction": direction.for_incident(con, r["id"], now_utc),
-            "still_burning": still_burning.check(con, r["id"], now_utc), "sensors": r["sensors"]})
+            "_order": safe(big_fire.order_key, con, r, nu, default=(2, 0.0)),
+            "runway": safe(runway.for_incident, con, r["id"]), "direction": safe(direction.for_incident, con, r["id"], now_utc),
+            "still_burning": safe(still_burning.check, con, r["id"], now_utc), "sensors": r["sensors"]})
     new = [f for f in fires if f["new"]]
     new.sort(key=lambda f: (f["_order"], f["first_seen_utc"]))    # points + size score (big_fire.order_key)
     for f in fires:
--- a/app/server.py
+++ b/app/server.py
@@ -236,16 +236,17 @@
             return out
         geo = len(rows) <= 400
         from . import control_burn, direction, still_burning, runway
+        from .hint import safe
         nu = firms.iso(now())
         for r, d in zip(rows, out):
-            d["control_burn"] = control_burn.check(con, r, nu)
-            d["big_fire"] = big_fire.check(con, r, nu)    # officials: points and items, never a % (Akkshay, 18 Oct 2026)
-            d["direction"] = direction.for_incident(con, r["id"], now())   # 30 m scene arrow, officials only (18 Oct 2026)
-            d["still_burning"] = still_burning.check(con, r["id"], now())   # officials only (18 Oct 2026)
-            d["runway"] = runway.for_incident(con, r["id"])   # which side likely burns farther, officials only (18 Oct 2026)
+            d["control_burn"] = safe(control_burn.check, con, r, nu)
+            d["big_fire"] = safe(big_fire.check, con, r, nu)    # officials: points and items, never a % (Akkshay, 18 Oct 2026)
+            d["direction"] = safe(direction.for_incident, con, r["id"], now())   # 30 m scene arrow, officials only (18 Oct 2026)
+            d["still_burning"] = safe(still_burning.check, con, r["id"], now())   # officials only (18 Oct 2026)
+            d["runway"] = safe(runway.for_incident, con, r["id"])   # which side likely burns farther, officials only (18 Oct 2026)
         for d in out:
             pts = con.execute("SELECT lat, lon, acq_utc FROM detections WHERE incident_id=?", (d["id"],)).fetchall()
-            d["burn_scar"] = scars.for_points(pts, with_geometry=geo)
+            d["burn_scar"] = safe(scars.for_points, pts, with_geometry=geo)
         return out
 
 
@@ -277,21 +278,23 @@
         row["big_fire_flag"] = big_fire.guard_flag(con, r, firms.iso(now()))
         row["big_fire_text"] = big_fire.GUARD_TEXT if row["big_fire_flag"] else None
         if me["role"] != "guard":   # officials only (Akkshay, 16 Oct 2026)
+            from .hint import safe
             from . import control_burn
-            row["control_burn"] = control_burn.check(con, r, firms.iso(now()))
+            row["control_burn"] = safe(control_burn.check, con, r, firms.iso(now()))
             from . import big_fire
-            row["big_fire"] = big_fire.check(con, r, firms.iso(now()))
+            row["big_fire"] = safe(big_fire.check, con, r, firms.iso(now()))
             from . import direction
-            row["direction"] = direction.for_incident(con, r["id"], now())
+            row["direction"] = safe(direction.for_incident, con, r["id"], now())
             from . import still_burning
-            row["still_burning"] = still_burning.check(con, r["id"], now())
+            row["still_burning"] = safe(still_burning.check, con, r["id"], now())
             from . import runway
-            row["runway"] = runway.for_incident(con, r["id"])
+            row["runway"] = safe(runway.for_incident, con, r["id"])
             from . import spread24   # likely burnt ground 24 h after the latest VIIRS look, officials only (19 Oct 2026)
-            row["spread_24h"] = spread24.for_incident(con, r["id"], now()) if (r["kind"] or "alert") == "alert" else None
+            row["spread_24h"] = safe(spread24.for_incident, con, r["id"], now()) if (r["kind"] or "alert") == "alert" else None
     from . import scars
     fsi = next((x for x in dets if x.get("fsi_beat")), None)
-    return row | {"detections": dets, "reports": reps, "reviews": revs, "burn_scar": scars.for_points(dets, with_geometry=True),
+    from .hint import safe
+    return row | {"detections": dets, "reports": reps, "reviews": revs, "burn_scar": safe(scars.for_points, dets, with_geometry=True),
                   "fsi_compartments": sorted({x["fsi_compartment"] for x in dets if x.get("fsi_compartment")}),
                   "fsi_beat": fsi and fsi["fsi_beat"]}
 
```
</details>

### H3 (high): unauthenticated, unlimited JSON bodies are read and parsed before the key check

**Where:** `app/api_v1.py:20-23` (`service` is a `Depends`), and every route with `body: dict` / `List[dict]` / pydantic bodies (`:314` daily_scores, `:339` big_watch_scores, `:373` tasks, `:460` grouping). `app/server.py` has no body limit and listens on `0.0.0.0`.

**What goes wrong:** FastAPI reads the whole request body and parses the JSON before it resolves `Depends(service)`, and uvicorn sets no size limit. Anyone who can reach the port can send a large body and make the server read it, parse it and hold it in memory. The process does not give that memory back. The legitimate 418k-row `daily_scores` body is 17.5 MB and the 430k-square big-watch body is 7.9 MB, so a 100 MB cap is safe.

**Repro:** `t/t_unauth_body.py`, 119 MB body to `/api/v1/big_watch_scores`:
```
key wrong  -> 401 after 7.4 s, RSS 445 -> 1324 MB
no key     -> 401 after 8.4 s, RSS 1211 -> 2089 MB   (memory not returned)
```
**Patched** (middleware checks the key and Content-Length first): 401 in 0.0 s, RSS unchanged at 445 MB. The 418k-row body still posts (200). A chunked body with no Content-Length is not capped, but it is still refused before it is read when the key is wrong.

<details><summary>Proposed patch</summary>

```diff
--- a/app/server.py
+++ b/app/server.py
@@ -5,7 +5,7 @@
 from typing import List, Optional
 
 from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
-from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
+from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
 from fastapi.staticfiles import StaticFiles
 from pydantic import BaseModel
 
@@ -19,6 +19,20 @@
 app = FastAPI(title="Van Agni field checks")
 app.mount("/static", StaticFiles(directory=STATIC), name="static")
 BEATS: Beats = None
+MAX_BODY = int(float(__import__("os").environ.get("FS_MAX_BODY_MB", "100")) * 2 ** 20)   # 6 photos x 15 MB + form
+
+
+@app.middleware("http")
+async def refuse_early(request, call_next):
+    """Check the service key and the body size before the body is read (FastAPI reads and parses the JSON body
+    before it runs Depends(service), so a wrong key still cost the full parse)."""
+    if request.url.path.startswith("/api/v1/") and (
+            not config.SERVICE_KEYS or request.headers.get("x-api-key", "") not in config.SERVICE_KEYS):
+        return JSONResponse({"detail": "missing or wrong X-Api-Key"}, status_code=401)
+    n = request.headers.get("content-length")
+    if n and n.isdigit() and int(n) > MAX_BODY:
+        return JSONResponse({"detail": f"body over {MAX_BODY >> 20} MB"}, status_code=413)
+    return await call_next(request)
 
 
 def BEATS_REF():
```
</details>

### H4 (high): guard-facing v1 calls return officials-only fields

**Where:** `app/api_v1.py:86-111` ("eNetra should not show these to guards"), returned by `v1_report` (`:190`), `v1_chance` (`:406`) and `v1_alerts` (`:157`), and pushed in webhooks (`:191, 223, 254, 389, 407`).

**What goes wrong:** the API has no guard view. When a guard files a report from eNetra, the answer goes back to that guard's phone and includes `cause_sample` (tagged or random group and p, which `server.cause_fields` deliberately hides from guards), `big_fire` (points and items), `direction`, `runway`, `still_burning` (a %), `control_burn` and `burn_scar`. Whether guards see these depends entirely on eNetra filtering them. The built-in app (`server.py`) does filter.

**Repro:** `t/t_guard.py`: `POST /api/v1/alerts/{id}/reports` (guard's report) → `alert` carries `big_fire, burn_scar, cause_sample, control_burn, direction, runway, still_burning`; for example `"runway": {"text": "Likely to burn farther toward the S (uphill)..."}`.
**Patched:** that answer carries none of them. `GET /api/v1/alerts?view=guard` gives the same guard view for listing. Webhooks still carry the official view, since the platform gets everything; INTEGRATION.md should say so.

<details><summary>Proposed patch</summary>

```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -53,7 +53,19 @@
     return search_m(con, iid)
 
 
-def alert_json(con, r, full=False):
+OFFICIALS_ONLY = ("cause_sample", "control_burn", "big_fire", "direction", "still_burning", "runway", "spread_24h", "burn_scar")
+
+
+def alert_json(con, r, full=False, view="official"):
+    """view='guard' leaves out the officials-only hints (for answers that go back to a guard's phone)."""
+    out = _alert_json(con, r, full)
+    if view == "guard":
+        for k in OFFICIALS_ONLY:
+            out.pop(k, None)
+    return out
+
+
+def _alert_json(con, r, full=False):
     B = BEATS_REF()
     beats = [x["beat_uid"] for x in con.execute("SELECT beat_uid FROM incident_beats WHERE incident_id=?", (r["id"],))]
     p = B.by_uid.get(r["beat_uid"], {})
@@ -138,7 +150,8 @@
 
 @app.get("/api/v1/alerts", dependencies=[Depends(service)])
 def v1_alerts(since: Optional[str] = None, division: Optional[str] = None, range_name: Optional[str] = None,
-              beat_uid: Optional[str] = None, status: Optional[str] = None, kind: Optional[str] = None, limit: int = 1000):
+              beat_uid: Optional[str] = None, status: Optional[str] = None, kind: Optional[str] = None, limit: int = 1000,
+              view: str = "official"):
     """Alerts changed since a time (pass the max 'updated' you saw), newest first, filtered by area.
     kind: alert (satellite), predicted (pilot cell checks), chance (fires found with no task); default all."""
     q, args = "SELECT i.* FROM incidents i WHERE 1=1", []
@@ -156,7 +169,7 @@
         args.append(beat_uid)
     with db.tx() as con:
         rows = con.execute(q + " ORDER BY i.first_seen_utc DESC LIMIT ?", args + [min(limit, 5000)]).fetchall()
-        out = [alert_json(con, r) for r in rows]
+        out = [alert_json(con, r, view=view) for r in rows]   # view=guard for a guard's phone
     if division or range_name:
         out = [a for a in out if (not division or a["division"] == division) and (not range_name or a["range"] == range_name)]
     return {"type": "FeatureCollection", "generated_utc": firms.iso(now()), "features": [
@@ -189,7 +202,7 @@
             raise HTTPException(404)
         sid = staff_id(con, staff_external_id, staff_name, inc["beat_uid"])
         res = record_report(con, inc, sid, f, raw, json.loads(photo_meta or "[]"))
-        res["alert"] = alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone())
+        res["alert"] = alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone(), view="guard")
     webhook.send("alert.reported", res["alert"])
     return res
 
@@ -405,7 +418,7 @@
         sid = staff_id(con, staff_external_id, staff_name)
         st = dict(con.execute("SELECT * FROM staff WHERE id=?", (sid,)).fetchone())
         res = record_chance(con, st, f, raw, json.loads(photo_meta or "[]"))
-        res["alert"] = alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (res["incident_id"],)).fetchone())
+        res["alert"] = alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (res["incident_id"],)).fetchone(), view="guard")
     webhook.send("alert.reported", res["alert"])
     return res
 
```
</details>

### H5 (high): big-fire scoring holds the write lock across network reads; uncached briefs take minutes

**Where:** `app/big_fire.py:197-204` (`score_new`: one transaction for every new alert), `:102-115` (`_crop` → `landcover.WorldCover`, HTTP range reads with `timeout=60`, `landcover.py:21,35`, behind one global lock), `:188` (INSERT). Lazy scoring in requests: `brief.py:70/77`, `server.py:233/242`, `api_v1.py:84/89`.

**What goes wrong:** after the first alert's INSERT, the poll thread holds SQLite's RESERVED lock while it reads WorldCover for the next alert. Every write in the app (guard reports, positions, reviews, the daily-scores post) waits for it, and with `connect(timeout=30)` a slow S3 read makes them fail with "database is locked". In combined mode the lock is released by accident, because `size_at`'s `executescript` commits (M1), but the wait still lasts as long as the read. In request paths, whenever scores are missing (poll thread failing, see M3, or a fresh or restored database), each unscored alert costs a WorldCover read inside the request.

**Repro:** `t/t_lock.py`, `_crop` stalled 35 s, a review INSERT from a second connection during `score_new`:
```
FS_NEWFIRE_ORDER=points : concurrent write FAILED after 30.1 s: database is locked
combined (default)      : concurrent write OK after 29.5 s   (0.5 s from failing)
```
`t/t_brief_cost.py`, 210 new fires in one division (Dindori):
```
cached scores                        0.10 s   1,019 SQL statements
cached scores (2nd)                  0.04 s     816
no stored big-fire score (WorldCover) 90.77 s  2,470
statewide (77 divisions, cached)      1.36 s
```
`t/t_listcost.py` (scores cached): admin `/api/incidents?days=7` 1.0 s (1,748 alerts); `/api/v1/alerts` limit 5000 4.4 s (7.4 MB); statewide `/api/brief` 2.1 s. With about 300 alerts unscored (WorldCover reads in the request), the same admin call had not answered when the 15-minute test limit killed it.
**Patched** (commit after each alert in `score_new`): the concurrent write goes through in 0.0 s. Further step, not in the diff: give `check()` a `score=False` mode for the list and brief paths, so that only the poll thread does WorldCover reads.

<details><summary>Proposed patch</summary>

```diff
--- a/app/big_fire.py
+++ b/app/big_fire.py
@@ -204,6 +204,7 @@
                            (firms.iso(now_utc - timedelta(days=days)), firms.iso(now_utc - timedelta(minutes=30)))).fetchall()
         for r in rows:
             check(con, r, firms.iso(now_utc), beats)
+            con.commit()      # release the write lock before the next alert's WorldCover read (network, up to 60 s)
     return len(rows)
 
 
```
</details>

## Medium

### M1 (medium): `executescript()` on read paths commits the caller's transaction

**Where:** `app/big_watch_list.py:74` (`size_at`), `:56` (`division_view`), `:32` (`store`), `app/api_v1.py:355`.

**What goes wrong:** Python's `sqlite3.executescript` first COMMITs any open transaction. `size_at` runs in the middle of other work, for example inside `alert_json` right after `record_report` has written a guard's report. If a later hint then raises, the client gets a 500, but the report is already committed. The phone retries and files a second report, and the photos are on disk twice. The tables are already created by `db.init()` (`db.py:216-217`).

**Repro:** `t/lockcheck.py`: a row inserted before `executescript(SCHEMA)` survives `rollback()` (True). `t/t_partial.py`, `direction.for_incident` raising:
```
alert not yet scored  two tries -> [500, 500]; reports stored: 1   <- 500 but saved
alert already scored  two tries -> [500, 500]; reports stored: 0
```
With H1 applied, both tries return 200 and both reports are stored, as intended for two sends. Removing `executescript` makes the "500 but saved" case impossible.

<details><summary>Proposed patch</summary>

```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -367,7 +367,6 @@
     """One division's big-fire watch list (top 1-2% of its squares, rank only, officials only)."""
     from . import big_watch_list
     with db.tx() as con:
-        con.executescript(big_watch_list.SCHEMA)
         day = day or (con.execute("SELECT max(issue_date) FROM big_watch_meta").fetchone()[0] or "")
         v = big_watch_list.division_view(con, day, division, BEATS_REF())
     if not v:
--- a/app/big_watch_list.py
+++ b/app/big_watch_list.py
@@ -53,7 +53,6 @@
 
 def division_view(con, day, division, beats):
     """One division's watch list, best rank first, with beat and range. Rank only, no %."""
-    con.executescript(SCHEMA)
     if not con.execute("SELECT 1 FROM big_watch_meta WHERE issue_date=?", (day,)).fetchone():
         return None
     rows = [dict(r) for r in con.execute(
@@ -71,8 +70,7 @@
     import math
     from pyproj import Transformer
     from .daily_list import grid
-    con.executescript(SCHEMA)
-    g = grid()
+    g = grid()                       # tables come from db.init(); executescript() here COMMITted the caller's transaction
     x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform([p[1] for p in latlons], [p[0] for p in latlons])
     cells = {(int((g["Y1"] - yy) // g["S"]) + a) * g["W"] + int((xx - g["X0"]) // g["S"]) + b
              for xx, yy in zip(x, y) for a in (-1, 0, 1) for b in (-1, 0, 1)}
```
</details>

### M2 (medium): runway hints: one bad fire blocks all; transient errors are never retried

**Where:** `app/runway.py:171-193`.

**What goes wrong:** `first_look()` (which calls `big_fire.check`) is outside the `try`. One fire that raises aborts `run_due`, and because it is the newest unscored fire, the next loop picks it again first. Runway hints stop for every fire until that one is two days old. Separately, a network error inside `compute()` is stored as `status='error'`, and `f.incident_id IS NULL` never selects it again, so a 2-minute S3 outage loses the hint for those fires for good.

**Repro:** `t/t_runway.py`:
```
(a) run 1: run_due raised OSError('points table unreadable')   fires stored: 0 of 5
    run 2: run_due raised OSError('points table unreadable')   fires stored: 0 of 5
(b) after a transient error and a later run: status 'error'
```
**Patched:** (a) 5 of 5 stored on both runs; (b) the next hourly retry gives `found`.

<details><summary>Proposed patch</summary>

```diff
--- a/app/runway.py
+++ b/app/runway.py
@@ -177,21 +177,20 @@
         if ids is None:
             ids = [r["id"] for r in con.execute(
                 """SELECT i.id FROM incidents i LEFT JOIN fire_runway f ON f.incident_id=i.id
-                   WHERE COALESCE(i.kind,'alert')='alert' AND f.incident_id IS NULL AND i.first_seen_utc >= ? AND i.first_seen_utc <= ?
-                   ORDER BY i.first_seen_utc DESC LIMIT ?""",
-                (firms.iso(now_utc - timedelta(days=2)), firms.iso(now_utc - timedelta(minutes=30)), limit))]
+                   WHERE COALESCE(i.kind,'alert')='alert' AND i.first_seen_utc >= ? AND i.first_seen_utc <= ?
+                   AND (f.incident_id IS NULL OR (f.status='error' AND f.checked_utc <= ?))
+                   ORDER BY f.incident_id IS NOT NULL, i.first_seen_utc DESC LIMIT ?""",
+                (firms.iso(now_utc - timedelta(days=2)), firms.iso(now_utc - timedelta(minutes=30)),
+                 firms.iso(now_utc - timedelta(hours=1)), limit))]   # an error (network) is retried hourly
     n = 0
     for iid in ids:
-        with db.tx() as con:
-            inc = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
-            look = first_look(con, inc, now_utc)
-        if look is None:
-            res = {"status": "not_new_fire"}
-        else:
-            try:
-                res = compute([(*to43(d["lon"], d["lat"]), d["frp"]) for d in look])
-            except Exception as e:
-                res = {"status": "error", "error": str(e)[:200]}
+        try:          # one bad fire must not stop the others (it used to raise out of the loop, every loop)
+            with db.tx() as con:
+                inc = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
+                look = first_look(con, inc, now_utc)
+            res = {"status": "not_new_fire"} if look is None else compute([(*to43(d["lon"], d["lat"]), d["frp"]) for d in look])
+        except Exception as e:
+            res = {"status": "error", "error": str(e)[:200]}
         with db.tx() as con:
             con.execute("INSERT OR REPLACE INTO fire_runway VALUES (?,?,?,?)", (iid, firms.iso(now_utc), res["status"], json.dumps(res)))
         n += 1
```
</details>

### M3 (medium): a big-fire scoring failure skips the daily scar run

**Where:** `app/server.py:78-91`: `run_live`, `score_new`, `PRAGMA optimize` and `scar_live.run_if_due` share one `try`.

**What goes wrong:** if `score_new` raises on every pass (for example a missing points table, or C1's grid file), the burn-scar run never starts and the scar layer goes stale with no other sign.

**Repro:** `t/t_poller.py`: `poll pass ran: ['run_live', 'score_new'] -> scar_live called: False`. **Patched:** `['run_live', 'score_new', 'scar_live']`.

<details><summary>Proposed patch</summary>

```diff
--- a/app/server.py
+++ b/app/server.py
@@ -95,13 +95,19 @@
         try:
             firms.run_live(BEATS, "7d" if first else "24h")
             first = False
+        except Exception:
+            log.exception("poll failed")
+        try:          # its own step: a failing hint must not stop the optimize and the daily scar run below
             from . import big_fire
             big_fire.score_new(now(), BEATS)   # so the officials' list and guard flags never score hundreds at once
+        except Exception:
+            log.exception("big-fire scoring failed")
+        try:
             with db.tx() as con:
                 con.execute("PRAGMA optimize")
             scar_live.run_if_due()   # once a day, in the background
         except Exception:
-            log.exception("poll failed")
+            log.exception("scar run failed")
         time.sleep(config.POLL_MINUTES * 60)
 
 
```
</details>

### M4 (medium): the 16:00 brief has no 2-day list and says nothing; stale-input flags are dropped

**Where:** `app/brief.py:102-111` (`_check_list` returns None when the list is missing and swallows every error), `brief.py:9-10` (16:00 IST) against `scripts/cloud_daily.py:2` ("~17:15 IST"), `app/daily_list.py:180-183` (the body's `inputs`/`stale` is not stored), `app/api_v1.py:331` (`GET /api/v1/daily_list` defaults to the newest list, without saying whether it is today's).

**What goes wrong:** the brief clock is 16:00 IST, and the runner posts the day's list about 75-90 minutes later. Anyone who opens the brief between 16:00 and about 17:30 IST, or on a day the runner failed, sees a brief with no "Check in the next 2 days" section and no explanation. The same happens if `division_view` raises. When the runner reports stale soil or MODIS, or that FIRMS failed (`inputs.stale`), the app drops it, so officials cannot tell a list built on stale inputs from a good one. The other cases checked: scores arriving twice is safe (the day is replaced, `daily_list.py:184-188`). Scores arriving late are safe for that day (the quiet mask stays cut at 16:00 IST), but the next days' danger scaling already ran without that day's mean, and it is not recomputed.

**Repro:** `t/t_brief_past.py`: no list for the day → `check_list = None`, and the page never mentions the 2-day list.
**Patched:** `check_list = {'missing': '2026-04-22', 'why': 'not received yet (the evening run posts it at about 17:30 IST)'}`, the page shows that line, and `inputs.stale` is shown under the table. A further question for the owner: should the brief clock move to 18:00 IST, or should the runner post before 16:00?

<details><summary>Proposed patch</summary>

```diff
--- a/app/brief.py
+++ b/app/brief.py
@@ -103,12 +103,15 @@
 def _check_list(con, division, now_utc, beats):
     """Today's 2-day check list for the division (app/daily_list.py), if the pipeline sent one."""
     from . import daily_list
+    day = (now_utc + IST).strftime("%Y-%m-%d")
     try:
-        v = daily_list.division_view(con, (now_utc + IST).strftime("%Y-%m-%d"), division, beats)
+        v = daily_list.division_view(con, day, division, beats)
     except Exception:
-        return None
-    if v:
-        v.pop("cells")
+        import logging; logging.getLogger("brief").exception("check list for %s %s", division, day)
+        return {"missing": day, "why": "could not be read"}
+    if not v:     # the cloud run posts at ~17:15 IST, after the 16:00 brief; say so instead of leaving the section out
+        return {"missing": day, "why": "not received yet (the evening run posts it at about 17:30 IST)"}
+    v.pop("cells")
     return v
 
 
@@ -161,6 +164,10 @@
 def _check_html(v):
     if not v:
         return ""
+    if v.get("missing"):
+        return f'<h2>Check in the next 2 days</h2><p class="h warn">The list for {E(v["missing"])} is {E(v["why"])}.</p>'
+    st = (v.get("statewide") or {}).get("stale")
+    stale = f'<p class="h warn">Some inputs were old or missing for this list: {E(", ".join(st))}.</p>' if st else ""
     r = v["by_reason"]
     rows = "".join(f'<tr><td>{E(g["range"] or "-")}</td><td class="n">{g["squares"]}</td><td class="n">{g["beats"]}</td>'
                    f'<td class="n">{g["quiet"]}</td></tr>' for g in v["by_range"][:12])
@@ -168,7 +175,7 @@
             f'{r["division"]} kept for the division, {r["quiet square"]} quiet squares (no fire within 5 km for 7 days), '
             f'{r["statewide"]} from the statewide pool. Busy divisions borrow checks from quiet ones; every division '
             f'keeps at least half its own count.</div><table><tr><th>Range</th><th class="n">Squares</th><th class="n">Beats</th>'
-            f'<th class="n">Quiet</th></tr>{rows}</table>')
+            f'<th class="n">Quiet</th></tr>{rows}</table>{stale}')
 
 
 def render(b, top=8, few=5):
--- a/app/daily_list.py
+++ b/app/daily_list.py
@@ -180,7 +180,8 @@
     summary = {"total": int(sum(n.values())), "flagged": len(rows), "rule": rule,
                "by_reason": {r: int((why == r).sum()) for r in ("division", "quiet square", "statewide")},
                "quiet_flags": int(quiet[sel].sum()) if len(sel) else 0, "divisions_below_half": short,
-               "squares_scored": int(len(cid)), "quiet_squares": int(quiet.sum()), "as_of_utc": until.strftime("%Y-%m-%dT%H:%M:%SZ")}
+               "squares_scored": int(len(cid)), "quiet_squares": int(quiet.sum()), "as_of_utc": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
+               "stale": list((body.get("inputs") or {}).get("stale") or [])}   # the runner's own input-age check
     con.execute("DELETE FROM daily_list WHERE issue_date=?", (day,))
     con.executemany("INSERT INTO daily_list VALUES (?,?,?,?,?,?,?,?)", rows)
     con.execute("INSERT OR REPLACE INTO daily_list_meta VALUES (?,?,?,?,?,?,?)",
```
</details>

### M5 (medium): combined order: a fire with no size score sinks below every fire with one, and stays there

**Where:** `app/big_fire.py:227-234` (`order_key` puts it in tier `(1, -points)`, below every `(0, -order)`), `:181-188` (an order of `None` is stored in `big_fire_score` for good), `app/brief.py:81` (sort), `:198` (heading text).

**What goes wrong:** `size_at()` returns None for one of three reasons: the night's run had not been posted when the fire was first scored (30 min after its first look), the run failed, or none of the 3 x 3 squares under the first-look dots have a score. That fire then sorts after **all** fires that got a size score, even ones with negative points. Because `check()` stores the result once, a runner post that arrives late (the runner skips the big-fire list when the daily list fails, `cloud_daily.py:395-405`, and `big_watch.py` may take up to an hour) never fixes it, even after a restart. In the 16:00 brief all new fires use the same night (D-1), so a night that is missing entirely is a uniform fall-back to points. The ordering breaks when coverage is partial, or when the run lands between the 01:30 and 13:30 IST passes. The heading still says "together with the square's size score from the night before".

**Repro:** `t/t_order.py`:
```
(a) order_key: 20 points, no size -> (1, -20.0); 0 points, size 0.001 -> (0, -0.0013): the 0-point fire goes first
(b) scored before that night's run arrived: order None
    after the run arrived (cache cleared, as after a restart): order None   <- size_at now returns 0.9
```
`t/t_order2.py`, real brief for East Mandla, with size scores for every in-beat square from the 21 Apr run: new fires listed as points 3, 2, 1, 1, -1, -1, -1, **4**. The 4-point fire's first-look squares are not in the table (4 of 276 new fires that day).
**Patched:** the order is recomputed when the brief is built, falling back to the night's mean size when the squares have none. Largest points inversion across all 77 divisions: 0.

<details><summary>Proposed patch</summary>

```diff
--- a/app/big_fire.py
+++ b/app/big_fire.py
@@ -234,6 +234,16 @@
     b = check(con, inc, now_utc, with_chance=True)
     if not b or not b.get("new_fire"):
         return (2, 0.0)
-    if b.get("order") is not None:
-        return (0, -b["order"])
-    return (1, -float(b.get("points") or 0))
+    if ORDER != "combined":
+        return (1, -float(b.get("points") or 0))
+    o = b.get("order")
+    if o is None:     # no size score when it was scored (run late or failed): look again now; else that night's mean,
+        from . import big_watch_list   # so a 20-point fire never sinks below every fire that happened to get a size score
+        day = (firms.parse_utc(b["first_look_utc"]) + timedelta(hours=5, minutes=30) - timedelta(days=1)).strftime("%Y-%m-%d")
+        size = big_watch_list.size_at(con, [(inc["lat"], inc["lon"])], day)
+        if size is None:
+            r = con.execute("SELECT avg(score) FROM size_score WHERE issue_date=(SELECT max(issue_date) FROM size_score WHERE issue_date<=?)",
+                            (day,)).fetchone()
+            size = r[0] if r and r[0] is not None else None
+        o = big_watch_list.order_value(b.get("points") or 0, size)
+    return (0, -o) if o is not None else (1, -float(b.get("points") or 0))
```
</details>

### M6 (medium): the control room and the brief show officials two different orders

**Where:** `app/static/control.html:118-121` (the "Big-fire watch" drawer sorts by `points`), `:110`; `app/brief.py:81` (combined order), `:185`, `:198`.

**What goes wrong:** the same officials see new fires ranked by points on the dashboard and by points plus size score in the brief. `order` is hidden (correctly), so the page cannot reproduce the brief's order.

**Repro (read and data):** in `t/t_order2.py` the brief order for East Mandla (3, 2, 1, 1, -1, -1, -1, 4) differs from the drawer's points order (4, 3, 2, ...). **Patched:** `/api/incidents` adds `big_fire.order_rank` (a rank only, no value), and the drawer sorts by it. `t/t_leak.py` was re-checked: no hidden value appears.

<details><summary>Proposed patch</summary>

```diff
--- a/app/server.py
+++ b/app/server.py
@@ -264,6 +264,10 @@
             d["direction"] = safe(direction.for_incident, con, r["id"], now())   # 30 m scene arrow, officials only (18 Oct 2026)
             d["still_burning"] = safe(still_burning.check, con, r["id"], now())   # officials only (18 Oct 2026)
             d["runway"] = safe(runway.for_incident, con, r["id"])   # which side likely burns farther, officials only (18 Oct 2026)
+        new = [(safe(big_fire.order_key, con, r, nu, default=(2, 0.0)), r["first_seen_utc"], d) for r, d in zip(rows, out)
+               if d.get("big_fire") and d["big_fire"].get("new_fire")]
+        for k, (_, _, d) in enumerate(sorted(new, key=lambda x: x[:2])):
+            d["big_fire"] = dict(d["big_fire"], order_rank=k + 1)    # the brief's order, as a rank only
         for d in out:
             pts = con.execute("SELECT lat, lon, acq_utc FROM detections WHERE incident_id=?", (d["id"],)).fetchall()
             d["burn_scar"] = safe(scars.for_points, pts, with_geometry=geo)
--- a/app/static/control.html
+++ b/app/static/control.html
@@ -118,7 +118,7 @@
 function bigWatch() {
   const now = Date.now() + CLOCK, d = document.getElementById('drawer');
   const rows = INC.filter(i => i.big_fire?.new_fire && now - new Date(i.big_fire.first_look_utc) <= 864e5 && now >= new Date(i.big_fire.first_look_utc))
-    .sort((a, b) => b.big_fire.points - a.big_fire.points);
+    .sort((a, b) => (a.big_fire.order_rank ?? 1e9) - (b.big_fire.order_rank ?? 1e9) || b.big_fire.points - a.big_fire.points);   // same order as the brief
   const told = rows.filter(i => i.big_fire.guard_flag).length;
   d.innerHTML = `<button class="btn alt" onclick="drawer.classList.remove('open')" style="float:right">Close</button>
     <h2 style="margin:0 0 4px">Big-fire watch · new fires in the last 24 h</h2>
```
</details>

### M7 (medium): a WorldCover failure is stored for good (farmland item lost)

**Where:** `app/big_fire.py:102-115` (`_crop` returns None on any error), `:186-188` (stored once, at first look + 30 min).

**What goes wrong:** one failed read, such as an S3 timeout or a proxy hiccup, is stored as `farmland_checked: false`, and that fire never gets its +/- farmland item, even after WorldCover is back. The card says "land cover map unreachable" for good.

**Repro:** `t/t_misc.py`: during the outage `farmland_checked False`; afterwards (cache cleared), the stored row is still `False`.
**Patched:** within 6 h of the first look the score is not stored when farmland was not checked; it is rescored on the next poll. Result: "nothing stored (will be rescored)".

<details><summary>Proposed patch</summary>

```diff
--- a/app/big_fire.py
+++ b/app/big_fire.py
@@ -186,7 +186,8 @@
             out["order_basis"] = "points + size score" if out["order"] is not None else "points (no size score that night)"
         out["note"] = ("Big-fire points from the first look: the higher, the more likely this fire grows past 200 ha. "
                        "Use them to order the day's new fires, not as a %.")
-    if now_utc >= firms.iso(t0 + timedelta(minutes=30)):
+    retry = out.get("farmland_checked") is False and now_utc < firms.iso(t0 + timedelta(hours=6))   # WorldCover was down
+    if now_utc >= firms.iso(t0 + timedelta(minutes=30)) and not retry:
         _cache[key] = out                 # the first look is complete; nothing later changes it
         con.execute("INSERT OR REPLACE INTO big_fire_score VALUES (?,?)", (inc["id"], json.dumps(out)))
     return out if with_chance else {k: v for k, v in out.items() if k not in HIDDEN}
```
</details>

### M8 (medium): `POST /api/v1/daily_scores` input validation

**Where:** `app/daily_list.py:146-188`, `app/api_v1.py:322` (only `KeyError`/`ValueError` become 400).

**What goes wrong:** bad bodies give 500 with no message for the runner, or worse, are accepted. A body whose cells are all invalid (null or NaN cast to garbage) is accepted with 200, and the stored list for that day becomes empty. Duplicate `(cell, division)` rows give `IntegrityError` and a 500.

**Repro:** `t/t_daily418.py`, `t/t_daily500.py`:
```
pct shorter than cell  500        cell null      200 {"total":0,"flagged":0,...}  <- day replaced by an empty list
cell outside the grid  500        division list shorter 500
duplicate (cell, division) rows -> sqlite3.IntegrityError (500)
418k-row valid body: 200 in 3.5-6.3 s, +130 MB RSS; a resend replaces (41,803 rows either way)
```
**Patched:** all of these give 400 with a message, duplicates are kept once, and the valid 418k body is unchanged (200, 2.5-4.3 s).

<details><summary>Proposed patch</summary>

```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -334,7 +334,7 @@
     try:
         with db.tx() as con:
             return daily_list.build(con, BEATS_REF(), body, now())
-    except (KeyError, ValueError) as e:
+    except (KeyError, ValueError, TypeError, IndexError) as e:
         raise HTTPException(400, str(e))
 
 
--- a/app/daily_list.py
+++ b/app/daily_list.py
@@ -148,7 +148,16 @@
     per square, 0-1, previous season's calibration], score [raw model score]; optional division [per row: the division whose model scored it], counts {division: n} (else the
     danger-scaled rule here), base_share {division: share}, rule ('pool' | 'division'), as_of_utc (replays)."""
     day = body["issue_date"]
+    datetime.strptime(day, "%Y-%m-%d")
     cid, pct, score = (np.asarray(body[k], dtype=float) for k in ("cell", "pct", "score"))
+    n_rows = len(cid)
+    if not n_rows or len(pct) != n_rows or len(score) != n_rows or (body.get("division") and len(body["division"]) != n_rows):
+        raise ValueError("cell, pct, score (and division) must be non-empty lists of the same length")
+    if not (np.isfinite(cid).all() and np.isfinite(pct).all() and np.isfinite(score).all()):
+        raise ValueError("cell, pct and score must be numbers")
+    g0 = grid()
+    if cid.min() < 0 or cid.max() >= g0["H"] * g0["W"]:
+        raise ValueError("cell id outside mp_grid")
     cid = cid.astype(np.int64)
     all_c, _, _, all_beat = cells()
     pos = {c: i for i, c in enumerate(all_c)}
@@ -172,7 +181,8 @@
     n = body.get("counts") or counts(con, day, div_cells, div_mean, body.get("base_share"))
     rule = body.get("rule") or RULE
     sel, why = select(div, pct, score, quiet, n, rule)
-    rows = [(day, int(cid[i]), div[i], beat[i], float(pct[i]), float(score[i]), w, int(quiet[i])) for i, w in zip(sel, why)]
+    rows = list({(int(cid[i]), div[i]): (day, int(cid[i]), div[i], beat[i], float(pct[i]), float(score[i]), w, int(quiet[i]))
+                 for i, w in zip(sel, why)}.values())      # a repeated (square, division) row is kept once, not a 500
     got = {}
     for i in sel:
         got[div[i]] = got.get(div[i], 0) + 1
```
</details>

## Low

### L1 (low): a brief for a past clock shows later visits as done

**Where:** `app/brief.py:71`. `status in ('visited','verified')` is the status now, not at the brief's clock.
**Repro:** `t/t_brief_past.py`: clock 22 Apr 10:30Z, report filed 23 Apr → `visited: True, overdue: False`. **Patched:** `visited: False, overdue: True`.

<details><summary>Proposed patch</summary>

```diff
--- a/app/brief.py
+++ b/app/brief.py
@@ -69,7 +69,7 @@
             continue
         p = beats.by_uid.get(r["beat_uid"], {})
         b = safe(big_fire.check, con, r, nu)
-        visited = r["status"] in ("visited", "verified") or (r["first_report_utc"] or "9") <= nu
+        visited = (r["first_report_utc"] or "9") <= nu     # as of the brief's clock, also for a past day
         fires.append({
             "id": r["id"], "beat": p.get("beat", r["beat_uid"]), "range": p.get("range", ""), "lat": r["lat"], "lon": r["lon"],
             "first_seen_utc": r["first_seen_utc"], "seen_last_utc": r["seen_last"], "new": r["first_seen_utc"] >= lo24,
```
</details>

### L2 (low): the 2-hour CDSE recheck is never used

**Where:** `app/direction.py:175-178` defines `recheck_h()` (2 h when CDSE answers); `:186` uses the constant `RECHECK_H = 6`. Same-day Sentinel-2 scenes (online ~16:00 IST) are therefore seen up to 6 h late.
**Repro:** `t/t_runway.py (c)`: `run_due uses recheck_h(): False`. **Patched:** `True`.
Read only: `PER_RUN = 30` fires per pass at roughly 20-40 s each (`direction_check.py` header) is about 60-90 fires an hour, fewer than a peak day's three-day fire count. New fires go first, so older fires mostly get no arrow, and runway (same thread, after direction) waits behind it.

<details><summary>Proposed patch</summary>

```diff
--- a/app/direction.py
+++ b/app/direction.py
@@ -183,7 +183,7 @@
     """Check alerts seen by VIIRS in the last 3 days whose last check is 6 h old or more (newest alerts first).
     A 'found' arrow is kept until a newer scene gives a new one. Returns how many were checked."""
     from . import db, firms
-    lo, re = firms.iso(now_utc - timedelta(days=LOOK_DAYS)), firms.iso(now_utc - timedelta(hours=RECHECK_H))
+    lo, re = firms.iso(now_utc - timedelta(days=LOOK_DAYS)), firms.iso(now_utc - timedelta(hours=recheck_h()))
     with db.tx() as con:
         todo = [r["id"] for r in con.execute(
             """SELECT i.id FROM incidents i LEFT JOIN fire_direction f ON f.incident_id=i.id
```
</details>

### L3 (low): a ranger whose range is not in the beat map gets the statewide brief

**Where:** `app/server.py:798-803`: `_brief_division` returns None, which `brief_json`/`brief_page` treat as statewide.
**Repro:** `t/t_misc.py (b)`: a ranger with `range_name='No such range'` gets the statewide brief, 77 divisions. **Patched:** 403 with a message.

<details><summary>Proposed patch</summary>

```diff
--- a/app/server.py
+++ b/app/server.py
@@ -826,7 +826,9 @@
     """Range officers get their own division; admins pick one (None = statewide)."""
     if me["role"] == "ranger":
         uids = BEATS.in_range(me["range_name"])
-        return BEATS.by_uid[uids[0]].get("division") if uids else None
+        if not uids:      # a ranger whose range is not in the beat map must not get the statewide page
+            raise HTTPException(403, "your range is not in the beat map; ask an admin")
+        return BEATS.by_uid[uids[0]].get("division")
     return division
 
 
```
</details>

### L4 (low): guards' card carries the burn scar; pilot fields reach guards

**Where:** `app/server.py:294` (`burn_scar` for every role; the list at `:235` hides it from guards as "for officials"), `server.py:195-204` (`inc_row` = every incident column).
**Repro:** `t/t_guard.py`: guard `/api/incidents/{id}` → `burn_scar, arm, model_hash, score`; guard `/api/incidents` → `arm, model_hash, score`.
**Patched (diff covers burn_scar only):** the guard card has no `burn_scar`. Whether `arm`, `score` and `model_hash` may reach guards is for the pilot protocol owner. They are not part of this area, so there is no diff.

<details><summary>Proposed patch</summary>

```diff
--- a/app/server.py
+++ b/app/server.py
@@ -318,7 +318,8 @@
     from . import scars
     fsi = next((x for x in dets if x.get("fsi_beat")), None)
     from .hint import safe
-    return row | {"detections": dets, "reports": reps, "reviews": revs, "burn_scar": safe(scars.for_points, dets, with_geometry=True),
+    return row | {"detections": dets, "reports": reps, "reviews": revs,
+                  "burn_scar": safe(scars.for_points, dets, with_geometry=True) if me["role"] != "guard" else None,   # as the list
                   "fsi_compartments": sorted({x["fsi_compartment"] for x in dets if x.get("fsi_compartment")}),
                   "fsi_beat": fsi and fsi["fsi_beat"]}
 
```
</details>

### L5 (low): size_score storage layout

**Where:** `app/big_watch_list.py:17-18`. A rowid table plus a separate `sqlite_autoindex_size_score_1` stores every row twice.
**Measured** (`t/t_bigpost.py`, 4 nights of 430,000 squares through the API): each post took 1.1-1.7 s (7.9 MB body, +12-67 MB RSS). Pruning kept exactly 3 nights (`2026-04-20/21/22`, 430,000 each). `size_at` uses the PK index (`SEARCH size_score USING INDEX sqlite_autoindex_size_score_1 (issue_date=? AND cell=?)`), 200 calls in 0.26 s. Storage was 40.4 MB table + 34.1 MB index. A standalone `WITHOUT ROWID` test gave 40 MB instead of 73 MB, with the same insert time (6.1 s for 3 nights) and the same lookup speed. Freed pages are reused, so the file stops growing after night 4.
**Patch:** `WITHOUT ROWID`, plus a one-time rebuild in `db.init()`. **Patched** (`t/t_bigpost.py` on the migrated copy): the same 4 posts take 0.8-1.1 s each, and the database file is 171 MB instead of 215 MB.

<details><summary>Proposed patch</summary>

```diff
--- a/app/big_watch_list.py
+++ b/app/big_watch_list.py
@@ -15,7 +15,7 @@
 CREATE TABLE IF NOT EXISTS big_watch_meta (issue_date TEXT PRIMARY KEY, model_version TEXT, summary TEXT NOT NULL,
   received_utc TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS size_score (issue_date TEXT NOT NULL, cell INTEGER NOT NULL, score REAL NOT NULL,
-  PRIMARY KEY (issue_date, cell));
+  PRIMARY KEY (issue_date, cell)) WITHOUT ROWID;
 """
 KEEP_SIZE_DAYS = 3
 # officials' new-fire order (Akkshay's card, 20 Oct): logistic on big-fire points + logit(size score of the first-look squares
--- a/app/db.py
+++ b/app/db.py
@@ -214,6 +214,12 @@
             con.execute("DROP TABLE daily_list_v1")
         con.executescript(DL)
         from .big_watch_list import SCHEMA as BW
+        sz = con.execute("SELECT sql FROM sqlite_master WHERE name='size_score'").fetchone()
+        if sz and "WITHOUT ROWID" not in sz[0]:          # 3 nights of scores, sent again every night: rebuild in the new layout
+            con.execute("ALTER TABLE size_score RENAME TO size_score_old")
+            con.executescript(BW)
+            con.execute("INSERT INTO size_score SELECT * FROM size_score_old")
+            con.execute("DROP TABLE size_score_old")
         con.executescript(BW)
         for m in MIGRATIONS:
             try:
```
</details>

### L6 (low): the watch-list note carries a rate

**Where:** `app/big_watch_list.py:65`: `"about 1 in 100 of these squares gets one"`. The rank-only rule (18 Oct) says no % for officials' big-fire info, and "1 in 100" is a 1% rate. This is a wording decision for the owner, so there is no diff. One option: "a short list to check first; most of these squares get no big fire". (`control.html:132` and the brief note carry similar replay rates: "1 in 4-5 passed 200 ha".)
Everything else held. `t/t_leak.py` stored size scores for two nights, scored 498 new fires (392 with a combined order), then searched every officials' response (`/api/v1/alerts`, `/{id}`, `/api/v1/brief`, `/api/v1/big_watch`, `/api/incidents`, `/{id}`, `/api/brief`) for keys `chance`, `order`, `size_score`, `size`, `_order` outside `still_burning`: **none found**. The `/brief` HTML has a `%` only in the still-burning lines (not big-fire info) and in the CSS.

### L7 (low, read only): the in-memory big-fire cache is never trimmed

**Where:** `app/big_fire.py:118` `_cache`: every alert's score that is read or computed stays in memory until restart (about 13k a season, plus whatever the 5000-alert API pages touch). `_CROP` is cleared at 50k. A restart loses nothing, because scores are in `big_fire_score`. Suggested: keep only the last 3 days, or use `functools.lru_cache`-style eviction. No repro; it grows at most by one dict per alert.

### L8 (low, read only): scar outlines are rebuilt inside a request

**Where:** `app/scars.py:83-111`. When the scar files' mtimes change (the nightly scar run), the next request that needs outlines (`/api/incidents` with 400 alerts or fewer, a card, `/scar-check`) rebuilds `scar_outlines.sqlite` inside that request, about 20 s on the network mount at startup per the code comment. Two requests can also both pass the `locked()` check and rebuild one after the other. Not reproduced: it needs the real scar files to change. Suggested: rebuild from `scar_live.run()` after a successful run, and have readers only read.

### L9 (low): brief wording under the combined order

**Where:** `app/brief.py:185` "And N more new fires with fewer points": under the combined order, fires below the top 8 can have more points. The heading at `:198` also states the size score is used even on nights when none arrived (see M5). **Patch:** wording only, at `:185`.

<details><summary>Proposed patch</summary>

```diff
--- a/app/brief.py
+++ b/app/brief.py
@@ -190,7 +190,7 @@
          f'<div class="kpi"><b>{c["burning"]}</b><span>older fires still seen burning</span></div>'
          f'<div class="kpi"><b>{c["not_visited"]}</b><span>alerts not visited, past due</span></div>{norm}</div>')
     new = "".join(_fire_line(f) for f in b["new"][:top]) or '<p class="h">No new fires.</p>'
-    more = f'<p class="h">And {len(b["new"]) - top} more new fires with fewer points: see the alert list.</p>' if len(b["new"]) > top else ""
+    more = f'<p class="h">And {len(b["new"]) - top} more new fires lower in this order: see the alert list.</p>' if len(b["new"]) > top else ""
     shown = {f["id"] for f in b["new"][:top]}
     dk = [f for f in b["dark"] if f["id"] not in shown][:few]
     shown |= {f["id"] for f in dk}
```
</details>

---

## Checked and sound

- **Rank-only:** no hidden value (chance, order, size score) appears in any API response or page; see L6.
- **Guards and big-fire info:** guards get only `big_fire_flag`/`big_fire_text` from the built-in app (`/api/incidents`, card). The v1 leak is H4.
- **size_score:** insert speed, 3-night pruning and index use are fine; see L5. The 418k-row `daily_scores` body (17.5 MB) takes 3.5-6.3 s and about +130 MB RSS, well inside the runner's 600 s timeout. A resend is idempotent. Parsing the JSON blocks the event loop for well under a second.
- **Daily-list season state:** `counts()` keeps each division's own history from 15 Feb (`daily_list.py:83-92`). The first week is counted per division in days that had a list, so early, mid and late divisions (20 Feb / 1 Mar / 20 Mar) each get their own base-share week. A missing day only lengthens the first week. Lists dated before 15 Feb count for nothing. A division with no squares that day gets no count, and a pipeline count for a division with no rows goes to the statewide pool. The old runner's `started()` let every division issue from 1 Oct to 31 Dec; the version rewritten today has `t.month < 10 and START <= md <= END`, which fixes that.
- **Night mapping:** first look at 23:59 IST uses the run of D-1 and at 00:01 IST the run of D; the 13:30 IST pass uses the run of D-1 and the 01:30 IST pass the run of D (`t/t_order.py (c)`). All new fires in a 16:00 brief use one night.
- **Midnight handling:** still-burning works in hours since the last VIIRS dot, with no date boundary. `scars.for_points` tries the UTC date and the next day for FSI IST dates. The scar-check week runs on IST days. The control-burn fire day uses IST with a 06:00 cut-off, and an all-daytime rule makes the day boundary irrelevant.
- **Brief cost when scores are stored:** 0.04-0.10 s for a 210-fire division, 1.4 s for all 77 divisions (`t/t_brief_cost.py`).
- **Project tests:** `daily_list_test.py` and `cause_check_test.py` pass.

## Files

- Tests and harness: `/tmp/claude-0/audit_officials/t/` (`h.py` harness; one script per finding, as named above).
- Patches: `/tmp/claude-0/audit_officials/patch/patches.py` (source), `patch/make.py` (applies them in order to a copy at `patch/b/` and writes `patch/diffs/*.diff`). All 19 compile (`py_compile`), and every repro above was run again against `patch/b/`.
- These live in /tmp, which is scratch: the diffs above are the copy to keep.

## Fixes applied (20 Oct 2026)

Each fix was ported by hand; no file from `patch/b/` was copied over. The auditor's repros were repointed to `/tmp/claude-0/fieldfix/o/` and run against the shipped code (`/tmp/claude-0/fieldfix/run_officials.sh`, output in `/tmp/claude-0/fieldfix/officials2.out`). `scripts/daily_list_test.py 2026-04-22` (ALL PASS) and `scripts/cause_check_test.py` (passed) were run on fresh databases. `scripts/run_tests.py` (flow, api_v1, pilot, webhook) passes 4 of 4, each on its own fresh database.

| Finding | Status | How checked |
|---|---|---|
| C1 big-fire error takes down guard list and eNetra API | fixed: every hint goes through `hint.safe` (logged, null on error) | t_isolation, t_sizeat_guard: every route 200 with big_fire.check and size_at raising |
| H1 no hint isolated | fixed: direction, runway, still-burning, control-burn, scars, spread24, big-fire and the brief's check list are each isolated | t_isolation, t_partial: 200 everywhere, report still stored |
| H3 unauthenticated bodies read before the key check | fixed: middleware gives 401 for `/api/v1/` without the right key before the body is read, and 413 over `FS_MAX_BODY_MB` | t_unauth_body: 119 MB body, 401 in 0.0 s, no RSS growth |
| H4 guard-facing v1 calls return officials-only fields | fixed: `view=guard`; the answers to a guard's report and chance find use it; the webhook keeps the officials' view | t_guard: officials-only keys [] in the report answer |
| H5 scoring holds the write lock across WorldCover reads | fixed: commit after each alert's score, so no lock is held during the next read | t_lock, both orders: concurrent write OK after 0.0 s |
| M1 `executescript()` commits the caller's transaction | fixed: removed from `store`, `division_view`, `size_at` and `v1_big_watch`; `size_score` rebuilt once in `db.init` | t_bigpost, t_lock |
| M2 runway: one bad fire blocks all, errors never retried | fixed (auditor's diff applied) | t_runway: 5 of 5 stored, transient error retried |
| M3 scoring failure skips the daily scar run | fixed: three separate steps in `poller` | t_poller: scar_live called |
| M4 16:00 brief has no list and says nothing | fixed: `_check_list` shows the newest list from yesterday or today, says when none has arrived and why, and shows the runner's stale inputs | t_brief_past: `check_list = {'missing': ..., 'why': ...}`, page mentions the list |
| M5 no size score sinks for good | fixed: missing size uses the points-only value (same logistic, logit(size) replaced by that night's mean, `size_mean_logit` saved with the night); recomputed and stored once that night's run arrives; nothing missing is stored for good | t_order (a) and (b) |
| M6 control room and brief show two orders | fixed: control room sorts by `order_rank` from `big_fire.order_key` | t_order2: largest inversion 0 |
| M7 one WorldCover failure stored for good | fixed: the score is not stored while farmland was unchecked within 6 h of the first look | t_misc (a): nothing stored, rescored later |
| M8 `daily_scores` input checks | fixed: date, equal lengths, finite numbers, grid range, empty usable set refused, duplicates once | t_daily418: 400 with a plain message for each bad body |
| L1 past-clock brief shows later visits | fixed: visited only when `first_report_utc <= clock` | t_brief_past: visited False |
| L2 2-hour CDSE recheck unused | fixed (auditor's diff applied) | t_runway (c): True |
| L3 ranger of an unknown range gets the statewide brief | fixed: 403 | t_misc (b): 0 divisions |
| L4 guards' card carries the burn scar | fixed for `burn_scar` (left out of the guard card and list). Not fixed: `arm`, `score`, `model_hash` (owner decision) | t_guard |
| L5 size_score storage layout | fixed: WITHOUT ROWID | t_bigpost |
| L6 watch-list note carries a rate | not fixed (wording is the owner's call) | - |
| L7 big-fire cache never trimmed | not fixed (read only, kept as a note) | - |
| L8 scar outlines rebuilt in a request | not fixed (read only, kept as a note) | - |
| L9 brief wording under the combined order | fixed: the heading says "points + size score" only when a new fire has one | t_leak, brief HTML |

Needs an owner decision (not done):
- L4: may `arm`, `score` and `model_hash` (patrol pilot fields) reach guards?
- L6: the "about 1 in 100" wording on the watch list.
- The brief is made at 16:00 IST and the runner posts the 2-day list at about 17:15 IST. Move the brief clock, or keep it and rely on the new "not received yet" line?
- API shape change: in the v1 brief, `check_list` is now an object with `missing` and `why` when there is no list, where it used to be null.
