# Audit: live ingest and alert creation

Scope: from the satellite poll to the stored incident and task. Files: `app/firms.py`, `app/bhuvan.py`, `app/fsi_portal.py`, `app/geo.py`, `app/landcover.py`, `app/db.py`, `app/config.py`, the poll and background threads in `app/server.py` (`startup` 45-58, `poller` 78-91, `/api/ingest` 841-843), `app/webhook.py` (it is called from ingest), and `scripts/bhuvan_test.py`, `scripts/source_order_test.py`, `scripts/import_archive.py`, `scripts/demo_replay.py`.

Audit date: 20 Oct 2026. Nothing under `/mnt/project-files/field-system` was changed apart from this file. All patches below are proposals. Some (P-1, P-2, P-5, P-6) were checked by applying them in memory only (`t05`, `t18`, `t19`).

## How the tests were run

- All databases and scratch files are in `/tmp/claude-0/audit_ingest/runs/<test>/`. The test scripts are in `/tmp/claude-0/audit_ingest/`. Each test's output is saved next to it as `tNN.out`.
- `common.py` points `FS_DATA_DIR` at a fresh folder. It also provides a local fake HTTP server (FIRMS, Bhuvan, FSI, WorldCover, webhook) that can return good files, HTML, empty files, truncated files, slow trickles, hangs and 5xx errors.
- The existing tests pass on a throwaway database: `bhuvan_test.py` (8/8) and `source_order_test.py` (4/4). Both also pass with the proposed grouping and Bhuvan patches applied (`t19`). `api_v1_test.py` passed against a server on :8011 using a `demo_replay.py 2026-04-15` database (FS_DEMO_NOW set, so no live polling).
- Live network use (a few requests in total): one FIRMS MODIS 24 h file, which has the expected columns and satellite codes `A`/`T`; one Bhuvan panel page, where the `PASS` regex still matches today's markup; one FSI portal request, which failed TLS verification from this sandbox (see L-12).
- Run any test with `cd /tmp/claude-0/audit_ingest && python3 tNN_*.py`. The run time is noted where a test is slow.

## Summary

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 6 |
| Medium | 9 |
| Low | 12 |

Already working (tested):
- One feed returning an HTTP error does not stop the other feeds (`t01` F).
- `kill -9` in the middle of `store()` leaves nothing half-written, because each feed is one transaction, and `integrity_check` is ok (`t15`).
- Exact repeat polls are de-duplicated.
- WAL mode is on.
- Over a 138k-point synthetic season, RSS stays flat at about 320 MB, almost all of it the beat layer (`t12`).
- With `PRAGMA optimize` after each poll, the per-point cost stays flat (but see L-5).

---

## CRITICAL

### C-1. The poll holds the SQLite write lock while it reads WorldCover over HTTP. Field reports and phone positions fail with HTTP 500 while it does.

`app/firms.py:90-137` (`store`): `with db.tx()` opens the transaction. The first `INSERT` takes the write lock. After that, every following in-beat point calls `forest_share()` (line 124), which goes to `landcover.py` (`_HTTPFile`, HEAD and range GETs with `timeout=60`, lines 21 and 35). The lock is held for the whole file. Every other writer (`db.connect(timeout=30)`, `db.py:223`), which includes guard reports, `/api/v1/positions`, reviews and the hint threads, waits 30 s and then gets `sqlite3.OperationalError: database is locked`.

Measured against the real S3 tiles from here: 0.25-1.7 s for each point that needs a new 1 MB block. A pass that brings 60-100 new in-beat points therefore holds the lock for 30-100 s. That happens on ordinary peak-season afternoons. The first poll after a restart pulls a 7-day window and holds it for many minutes. If S3 is slow or down, every point retries the HEAD (no negative cache, see M-5), up to 60 s each, so the lock can be held for hours.

Reproduced:
- `t06_locking.py` A (2 min): 90 points at 0.5 s of WorldCover each. `store took 45 s; concurrent API write: database is locked after 30.1 s`.
- `t16_api_write_vs_lock.py` (end to end, against the server on :8011): `POST /api/v1/positions` while another connection holds the write lock gives `500 after 30.1 s`, and the server log shows `sqlite3.OperationalError: database is locked`.
- `t08_worldcover_down.py` B: a 4 s WorldCover stall made 3 points take 12 s inside the transaction, with no back-off.

Proposed patch: read WorldCover before the write transaction, and back off when it fails. The behaviour is otherwise unchanged.

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -15,15 +15,24 @@
 _WC = None
+_WC_DOWN_UNTIL = 0.0       # back-off after a WorldCover failure (no 60 s retry per point)
+SEEN_SQL = "SELECT 1 FROM detections WHERE instrument=? AND satellite=? AND lat=? AND lon=? AND acq_utc=?"
 
 
 def forest_share(d):
     """Tree + shrub share in the pixel footprint, or None if WorldCover can't be read (then keep the point)."""
-    global _WC
+    global _WC, _WC_DOWN_UNTIL
+    import time
+    if time.monotonic() < _WC_DOWN_UNTIL:
+        return None
     try:
         _WC = _WC or WorldCover()
         s = _WC.share(d["lat"], d["lon"], FOOTPRINT_KM[d["instrument"]])
         return None if s is None else round(s[1], 3)
     except Exception:
         log.exception("worldcover read failed")
+        _WC_DOWN_UNTIL = time.monotonic() + 600
         return None
@@ -86,10 +95,21 @@ def store(rows, beats, source_label):
     fetched = len(rows)
     rows = sorted((d for d in rows if in_bbox(d)), key=lambda d: d["acq_utc"])
     new_rows = new_inc = 0
     touched = set()
+    # WorldCover is read over HTTP (0.3-2 s a point). Read it before the write transaction: inside it every
+    # API write (reports, positions, reviews) waits on the lock and fails after 30 s.
+    shares = {}
+    if config.FOREST_FILTER:
+        with db.tx() as ro:
+            for d in rows:
+                k = (d["instrument"], d["lat"], d["lon"])
+                if (d["source"] != "FSI_PORTAL" and k not in shares
+                        and beats.touching(d["lat"], d["lon"], FOOTPRINT_KM[d["instrument"]])
+                        and not ro.execute(SEEN_SQL, (d["instrument"], d["satellite"], d["lat"], d["lon"], d["acq_utc"])).fetchone()):
+                    shares[k] = forest_share(d)
     with db.tx() as con:
         for d in rows:
-            if con.execute("SELECT 1 FROM detections WHERE instrument=? AND satellite=? AND lat=? AND lon=? AND acq_utc=?",
-                           (d["instrument"], d["satellite"], d["lat"], d["lon"], d["acq_utc"])).fetchone():
+            if con.execute(SEEN_SQL, (d["instrument"], d["satellite"], d["lat"], d["lon"], d["acq_utc"])).fetchone():
                 continue   # seen in an earlier poll
@@ -121,8 +141,8 @@ def store(rows, beats, source_label):
             if official:   # FSI's own alert: FSI has already masked it to forest
                 d["mask_kind"] = None
-            d["forest_share"] = (forest_share(d) if d["beat_uid"] and not d["mask_kind"] and config.FOREST_FILTER
-                                 and not official else None)
+            d["forest_share"] = (shares.get((d["instrument"], d["lat"], d["lon"])) if d["beat_uid"] and not d["mask_kind"]
+                                 and config.FOREST_FILTER and not official else None)
```

Follow-ups:
- `persistent_heat` and `fsi_portal.match` are fast once statistics exist (`t12`), so they can stay inside the transaction.
- `scripts/import_archive.py` sends a whole archive through one `store()` call. Committing every ~500 rows would keep a running server responsive during an import.

---

## HIGH

### H-1. Alerts are grouped in arrival order, not time order. A point older than an open alert's first look can never join it, which gives about 22% extra alerts (duplicate tasks for one fire).

`app/firms.py:201-205`: candidates must have `i.first_seen_utc <= d.acq_utc`. Points arrive out of time order in normal running:
- Bhuvan's time is the granule time, 2-12 min after the scan.
- NOAA-21 (FIRMS only) often scanned before the S-NPP or NOAA-20 look that Bhuvan already turned into an alert.
- Each poll stores the feeds one at a time (SNPP, N20, N21, MODIS), each sorted separately. This matters for the 7-day pull at start-up and after any backlog.

The earlier point then opens a second alert for the same fire.

Reproduced:
- `t04_grouping_order.py`:
  - A. Terra MODIS at 05:10 stored after S-NPP at 08:00, 0.45 km apart: 2 alerts.
  - B. A neighbouring NOAA-20 pixel of the pass Bhuvan sent: 2 alerts.
  - C. NOAA-21 look 25 min before the Bhuvan S-NPP look, 0.4 km away: 2 alerts.
- `t05_order_quantify.py` (1 min) on the real Ratapani FIRMS 2026 points (4,164):

| Run | Alerts |
|---|---|
| Time-sorted per day | 524 |
| Feed by feed per day (start-up or backlog) | 641 (+22%) |
| Simulated 15-min polls with FIRMS latency, FIRMS only | 566 |
| Same, Bhuvan on | 689 (+22%; detections identical at 4,164, so every Bhuvan copy merged and the extra alerts are pure duplicates) |
| Same, Bhuvan on, patch below | 582 |

The README's "Grouping is order-dependent at the edges" covers only the spatial case. This time-order case is larger and was added by Bhuvan on 19-20 Oct.

Proposed patch (checked in `t05` and `t19`; the existing tests still pass):

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -201,15 +201,18 @@ def attach_to_incident(con, det_id, d):
     cands = con.execute(
         """SELECT DISTINCT i.id, x.lat, x.lon FROM incidents i JOIN detections x ON x.incident_id = i.id
            WHERE ((i.status IN ('new','revisit') AND i.last_seen_utc >= ?) OR (i.large = 1 AND i.last_seen_utc >= ?))
              AND i.first_seen_utc <= ? AND x.lat BETWEEN ? AND ? AND x.lon BETWEEN ? AND ?""",
-        (lo, lo_large, d["acq_utc"], d["lat"] - dl, d["lat"] + dl, d["lon"] - 1.2 * dl, d["lon"] + 1.2 * dl)).fetchall()
+        # a point may arrive after a later look of the same fire (Bhuvan granule time, NOAA-21 via NASA, feed order)
+        (lo, lo_large, iso(t + timedelta(hours=config.CLUSTER_HOURS)),
+         d["lat"] - dl, d["lat"] + dl, d["lon"] - 1.2 * dl, d["lon"] + 1.2 * dl)).fetchall()
@@ -212,8 +215,11 @@ def attach_to_incident(con, det_id, d):
         inc = best[0]
         con.execute("""UPDATE incidents SET n_detections = n_detections + 1,
+                       due_utc = CASE WHEN ? < first_seen_utc THEN min(due_utc, ?) ELSE due_utc END,
+                       first_seen_utc = min(first_seen_utc, ?),
                        last_seen_utc = max(last_seen_utc, ?), max_frp = max(coalesce(max_frp,0), ?),
                        sensors = CASE WHEN instr(sensors, ?) THEN sensors ELSE sensors || ',' || ? END
-                       WHERE id = ?""", (d["acq_utc"], d["frp"], d["source"], d["source"], inc))
+                       WHERE id = ?""", (d["acq_utc"], iso(due_for(t)), d["acq_utc"], d["acq_utc"], d["frp"],
+                                         d["source"], d["source"], inc))
```

Also, in `run_live`, fetch all four FIRMS feeds first and call `store()` once on the merged, time-sorted list.

### H-2. A restart re-reads Bhuvan's passes and re-adds every pixel FIRMS already filled in. Fires already visited get a second open task.

`app/bhuvan.py:24,76,84` and `app/firms.py:114`:
- `_done` (the passes already read) lives only in memory.
- When FIRMS merges into a Bhuvan row, the row's lat, lon, time and satellite become FIRMS'. A re-read Bhuvan point therefore no longer matches it exactly.
- `match()` finds the merged row, but the guard at line 114 only skips when the matched source is *not* `BHUVAN`.

So after any restart (or a crash and restart), every Bhuvan pass still on the panel (the whole IST day) is stored again:
- If the original alert was visited, the copy opens a new task.
- Otherwise it inflates `n_detections`.

Reproduced: `t03_bhuvan.py` C: `after restart: detections 2 incidents 2 [(1,'visited',...),(2,'new',...)]`. The duplicate task stays open after the next FIRMS poll. With the patch: `t18` check 1 PASS, and `bhuvan_test.py` still passes (`t19`).

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -113,4 +113,4 @@ def store(rows, beats, source_label):
                     continue
-                if src and d["source"] == "BHUVAN" and src != "BHUVAN":
-                    continue   # Bhuvan point for a pixel FIRMS or FSI already sent
+                if src and d["source"] == "BHUVAN":
+                    continue   # Bhuvan point for a pixel already stored (FIRMS, FSI, or an earlier read of this pass)
```

### H-3. No health signal. Ingest can stop silently in at least five ways, and the control room banner says the feeds were checked.

There is no `/health` route (`t13` C: none of the 61 routes). The only signal is `GET /api/stats -> ingest` (the last 8 `ingest_log` rows, `server.py:594`). `control.html:72-73` turns that into "NASA FIRMS and FSI feeds checked N ago" using the newest row of *any* source without an error. Ways ingest stops while looking fine:

1. **Hung poll thread.** `t13` A: the thread is alive but blocked in `urlopen` for 25 s+, writes no `ingest_log` rows and logs nothing, and the banner still shows the 3-hour-old success with no warning. See H-4 for why the timeout does not end it.
2. **Every NASA feed failing while FSI works.** `t13` B: the banner says "NASA FIRMS and FSI feeds checked just now".
3. **Bhuvan page markup changes.** `t03` A: `passes()` returns `[]`, so `run()` returns `(0,0,0)` with no `ingest_log` row and no error. This is a regex scraper of a web page, so a site change is a silent stop.
4. **Empty file, header-only file, or one-line HTML error page from NASA with HTTP 200.** `t01` C1 and D: these are logged as `fetched=0, error NULL`, which looks the same as "no fires". A South Asia 24 h file is never empty in practice (the 20 Oct MODIS 24 h file had 211 rows).
5. **A failed Bhuvan pass** is logged only to the Python log, not to `ingest_log` (`t02` B).

Proposed patch: per-source freshness, a poll heartbeat, and "empty" treated as an error.

```diff
--- a/app/server.py
+++ b/app/server.py
@@ -78,14 +78,19 @@
+POLL = {"started": None, "finished": None}
+
+
 def poller():
     first = True
     while True:
+        POLL["started"] = time.time()
         try:
             firms.run_live(BEATS, "7d" if first else "24h")
             ...
         except Exception:
             log.exception("poll failed")
+        POLL["finished"] = time.time()
         time.sleep(config.POLL_MINUTES * 60)
@@
+@app.get("/api/health")
+def health():
+    """For eNetra / an uptime monitor: per source, the last good non-empty read. 503 when anything is stale."""
+    lim = {"BHUVAN": 6 * 3600, "FSI_PORTAL": 6 * 3600}
+    with db.tx() as con:
+        rows = con.execute("""SELECT CASE WHEN source LIKE 'BHUVAN%' THEN 'BHUVAN' WHEN source LIKE 'FSI_PORTAL%' THEN 'FSI_PORTAL'
+                                          ELSE replace(replace(source, '_24h', ''), '_7d', '') END AS src,
+                                     max(CASE WHEN error IS NULL AND coalesce(fetched, 0) > 0 THEN utc END) AS last_ok
+                              FROM ingest_log WHERE utc >= ? GROUP BY src""",
+                           (firms.iso(now() - timedelta(days=3)),)).fetchall()
+    t = time.time()
+    out = {r["src"]: {"last_ok_utc": r["last_ok"], "stale": not r["last_ok"] or
+                      t - firms.parse_utc(r["last_ok"]).timestamp() > lim.get(r["src"], 3 * 3600)} for r in rows}
+    running = POLL["started"] and (not POLL["finished"] or POLL["finished"] < POLL["started"])
+    body = {"sources": out, "poll_running_s": round(t - POLL["started"]) if running else 0}
+    stuck = running and t - POLL["started"] > 30 * 60
+    return Response(json.dumps(body), status_code=503 if stuck or any(v["stale"] for v in out.values()) else 200,
+                    media_type="application/json")
--- a/app/bhuvan.py
+++ b/app/bhuvan.py
@@ -74,4 +74,7 @@ def run(beats):
     read = new_rows = new_inc = 0
-    for p in passes():
+    ps = passes()
+    if not ps:
+        raise RuntimeError("Bhuvan panel lists no 375 m passes (page layout changed?)")   # logged in ingest_log
+    for p in ps:
```

Raise on an empty or HTML FIRMS file as in H-5. In `control.html`, show the age per source and turn it red past 3 h. That file belongs to the dashboard area; this is only a note.

### H-4. Timeouts are per socket read, not deadlines, and the sources run one after another. One slow source delays all the others, possibly forever.

- `app/firms.py:72` `urlopen(timeout=120)`, `app/fsi_portal.py:33` the same, and `app/bhuvan.py:31` `requests.get(timeout=60)` are all per-read timeouts. A server that trickles bytes never trips them.
- `bhuvan._get` adds 5 tries with 2+4+6+8 s back-off, so one hung pass download costs about 320 s.
- `run_live` (`firms.py:258-289`) runs Bhuvan, then FSI, then the four FIRMS feeds in series, inside the single poll thread.

Reproduced:
- `t02_slow_sources.py` A (2.5 min): a fetch with `timeout=120` ran 150 s against a trickling server and only ended because the fake stopped. A slower trickle never ends.
- `t02` B (5.5 min): one hung Bhuvan pass held every FIRMS feed back by 320 s. A panel lists about 9 passes a day, so N hung passes cost N × 320 s per poll, and that repeats every poll because a failed pass is retried.

Proposed patch: a total deadline per download, and a time budget for Bhuvan. Running Bhuvan, FSI and FIRMS on separate threads would be better still.

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -66,9 +66,22 @@
+def http_get(req, timeout=30, deadline=180):
+    """GET with a total deadline: urlopen's timeout is per socket read, so a trickling server never trips it."""
+    import time
+    end = time.monotonic() + deadline
+    with urllib.request.urlopen(req, timeout=timeout) as r:
+        buf = []
+        while chunk := r.read1(1 << 16):
+            buf.append(chunk)
+            if time.monotonic() > end:
+                raise TimeoutError(f"download over {deadline} s")
+    return b"".join(buf)
+
+
 def fetch_feed(source, window="24h"):
     instrument, path = FEEDS[source]
     url = f"{BASE}/{path.format(r=config.FIRMS_REGION, w=window)}"
-    with urllib.request.urlopen(url, timeout=120) as r:
-        text = r.read().decode("utf-8")
+    text = http_get(url).decode("utf-8")
--- a/app/bhuvan.py
+++ b/app/bhuvan.py
@@ -27,5 +27,5 @@
-def _get(url, params=None, tries=5):
+def _get(url, params=None, tries=3):
     import requests
     for i in range(tries):
         try:
-            r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
+            r = requests.get(url, params=params, timeout=(10, 30), headers={"User-Agent": "Mozilla/5.0"})
@@ -74,5 +74,9 @@ def run(beats):
     read = new_rows = new_inc = 0
+    t_end = time.monotonic() + 240   # never hold back FSI / NASA for more than 4 min
     for p in passes():
         if p in _done:
             continue
+        if time.monotonic() > t_end:
+            log.warning("bhuvan: time budget used, remaining passes next poll")
+            break
```

Apply the same `http_get` in `fsi_portal.fetch`. The requests calls in `landcover._HTTPFile` have the same per-read limit; C-1's back-off bounds that cost.

### H-5. One malformed row discards the whole file. A truncated line, a blank FSI time or an unknown FSI sensor drops every point of that feed, on every poll for 24-48 h.

`app/firms.py:74` and `app/fsi_portal.py:35` parse with one list comprehension. Any `ValueError`, `TypeError` or `KeyError` in one row raises for the whole feed. For FSI-only rows, `firms.store` also does `FOOTPRINT_KM[d["instrument"]]` (lines 118 and 124), so a `Source_Type` other than `VIIRS`/`MODIS` raises `KeyError` and rolls back the whole FSI batch.

The bad row stays in the 24 h FIRMS file or the 2-day FSI window, so the feed is lost for as long as the row is listed.

Reproduced:
- `t01_feed_formats.py` A: 20 good rows plus a truncated last line make `fetch_feed` raise `ValueError ... 'None None'`, and all 20 are lost.
- `t07_fsi.py`:
  - B. One FSI row with a blank `Fire_Time`: `Invalid isoformat string`, and the whole FSI download fails.
  - C. One `Source_Type` of `VIIRS_375` rolls back every FSI-only point of the poll.

Proposed patch (checked in `t18`: 20 of 20 good rows kept, the bad one skipped and counted):

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -72,3 +72,16 @@ def fetch_feed(source, window="24h"):
-    return [normalise(row, source, instrument) for row in csv.DictReader(io.StringIO(text))]
+    out, bad = [], 0
+    for row in csv.DictReader(io.StringIO(text)):
+        try:
+            if not row.get("satellite") or not str(row.get("acq_time") or "").isdigit() or None in row.values():
+                raise ValueError("incomplete row")
+            out.append(normalise(row, source, instrument))
+        except (KeyError, ValueError, TypeError):
+            bad += 1
+    if bad:
+        log.warning("%s: skipped %d malformed rows", source, bad)
+    if not out and bad == 0 and "latitude" not in text[:200]:
+        raise ValueError("not a FIRMS CSV (HTML or empty file?)")
+    return out
--- a/app/fsi_portal.py
+++ b/app/fsi_portal.py
@@ -33,3 +33,13 @@ def fetch(days=2):
-        text = r.read().decode("utf-8")
-    return [normalise(row) for row in csv.DictReader(io.StringIO(text))]
+        text = r.read().decode("utf-8-sig")          # also tolerates a BOM (L-9)
+    out = []
+    for row in csv.DictReader(io.StringIO(text)):
+        try:
+            d = normalise(row)
+        except (KeyError, ValueError, TypeError):
+            continue
+        if d["instrument"] in ("VIIRS", "MODIS"):    # unknown sensors would raise KeyError in firms.store
+            out.append(d)
+    return out
```

### H-6. When the database is locked, the exception escapes `run_live` through its own error handler, and the rest of the poll is skipped.

`app/firms.py:266-268`, `276-278` and `285-287`: each `except` block writes the error to `ingest_log` through `db.tx()`. When the failure was "database is locked" (C-1, an import, or `/api/ingest` running alongside the poll), that write also waits 30 s and raises. The new exception leaves `run_live`, so the remaining sources are not fetched in that poll. `poller` catches it as "poll failed"; `/api/ingest` returns a 500.

Reproduced: `t06_locking.py` B: `run_live after 70 s: escaped=OperationalError('database is locked'), feeds fetched=['SUOMI_VIIRS_C2_South_Asia_24h.csv']`, so 3 of 4 feeds were skipped. With the patch (`t18` check 3), all 4 feeds are tried and `run_live` returns.

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -257,2 +257,11 @@
+def _log_error(source, e):
+    try:
+        with db.tx() as con:
+            con.execute("INSERT INTO ingest_log(utc,source,error) VALUES (?,?,?)",
+                        (iso(datetime.now(timezone.utc)), source, str(e)[:500]))
+    except Exception:
+        log.exception("could not log %s error", source)
+
+
 def run_live(beats, window="24h"):
@@ (same change in the three except blocks)
-            with db.tx() as con:
-                con.execute("INSERT INTO ingest_log(utc,source,error) VALUES (?,?,?)",
-                            (iso(datetime.now(timezone.utc)), source, str(e)[:500]))
+            _log_error(source, e)
```

Also serialise `/api/ingest` with the poller using a module-level `threading.Lock` in `run_live`, so the two never fight over the lock (L-10).

---

## MEDIUM

### M-1. A FIRMS line cut inside `acq_time` is accepted with a wrong time and `satellite=NULL`, and is stored again on every poll.

`app/firms.py:49-61`: `str("07").zfill(4)` gives `00:07`. Missing columns become `None` (`satellite=None`, `confidence="None"`, which passes the "not low" test). `UNIQUE(instrument, satellite, ...)` never matches a NULL, so the dedupe `SELECT ... satellite=?` misses it and every re-poll inserts another copy.

Reproduced: `t01` B: parsed `{'acq_utc': '2026-04-22T00:07:00Z', 'satellite': None, 'confidence': 'None'}`, and after 3 polls there were `3 copies`.

Fix: the row check in the H-5 patch (requires a satellite, a numeric `acq_time` and no missing columns).

### M-2. FSI-only alerts skip the industry mask and persistent heat. The README says "Mines and persistent heat stay out".

`app/firms.py:122-123`: `if official: d["mask_kind"] = None`. FSI-only points therefore open tasks at mines, factories and kilns. README (FSI section): "FSI alerts our WorldCover filter dropped still become tasks... Mines and persistent heat stay out." That sentence holds only for FIRMS points that FSI tagged (the promotion in `fsi_portal.run` checks `mask_kind IS NULL`).

Reproduced: `t07` A: an FSI-only point at a real `industry_mask.geojson` site (23.0945, 77.52732, beat 009-005-005) gave `(mask_kind None, incident 1)`.

The patch below makes the code follow the README. The owner should confirm which rule is intended, since FSI's own SMS may already go out for these points.

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -121,4 +121,2 @@ def store(rows, beats, source_label):
             d["mask_kind"] = (_MASK.hit(d["lat"], d["lon"]) or persistent_heat(con, d)) if d["beat_uid"] else None
-            if official:   # FSI's own alert: FSI has already masked it to forest
-                d["mask_kind"] = None
             d["forest_share"] = (forest_share(d) if d["beat_uid"] and not d["mask_kind"] and config.FOREST_FILTER
```

### M-3. `scripts/import_archive.py` turns history into open, overdue field tasks. With a webhook set it crashes, and one blank time fails the whole import.

The README tells the operator to "load a year of archive points" for persistent heat, but `store()` always opens tasks.

Reproduced: `t09_import_archive.py`:
- A. 11 archive points give 11 `new` tasks, all already overdue (`min(due_utc)=2025-01-15T14:00:00Z`). They count in `/api/stats` overdue for the period. `/api/v1/alerts?status=new` returns them to eNetra. They are also grouping candidates for live points.
- B. With `FS_WEBHOOK_URL` set, the script dies after its commit: `AttributeError: 'NoneType' object has no attribute 'by_uid'`. `alert_json` uses `server.BEATS`, which is `None` outside the server.
- C. One row with a blank `acq_time` (as in the `*NRT-EE` rows of `fire-alert-scars/alerts/*.csv`) makes pandas read the column as float. Every row becomes `"800.0"`, and the import fails with `unconverted data remains: .0`.

```diff
--- a/app/firms.py
+++ b/app/firms.py
@@ -48,3 +48,3 @@ def normalise(row, source, instrument):
-    t = str(row["acq_time"]).zfill(4)
+    t = str(int(float(row["acq_time"]))).zfill(4)        # pandas reads 800 as 800.0 when a column has a blank
@@ -81,3 +81,3 @@
-def store(rows, beats, source_label):
+def store(rows, beats, source_label, tasks=True):
@@ -134,3 +134,3 @@ def store(rows, beats, source_label):
-            if d["beat_uid"] and d["confidence"] != "low" and in_forest and not d["mask_kind"]:
+            if tasks and d["beat_uid"] and d["confidence"] != "low" and in_forest and not d["mask_kind"]:
@@ -140,1 +140,1 @@ def store(rows, beats, source_label):
-    if touched and config.WEBHOOK_URL:
+    if tasks and touched and config.WEBHOOK_URL:
--- a/scripts/import_archive.py
+++ b/scripts/import_archive.py
@@ -18,2 +18,3 @@
 df["acq_date"] = pd.to_datetime(df["acq_date"]).dt.strftime("%Y-%m-%d")
+df = df[df["acq_time"].notna() & df["satellite"].notna()]   # Earth Engine rows carry no time or satellite
@@ -28,1 +29,2 @@
-print("new detections, new alerts:", firms.store(rows, Beats(), "archive:" + Path(a.path).name))
+# history feeds persistent heat and the near-recent hints; it must not create field tasks
+print("new detections:", firms.store(rows, Beats(), "archive:" + Path(a.path).name, tasks=False)[0])
```

### M-4. Ingest webhooks start one OS thread per event, run the heavy `alert_json` in the poll thread, and drop an event after one failed try.

- `app/webhook.py:17-22` starts a thread per event, with no limit.
- `firms.py:140-145` and `fsi_portal.py:110-119` build `alert_json` (big-fire, control-burn, direction, still-burning, runway, scars) for every touched alert, inside the poll thread.
- A failed POST is logged as a warning and lost, with no outbox and no retry. eNetra then never hears about that alert.

Reproduced: `t14_webhook_flood.py`: 400 points gave 399 alerts. `store()` took 42 s with webhooks against 0.2 s without, so 42 s of the poll went on `alert_json`, and 286 sender threads were still open at the end against a 20 s receiver. With the endpoint down, the event is gone (only a warning line).

Minimal patch: one sender thread fed by a bounded queue, with a few retries. A DB outbox table would also survive restarts.

```diff
--- a/app/webhook.py
+++ b/app/webhook.py
@@ -1,22 +1,40 @@
-import hashlib, hmac, json, logging, threading, urllib.request
+import hashlib, hmac, json, logging, queue, threading, time, urllib.request
 from . import config
 
 log = logging.getLogger("webhook")
+_Q = queue.Queue(maxsize=5000)
+
+
+def _worker():
+    while True:
+        event, body, headers = _Q.get()
+        for i in range(4):
+            try:
+                urllib.request.urlopen(urllib.request.Request(config.WEBHOOK_URL, data=body, headers=headers), timeout=30)
+                break
+            except Exception as e:
+                log.warning("webhook %s failed (try %d): %s", event, i + 1, e)
+                time.sleep(5 * 2 ** i)
+
+
+threading.Thread(target=_worker, daemon=True, name="webhook").start()
 
 
 def send(event, payload):
     if not config.WEBHOOK_URL:
         return
     body = json.dumps({"event": event, "data": payload}, default=str).encode()
     headers = {"Content-Type": "application/json", "X-Event": event}
     if config.WEBHOOK_SECRET:
         headers["X-Signature"] = hmac.new(config.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
-
-    def go():
-        try:
-            urllib.request.urlopen(urllib.request.Request(config.WEBHOOK_URL, data=body, headers=headers), timeout=30)
-        except Exception as e:
-            log.warning("webhook %s failed: %s", event, e)
-    threading.Thread(target=go, daemon=True).start()
+    try:
+        _Q.put_nowait((event, body, headers))
+    except queue.Full:
+        log.error("webhook queue full, %s dropped", event)
```

Also wrap the webhook loops in `firms.store` and `fsi_portal.run` in `try/except`. An `alert_json` error after the commit is currently reported as a feed failure, and the remaining webhooks for that poll are lost (see M-3 B).

### M-5. When WorldCover can't be read, the forest filter fails open, nothing records it, and every point retries.

`app/firms.py:18-27`: an S3 403, a proxy HTML page or a timeout gives `forest_share=None`. That stores exactly what a disabled filter stores, so every in-beat farm fire becomes a task. In October that is about 6× the tasks (README: 128 against 21 for 7-14 Oct). Neither `ingest_log` nor the detection says the filter was off. `landcover._page` caches only successes, so each point repeats the HEAD.

Reproduced: `t08_worldcover_down.py` A: 3 points gave `(None, task)` each, no `ingest_log` error, and 3 HEAD requests (each can take up to 60 s).

Fix: the back-off in C-1, plus a count of failed reads for the poll written to the feed's `ingest_log.error` (for example `"forest filter unavailable for 37 points"`). Optionally, hold the task (`mask_kind='forest_unknown'`) instead of opening it, and let a later poll re-check. That last part is an owner decision.

### M-6. A Bhuvan pass whose sheet is empty on the first read is marked done and never read again.

`app/bhuvan.py:83-84`: `_done.add(p)` runs even when `rows == []`. If the panel lists a pass before its points are filled in, or briefly returns an empty sheet, the early points for that pass are lost. NASA brings them 1-5 h later, which is the delay Bhuvan was added to remove.

Reproduced: `t03` B: the first read returned an empty sheet, the filled sheet was never fetched (`reads=1`), and 0 points were stored.

```diff
--- a/app/bhuvan.py
+++ b/app/bhuvan.py
@@ -83,2 +83,4 @@ def run(beats):
         n, k = firms.store(rows, beats, f"BHUVAN_{p[3]}") if rows else (0, 0)
-        _done.add(p)
+        # an empty sheet may not be filled in yet: keep re-reading it for 3 h after the pass
+        if rows or datetime.now(timezone.utc) - pass_utc(p[1], p[2]) > timedelta(hours=3):
+            _done.add(p)
```

### M-7. The due time is not recomputed when an alert's first look moves earlier, and day alerts can be overdue when they are created.

`app/firms.py:108-112` (the merge path) moves `first_seen_utc` back to the FIRMS scan time but keeps `due_utc` from Bhuvan's later granule time. Across the 18:00 IST boundary the rule flips:
- Bhuvan at 18:04 IST falls under the night rule, so due is 09:00 the next day.
- The scan at 17:57 IST falls under the day rule, so due should be 22:57 IST.

`due_for` (`161-172`) also counts from the pass, not from when the alert arrived. A 13:30 IST pass that NASA delivers 6 h later (README: 4.5-6 h by day) is due at 19:30 IST, so it is overdue when it is created.

Reproduced: `t10_due_times.py`:
- A. first_seen `12:27Z`, due `2026-04-23T03:30Z`, while the rule gives `2026-04-22T17:27Z`, so the alert is due about 10 h late.
- B. "day pass due 19:30 IST, NASA file at 19:30 IST: overdue on creation".

The table in `t10.out` shows the rule as coded: 17:59 IST is due at 22:59 the same night, 18:00 is due at 09:00 the next day.

Fix:
- In the merge path, add `due_utc = min(due_utc, <due_for(FIRMS time)>)`, the same CASE as in the H-1 patch.
- In `attach_to_incident` for new alerts, use `due = max(due_for(t), now + 2 h)`, so a late alert is never born overdue. Also record `created_utc`, which exists already, in the stats on time to visit.

### M-8. Only the first of FSI's junction beats is kept (22% of FSI points carry two or more beats).

`app/fsi_portal.py:71-74`: `tag()` writes only `WHERE fsi_beat IS NULL`, and identical lat/lon/time rows de-duplicate in `store()`. FSI lists a junction pixel once per beat. In `ratapani/fsi/fsi_portal/obd_2026.csv`, 231 of 1,061 unique points have more than one beat. `alert.fsi.beats` therefore lists one beat, and the guards of the other beats (who receive FSI's SMS) are not linked.

Reproduced: `t07` D: FSI sent the same pixel for TAJPURA and CHOKA; the alert has `fsi.beats == ['Tajpura']`.

Fix: store FSI tags in their own table, `fsi_tags(detection_id, division, range, beat, compartment, PRIMARY KEY(detection_id, beat))`, and build `alert.fsi` from it. The `alert_json` side is in the API area.

### M-9. FSI tags and FIRMS fill-ins change an alert without moving any timestamp, so `GET /api/v1/alerts?since=` never returns those updates.

The `since` filter (`api_v1.py`) checks `last_seen_utc`, `first_report_utc` and `created_utc`. These ingest changes move none of them:
- an FSI tag added later (`fsi_portal.tag`, line 71);
- FIRMS filling a Bhuvan or FSI row (`firms.py:104-112`; this even moves `first_seen` back);
- promotion of an FSI-tagged point into an existing alert.

INTEGRATION.md says "FSI tags can arrive after the alert ... updated (`alert.updated` webhook)". A client that polls instead of using the webhook, and webhook events lost as in M-4, never see the update.

Read-only for the API side, but the cause is in ingest: add `incidents.updated_utc`, set it in every ingest `UPDATE` of an incident or its detections, and filter on it.

---

## LOW

L-1. **A renamed `confidence` column turns low-confidence points into tasks.** In `firms.py:51-55` a missing column gives `""`, which is not `"low"`. Reproduced in `t01` E. Fix: if the header lacks `confidence`, raise, as in H-5.

L-2. **The large-fire test uses a fixed 0.6 km and ignores pixel size.** `firms.py:250`: at the swath edge, VIIRS pixels are about 0.75 km along the scan, so 4 touching pixels are never flagged large. Reproduced in `t11` B (`large 0, points 4`). Fix: `<= 1.5 * max(scan_i, scan_j, 0.375)` (select `scan` in line 236). Unmerged Bhuvan rows have `scan=0`, which the `0.375` floor covers.

L-3. **A pixel that FIRMS later rates low still has its Bhuvan/FSI task.** `firms.py:104-107` copies `confidence='low'` onto the row but leaves the alert open (`t11` C). This may be intended, since FSI and Bhuvan did send it. If not, close a one-point alert whose only point turns low before anyone visits.

L-4. **The industry mask file is not checked.** If it is missing, the mask is silently empty (`geo.py:76`, `t17` A). If it is truncated, every `store()` raises `JSONDecodeError`, so every source fails every poll (`t17` B). Log a warning when it is missing, and catch a decode error once at start-up.

L-5. **`fsi_portal.match` scans every VIIRS row until statistics exist.** On a fresh database `ANALYZE` (`db.py:309`) runs on empty tables, and the planner picks the UNIQUE index on `instrument=?`. Cost per point grows linearly: 0.6 ms at season start, 14 ms at 138k rows (`t12`, 18 min). `PRAGMA optimize` after the first poll fixes the plan (0.02 ms, measured on a copy). It never runs in the scripts or during the first 7-day pull. Fix: `WHERE +instrument=? AND acq_utc BETWEEN ...` in `fsi_portal.py:56`, so the planner uses `det_latlon` or `det_time`.

L-6. **The WorldCover block cache can grow to about 400 MB.** `landcover.py:42`: `max_blocks=400` blocks of 1 MB each (measured `nbytes=1048576`). That is a lot on a small VM or a PC running other work. 64 blocks would do.

L-7. **Footprints are about 8% narrower east-west.** Read only. `geo.touching` (`r = km/111.32` degrees in both axes) and `landcover.classes` (`r_px` from latitude degrees) do not correct for cos(lat). At 23°N the footprint is about 8% narrower east-west, so a few junction beats and edge pixels are missed. Scale the longitude by `1/cos(lat)`.

L-8. **`demo_replay.py` can write into the live database, and puts MODIS points at the wrong time.** Without `FS_DATA_DIR` it writes into `./var`, the live default, and adds demo staff with PINs 1111/2222/3333 when `staff` is empty. Read only; not run that way. It also loads the `NRT-EE` MODIS rows, which have no time, at 00:00 UTC. In the smoke run (`runs/demo`), 14 of 14 MODIS points were at `T00:00:00Z`. Fix: refuse to run without `FS_DATA_DIR`, and skip rows with a blank `acq_time`.

L-9. **A UTF-8 BOM would break the FSI feed.** If the FSI CSV ever starts with one (common for .NET exports), the first key becomes `'﻿Fire_Date'` and the feed fails every poll (`t07` E). The saved exports have no BOM today. Fix: `decode("utf-8-sig")`, which is in the H-5 patch.

L-10. **`/api/ingest` can run alongside the poller, even in demo mode.** `server.py:841-843` has no lock, so a second `run_live` can run at the same time as the poll's: double downloads, and lock waits as in C-1 and H-6. Under `FS_DEMO_NOW` the poller is off, but this endpoint still pulls live data into the demo database. Fix: a lock in `run_live`, and refuse when `DEMO_NOW` is set.

L-11. **Day and night use three different definitions.** FSI uses UTC 00-12 (`fsi_portal.py:44`), Bhuvan uses IST 06-18, FIRMS uses the instrument flag, and `due_for` uses IST 06-18. `burn_hint` keys on `daynight == "D"`. Use one helper.

L-12. **FSI TLS failed from this sandbox.** Read only, environment. `fsiforestfire.gov.in` failed TLS verification here (`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`) from both curl and Python. It may be this sandbox's proxy, or the site missing an intermediate certificate (common on gov.in hosts). If the deployment PC sees the same, FSI errors on every poll. That is at least visible in `ingest_log`. Check once on the target machine.

Not applicable: date-line handling (MP is at 74-83°E). IST midnight is handled correctly in `bhuvan.pass_utc` and in the FSI date window, which starts from the UTC date minus 2 days. The Bhuvan panel lists only the current IST day's passes, and no 375 m pass over MP falls between 23:00 and 24:00 IST, so the midnight rollover drops nothing.

## Ranked fix order (suggested)

1. C-1 + H-6: read WorldCover outside the transaction, back off, and make error logging unable to raise. This stops field reports failing at pass times.
2. H-2 + H-1: the one-line Bhuvan fix, and joins regardless of arrival order. Duplicate tasks drop by about 20%.
3. H-3 + H-4 + H-5: `/api/health`, download deadlines, row-tolerant parsing, and "empty" or "no passes" treated as errors.
4. M-2 (owner decision), M-3, M-4, M-6, M-7.

## Fixes applied (20 Oct 2026)

The repros were copied to `/tmp/claude-0/fieldfix/itests/` (same harness, scratch moved) and run against the shipped code; outputs are `tNN.out` there. Once a finding is fixed, a repro's "FINDING" check prints FAIL. Some repros apply the proposed patches to the old code in memory (`t05` part 2, `t18`, `t19`); they no longer apply and were not used. `t01` stops at C1 because the old code did not raise there. Checks the old repros cannot express are in `itests/verify_ingest.py` (24 of 25 PASS; the one FAIL was a test bug, re-checked in `verify_m4.py`), `verify_m4.py`, `verify_m6.py` and `verify_m7.py` (all PASS). `scripts/bhuvan_test.py` and `scripts/source_order_test.py` pass on fresh folders. `scripts/run_tests.py` passes 4 of 4.

| Finding | Status | How checked |
|---|---|---|
| C-1 write lock held during WorldCover reads | fixed: WorldCover is read before the transaction; the store takes `BEGIN IMMEDIATE` up front; guard reports, chance finds and positions (built-in and v1) go through `db.write` (30 s busy wait plus 2 retries), and a lock that outlasts that gives 503, not 500. The field page keeps a report on a 5xx. `import_archive` commits every 500 points | t06 A: concurrent write ok after 0.0 s; verify_ingest: positions during a 35 s lock give 200 |
| H-1 grouping in arrival order | fixed: candidates up to `t + CLUSTER_HOURS`, and a merge moves `first_seen_utc` back with `due_utc`; the four NASA files are fetched, merged and stored as one time-sorted list | t04 A, B, C: 1 alert each; t05 part 1: feed-by-feed 533 against 524 time-sorted (was 641) |
| H-2 restart re-adds Bhuvan pixels | fixed: a Bhuvan point is skipped whenever the pixel is already stored | t03 C: 1 detection, 1 incident after restart |
| H-3 no health signal | fixed: `GET /api/v1/health` (extended, no new route) checks NASA (3 h), Bhuvan and FSI (6 h) separately, the poll heartbeat (over 30 min running, or none finished in 3 intervals) and points kept unfiltered; empty, header-only or HTML files and a panel with no passes raise and go to `ingest_log`; a failed Bhuvan pass goes to `ingest_log`; the control-room line shows each source's age and turns red when stale | verify_ingest H-3 rows; t13 C is answered by the extended v1 route |
| H-4 per-read timeouts, serial sources | fixed: `firms.http_get` with a 180 s total deadline (FIRMS, FSI); Bhuvan 3 tries, `(10, 30)` timeouts, 60 s deadline per try, 240 s budget per poll; Bhuvan, FSI and the NASA files download on separate threads, and stores run one at a time (`firms.LOCK`); a Bhuvan thread still hung from the last poll is reported and not started again | verify_ingest: deadline after 5 s; NASA point stored 0.2 s into a poll with a hung Bhuvan pass; t02 B: 0 s hold-back |
| H-5 one bad row drops the file | fixed: rows parsed one by one, bad ones counted and skipped; FSI keeps only VIIRS and MODIS; `utf-8-sig` | verify_ingest: 20 of 20 kept; t07 B, C: FSI ok |
| H-6 locked DB escapes run_live | fixed: `_log_error` retries and cannot raise; run_live returns with every source tried | t06 B; verify_ingest H-6 |
| M-1 cut acq_time accepted | fixed: needs a satellite, a numeric acq_time and no missing columns | verify_ingest M-1 |
| M-2 FSI-only alerts skip the mask | not fixed (owner decision) | t07 A still opens the task |
| M-3 archive import opens tasks, crashes, fails on a blank time | fixed: `store(..., tasks=False)`, `normalise` takes "800.0", rows without time or satellite dropped, bad rows counted | t09 A, B, C; verify_ingest M-3 |
| M-4 webhook threads, lost events | fixed: durable outbox and one worker (field audit C3); `alert_json` failures after the commit are logged per alert and no longer fail the feed. Still open: `alert_json` for every touched alert runs in the poll thread (t14: 41 s for 399 alerts), after the commit, with no lock held | t14 A: 0 threads; verify_m4 |
| M-5 WorldCover failure fails open, no trace, no back-off | fixed: 10 min back-off, unfiltered points counted in `ingest_log.forest_unknown`, logged, and reported by health. Holding such tasks is an owner decision | t08 A: 1 request for 3 points, t08 B: 0 s; verify_ingest M-5 |
| M-6 empty Bhuvan sheet marked done | fixed: re-read until 3 h after the pass | verify_m6 (t03 B uses a pass from April, so it is past 3 h) |
| M-7 due not recomputed; born overdue | fixed: merges take `min(due, due_for(earlier look))`; a live alert is due no sooner than 2 h after it arrives (not in replay mode, not for points older than `FS_VISIT_DUE_HOURS`) | t10 A; verify_m7 |
| M-8 only the first FSI junction beat kept | fixed: `fsi_tags` table, and `alert.fsi.beats` and `compartments` list every beat. Not done: linking the other beats' guards (FSI beat names need a mapping to our beat ids) | t07 D: ['Choka', 'Tajpura'] |
| M-9 ingest changes move no timestamp | fixed: `updated_utc` with a trigger on every incident update; an FSI tag also moves it | verify_ingest M-9 |
| L-1 renamed confidence column | fixed: the header must have `confidence` | verify_ingest H-3 "no confidence" |
| L-2 large-fire test ignores pixel size | fixed: `1.6 x max(scan, 0.375)` (0.6 km at nadir as before) | t11 B: large 1 |
| L-3 FIRMS rates a Bhuvan/FSI pixel low | not fixed (FSI and Bhuvan did send it; owner decision) | t11 C |
| L-4 mask file not checked | fixed: a missing or empty mask is logged; an unreadable one is logged and the stores carry on | t17 B; verify_ingest L-4 |
| L-5 FSI match scans every VIIRS row | fixed: `+instrument` | verify_ingest L-5: uses det_latlon |
| L-6 WorldCover cache up to 400 MB | not fixed (`landcover.py` is outside this change) | - |
| L-7 footprints narrower east-west | not fixed (read only; `geo.py`, `landcover.py`) | - |
| L-8 demo_replay can write into the live DB; timeless MODIS rows | fixed: refuses without `FS_DATA_DIR`, skips rows without a time or satellite | verify_ingest L-8 |
| L-9 BOM breaks FSI | fixed | t07 E, verify_ingest |
| L-10 /api/ingest alongside the poller, also in replay | fixed: one `run_live` at a time (`/api/ingest` gives 409 while a poll runs) and 409 in replay mode | verify_ingest L-10 |
| L-11 three day/night definitions | not fixed (changing it moves `burn_hint` and due times; owner decision) | - |
| L-12 FSI TLS from this sandbox | not fixed (environment; check once on the target PC, failures show in health) | - |

Needs an owner decision (not done):
- M-2: should FSI-only alerts go through the industry mask and the persistent-heat check (as the README says), given FSI's own SMS already goes out for them?
- M-5: when WorldCover cannot be read, keep opening the task (current behaviour, now counted and reported), or hold it until a later poll can check it?
- L-3: close a one-point Bhuvan/FSI alert when FIRMS later rates the pixel low?
- L-11: one day/night rule for FSI, Bhuvan, FIRMS and the due time.
- M-8: linking FSI's other junction beats to our beats needs an FSI-name to beat-id mapping.
- `ingest_log` now holds one row for the merged NASA store (source `FIRMS_<window>:<feeds>`) plus an error row for each failed file, instead of one row per file.
