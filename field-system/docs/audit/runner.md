# Audit: evening cloud runner (scripts/cloud_daily.py), 20 Oct 2026

Scope: `scripts/cloud_daily.py`, `app/cloud_{gfs,soil,modis,hls,inputs,build}.py`, `pc_models/` (builder, gfs_features,
soil_map, meta, calibration, models), and the call into `research/large-fires/watch/big_watch.py` (read, not edited).
Also checked: the app endpoints it posts to (`app/api_v1.py`, `app/daily_list.py`, `app/brief.py`), because the contract matters.

All tests are in `/tmp/claude-0/audit_runner/tests/`. `harness.py` loads `cloud_daily.py` with `CS` and the
`ratapani/mp_grid/dryness` path redirected into `/tmp/claude-0/audit_runner/work/<test>/`, so nothing is written under
`/mnt/project-files`. Network use was light: one Planetary Computer STAC query, two CMR queries, the three FIRMS 7-day files,
about 30 ARCO chunk HEAD-size probes, and one GFS day.
Each finding says **reproduced** (with the test) or **read only**.

Counts: **3 critical, 8 high, 8 medium, 7 low**.

---

## CRITICAL

### C1. Every live run re-appends the newest MODIS composite, and the builder then crashes. No list from the 2nd live run on.
`scripts/cloud_daily.py:75-84`, `app/cloud_modis.py:22-24`

`d0` is the day after the newest composite start. The STAC `datetime` search returns any item whose 8-day interval
*intersects* `[d0, t]`, so the newest composite (start = d0-1) comes back each time. `composites()` filters NASA granules
by `start >= d0` but not Planetary Computer items. The new values are concatenated with no check on dates. The second
duplicate makes `modis_frames` produce two rows per (date, cell), and `build_day_features.modis_asof` → `pivot` raises.

Reproduced (`tests/t3_modis_dup.py`):
```
A. composites(d0=2026-05-26) keys: ['2026-05-25']          <- live STAC/CMR query; 2026-05-25 is already stored
B. after live run 1: 35 composites, last 3 = ['2026-05-17', '2026-05-25', '2026-05-25'], duplicates = 1
B. after live run 2: 36 composites, ... duplicates = 2
B. build_day_features.build: ValueError Index contains duplicate entries, cannot reshape
```
For a new season the bootstrap run (no npz) works, and the next day's run crashes.

The same code has a related bug (read only). A composite is stored as soon as *any* item exists: one PC tile of six, or
MOD09A1 without MOD11A2 (LST NaN). It is never fetched again because `d0` moves past it. Also, values are loaded for the
current `cells`, but the old `z["cells"]` is kept. If the cell list ever changes (for example a new static table), the
columns are silently misaligned.

Patch: re-read a short window, merge by start date (new data replaces old), keep the result sorted, and check the cells:
```diff
--- a/scripts/cloud_daily.py
+++ b/scripts/cloud_daily.py
@@ -74,13 +74,21 @@ def update_inputs(t, S, divs):
     cells = np.unique(np.concatenate(list(divs.values())))
     f = CS / f"modis_{S}.npz"; z = dict(np.load(f)) if f.exists() else None
-    d0 = (pd.Timestamp(str(z["dates"][-1])) + pd.Timedelta(days=1)) if z else pd.Timestamp(f"{S - 1}-09-01")
+    if z is not None and not np.array_equal(z["cells"], cells):
+        raise SystemExit(f"{f}: cell list differs from static_inputs; rebuild the MODIS series")
+    # re-read the last 2 composites: the STAC search returns the composite overlapping d0, and late tiles / a late
+    # MOD11A2 must replace what was stored. Merge by composite start, never append blindly.
+    d0 = (pd.Timestamp(str(z["dates"][-1])) - pd.Timedelta(days=8)) if z else pd.Timestamp(f"{S - 1}-09-01")
     vals = cloud_modis.load(cells, bbox(cells), str(d0.date()), str(t.date()))
     if vals:
         q = lambda a, s: np.where(np.isfinite(a), np.round(a * s), -32768).astype(np.int16)
         V = np.stack([vals[k] for k in sorted(vals)])
         add = dict(dates=np.array([str(k.date()) for k in sorted(vals)]), ndvi=q(V[..., 0], 1e4), ndmi=q(V[..., 1], 1e4),
                    lst=q(V[..., 2] - 250, 50))
-        z = add | {"cells": cells.astype(np.int32)} if z is None else {"cells": z["cells"], **{k: np.concatenate([z[k], add[k]]) for k in add}}
-        np.savez_compressed(f, **z)
+        if z is not None:
+            old = ~np.isin(z["dates"], add["dates"])
+            add = {k: np.concatenate([z[k][old], add[k]]) for k in add}
+            o = np.argsort(add["dates"], kind="stable"); add = {k: v[o] for k, v in add.items()}
+        z = add | {"cells": cells.astype(np.int32)}
+        savez_atomic(f, z)                                   # see M2
```
Also make `inputs_asof` defensive, because the existing shared `modis_2026.npz` would get a duplicate on its first live run:
```diff
@@ -115,3 +115,5 @@ def inputs_asof(t, S, replay):
     mz = dict(np.load(CS / f"modis_{S}.npz"))
+    _, last = np.unique(mz["dates"][::-1], return_index=True); last = np.sort(len(mz["dates"]) - 1 - last)
+    mz = {k: (v[last] if k != "cells" else v) for k, v in mz.items()}       # one row per composite, the newest copy
     keep = pd.to_datetime(mz["dates"]) + pd.Timedelta(days=MODIS_AGE if replay else 0) <= t
```
In `cloud_modis.composites`, accept a composite only when both products have the full tile count (6 MODIS tiles over the
MP bbox). Otherwise leave it for the next run.

### C2. One missing GFS cycle stops every later run, and a failure throws away all days already fetched in that run.
`scripts/cloud_daily.py:59-62`, `app/cloud_gfs.py:16-26,44-47`

GFS days are fetched in one list comprehension and appended only at the end. Any `HTTPError` (today's 00Z late, or one
cycle that NOAA never uploads) raises out of `update_inputs`. The missing day is retried on every run, because it is
still not in `have`. So one permanently missing cycle means no list for the rest of the season. There is no fallback
(previous 18Z run, carry forward).

Reproduced (`tests/t1_sources.py`, `tests/t7_gfs_hole_soil_stale.py`):
```
[gfs_00z_missing] CRASH HTTPError: HTTP Error 404   series written: []   GFS days fetched before the failure and thrown away: 19
(a) 2026-11-04 OK
(a) 2026-11-06 CRASH HTTPError 404     (hole on 2026-11-05)
(a) 2026-11-20 CRASH HTTPError 404
(a) 2027-03-01 CRASH HTTPError 404
```
Measured cost: 13.6 s per GFS day for all 87 divisions (`t_gfs_time.py`). A first run on 20 Feb fetches 143 days
(about 33 min), and that work is all-or-nothing.

Patch: fetch day by day and save as you go. For a missing 00Z, use the previous day's 18Z run with lead +6 h. A past day
that is still missing is left as a gap (weather_table reindexes, and prcp rolling sums use min_periods). Only the issue
day is required.
```diff
--- a/app/cloud_gfs.py
+++ b/app/cloud_gfs.py
@@ -44,4 +44,6 @@
-def records(day, hour):
+def records(day, hour, cycle=0):
     """{name: 2-D field} for one forecast hour of the 00Z run of `day`."""
-    base = f"{BUCKET}/gfs.{pd.Timestamp(day):%Y%m%d}/00/atmos/gfs.t00z.pgrb2.0p25.f{hour:03d}"
+    run = pd.Timestamp(day) - pd.Timedelta(hours=(24 - cycle) % 24)          # cycle 18 = 18Z of the day before
+    hour = hour + (24 - cycle) % 24
+    base = f"{BUCKET}/gfs.{run:%Y%m%d}/{run.hour:02d}/atmos/gfs.t{run.hour:02d}z.pgrb2.0p25.f{hour:03d}"
@@ -53 +55 @@
-        take = name in WANT or (name == "APCP:surface" and bucket == f"{hour - 6}-{hour} hour acc fcst")
+        take = name in WANT or (name == "APCP:surface" and bucket == f"{hour - 6}-{hour} hour acc fcst")  # 6-h buckets in both runs
@@ -80,6 +82,13 @@
-def daily(day, hulls):
+def daily(day, hulls):
+    try:
+        return _daily(day, hulls, 0)
+    except Exception as e:
+        print("GFS 00Z", pd.Timestamp(day).date(), "missing:", str(e)[:80], "- using 18Z of the day before", flush=True)
+        return _daily(day, hulls, 18).assign(cycle="18Z-1")
+
+def _daily(day, hulls, cycle):
@@
-        f = records(day, h)
+        f = records(day, h, cycle)
```
(The 18Z run has 6-h APCP buckets at f012/f018/f024/f030, so the bucket test carries over.)
```diff
--- a/scripts/cloud_daily.py
+++ b/scripts/cloud_daily.py
@@ -59,4 +59,12 @@
     f = CS / f"gfs_daily_{S}.csv"; have = set(pd.read_csv(f, usecols=["date"]).date) if f.exists() else set()
-    new = [cloud_gfs.daily(d, hulls) for d in pd.date_range(f"{S - 1}-10-01", t) if str(d.date()) not in have]
-    if new:
-        append_csv(f, pd.concat(new), ["division", "date"])
+    new, miss = [], []
+    for d in pd.date_range(f"{S - 1}-10-01", t):
+        if str(d.date()) in have:
+            continue
+        try:
+            new.append(cloud_gfs.daily(d, hulls))
+        except Exception as e:
+            miss.append(str(d.date())); print("GFS", d.date(), "not available:", str(e)[:80], flush=True)
+        if len(new) >= 10 or (new and d == t):
+            append_csv(f, pd.concat(new), ["division", "date"]); new = []
+    STATUS["gfs_missing"] = miss                               # see M1; main() refuses to score if t is in miss
```
Add a `missing.json` skip list so a past day that has failed 3 times is no longer tried every evening.

### C3. Divisions "issue" from October to December and from June to September. Lists go out out of season.
`scripts/cloud_daily.py:42-44`

`started()` compares "MM-DD" strings: `"10-20" >= "02-20"` is true. Every division counts as started on every day from
1 Oct to 31 Dec and from 1 Jun to 30 Sep. The models' issue days are 13 Feb to 30 May, and big_watch raises outside them.

Reproduced (`tests/t2_season.py`):
```
2026-10-20 season 2027 divisions issuing 87
2026-12-31 season 2027 divisions issuing 87
2027-01-15 ... 0 | 2027-02-20 ... 7 | 2027-03-01 ... 78
2027-06-15 season 2027 divisions issuing 87
2027-09-30 season 2027 divisions issuing 87
```
Today (Oct–Dec) the runner crashes before it posts (H1). Once H1 is fixed, or if `CD_HLS` is set, it would post October
lists. In June it posts the daily list and then exits 1 in big_watch (`ValueError: issue days run 13 Feb - 30 May`).

```diff
@@ -39,6 +39,8 @@
 START = {"early": "02-20", "mid": "03-01", "late": "03-20"}
+END = "05-30"                                  # last issue day the models and big_watch were built for
 
 def started(dv, t):
     g = "early" if dv in EARLY else "late" if dv in LATE else "mid"
-    return f"{t.month:02d}-{t.day:02d}" >= START[g]
+    md = f"{t.month:02d}-{t.day:02d}"
+    return t.month < 10 and START[g] <= md <= END
```

---

## HIGH

### H1. From 1 Oct to 1 Jan every run crashes with `KeyError: 'CD_HLS'`, and a missing soil file crashes the first run.
`scripts/cloud_daily.py:118, 109, 136-143`

`hls_<S>.npz` is created only when the first step (2 Jan) is built. `inputs_asof` is called *before* the `if not live`
check, and it falls back to `os.environ["CD_HLS"]`. The runner has to run daily from 1 Oct to keep the 7-day FIRMS window
(H5), so it would fail with a traceback for 3 months. Real failures would then be hidden among these. If ERA5 is down on
the first run of a season, `swvl1_<S>.csv` does not exist and `read_csv` raises.

Reproduced (`tests/t2_season.py`):
```
inputs_asof 20 Oct 2026 (live): KeyError 'CD_HLS'
inputs_asof with no soil file yet: FileNotFoundError : '.../swvl1_2027.csv'
```
```diff
@@ -136,8 +136,11 @@ def main():
     if not a.replay:
         update_inputs(t, S, divs)
-    gfs, sw, mz, hz, fires = inputs_asof(t, S, a.replay)
-    cell, div, pct, score = [], [], [], []
     live = {dv for dv in meta["divisions"] if started(dv, t) or os.environ.get("CD_ALL_DIVISIONS")}
     print(t.date(), "divisions issuing", len(live), "of", len(meta["divisions"]), flush=True)
     if not live:
-        return
+        return 0                                   # inputs kept up to date; nothing to issue
+    gfs, sw, mz, hz, fires = inputs_asof(t, S, a.replay)
+    cell, div, pct, score = [], [], [], []
@@ -118 +121,4 @@
-    hz = dict(np.load(CS / f"hls_{S}.npz")) if (CS / f"hls_{S}.npz").exists() else dict(np.load(os.environ["CD_HLS"]))
+    hf = CS / f"hls_{S}.npz" if (CS / f"hls_{S}.npz").exists() else Path(os.environ.get("CD_HLS", "/nonexistent"))
+    if not hf.exists():
+        raise SystemExit(f"no HLS series for season {S} ({CS / f'hls_{S}.npz'}; replays: set CD_HLS)")
+    hz = dict(np.load(hf))
```
(also `sw = pd.read_csv(...) if exists else empty frame`, plus a stale-soil flag; see M1)

### H2. An HLS step built while LP DAAC has no looks (or only some) is stored as done, never rebuilt, and used right away.
`scripts/cloud_daily.py:86-93, 119`; `app/cloud_hls.py:149, 171-173, 183-185`

The live runner builds step `s` on day `s`. Its window is `[s-15, s)`, but HLS granules reach CMR about 44 h after
acquisition (median, measured below). If CMR returns no granules (outage or ingest backlog), `step_fast` returns NaN
indices with `clear = 0`. A look that fails to read is printed and dropped. In both cases `X[k,:,3] != -32768`, so the
step is never rebuilt. The `ok` mask in `inputs_asof` accepts it, and every hls_* input for the whole state is NaN until
the next step. In replay, steps are used 10 days late (`HLS_LATE`). Live uses them 0 days late, built from incomplete
data. So live does not match the setup that was validated (66.7/47.3/82.1).

Reproduced (`tests/t4_hls.py`, CMR returning no granules for step 2027-01-12):
```
2027-01-13: step_fast called for ['2027-01-12']; filled ['2027-01-02','2027-01-12']; clear% of 2027-01-12 = 0
2027-01-14: step_fast called for []                    <- never retried
2027-01-15 Guna hls_ndmi non-NaN share: 0.0 (step 2027-01-02 had values for 100%)
```
Live CMR today, Guna bbox (`granules.json`, `updated - time_start`): HLSS30 median lag 43.5 h (max 55 h), HLSL30 43.9 h
(max 91 h). The newest S30 granule starts on **10 Oct**, so on 20 Oct the last 10 days are missing.

```diff
@@ -89,5 +89,9 @@
     for k, s in enumerate(steps):
-        if s <= t and (z["X"][k, :, 3] == -32768).all():
+        clear = z["X"][k, :, 3]
+        due = s + pd.Timedelta(days=HLS_LATE) <= t          # as in the validated replay: looks for [s-15, s) are in by s+10
+        weak = (clear == -32768).all() or ((clear > 0).mean() < 0.5 and s + pd.Timedelta(days=HLS_LATE + 10) > t)
+        if due and weak:
             o = cloud_hls.step_fast(z["cells"], s)
+            if not np.isfinite(o[:, 0]).any():
+                print("HLS step", s.date(), "has no clear looks yet; will retry", flush=True); continue
             z["X"][k] = ...
@@ -119 +123 @@
-    ok = (hz["X"][:, :, 3] != -32768).any(1) & (pd.to_datetime(hz["steps"]) + pd.Timedelta(days=HLS_LATE if replay else 0) <= t)
+    ok = (hz["X"][:, :, 3] > 0).any(1) & (pd.to_datetime(hz["steps"]) + pd.Timedelta(days=HLS_LATE) <= t)
```
`step_fast` should also return how many looks it skipped, and the runner should rebuild the step when more than 10% were skipped.

### H3. big_watch's HLS file (`mp_dry_<S>.npz`) is copied once and never updated. The big-fire list runs on stale HLS.
`scripts/cloud_daily.py:99-101`

The copy runs only `if not dry.exists()`. Later steps stay at -32768 in big_watch's copy. `features.season_iter` treats
them as NaN and picks the step by date without an "ok" mask, so ndvi, ndmi, nbr, clear, d_ndmi and d_ndvi are NaN for the
whole state from the second step on. Nothing fails, so nobody notices.

Reproduced (`tests/t4_hls.py`):
```
2027-01-23: hls_2027 steps filled ['2027-01-02','2027-01-12','2027-01-22'] | mp_dry_2027 (big_watch) steps filled ['2027-01-02']
```
```diff
@@ -99,3 +99,6 @@
     dry = Path(f"/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_{S}.npz")    # big_watch reads HLS from here
-    if not dry.exists() and (CS / f"hls_{S}.npz").exists():
-        import shutil; shutil.copy(CS / f"hls_{S}.npz", dry)
+    src = CS / f"hls_{S}.npz"
+    if src.exists() and (not dry.exists() or dry.stat().st_mtime < src.stat().st_mtime):
+        import shutil; tmp = dry.with_suffix(".tmp.npz"); shutil.copy(src, tmp); os.replace(tmp, dry)
```
(With H2 applied, the copy holds only steps that are `due`, so big_watch also sees HLS 10 days late, as in replay.)

### H4. A FIRMS feed that is down or returns an empty body crashes the whole run. It has no retry, and comes after 30+ min of other downloads.
`scripts/cloud_daily.py:95`

`urlopen` is called once for each of the 3 feeds, with no retry. A 0-byte response raises `EmptyDataError`. All three must
succeed. The FIRMS step is the last one in `update_inputs`, so a failure there, after the GFS, soil, MODIS and HLS steps,
means no list.

Reproduced (`tests/t1_sources.py`):
```
[firms_down]        CRASH URLError: <urlopen error FIRMS down>
[firms_zero_bytes]  CRASH EmptyDataError: No columns to parse from file
[firms_header_only] OK
```
```diff
@@ -94,3 +94,18 @@
     from make_fire_celldays import to_celldays
-    v = pd.concat([pd.read_csv(urllib.request.urlopen(FIRMS.format(p=p, f=n), timeout=120)) for p, n in FEEDS])
+    parts = []
+    for p, n in FEEDS:
+        for k in range(4):
+            try:
+                parts.append(pd.read_csv(urllib.request.urlopen(FIRMS.format(p=p, f=n), timeout=120))); break
+            except Exception as e:
+                if k == 3:
+                    STATUS.setdefault("firms_failed", []).append(n); print("FIRMS", n, "failed:", str(e)[:80], flush=True)
+                else:
+                    import time; time.sleep(30 * (k + 1))
+    if not parts:
+        STATUS["firms_failed_all"] = True                          # score on yesterday's fires; flagged in the body (M1)
+        return
+    v = pd.concat(parts)
+    v = v[v.latitude.between(20.5, 27.5) & v.longitude.between(73.5, 83.5)]   # MP only (L1)
```

### H5. Fire history only comes from the 7-day files, from the day the runner starts. Any gap over 7 days is lost for good, and no check reports it.
`scripts/cloud_daily.py:95-103, 121-124`

`fire_celldays.parquet` ends on **2026-06-03**. After that the only fire source is `fires_live.parquet`, which gets the
FIRMS 7-day files only on days the runner runs, and no scheduler exists yet. Inputs that depend on the missing days:
`early_cell/nb3/nb7` (1 Oct – 14 Feb), `dsl` (400 days), `cell_d30`, `nb*_d7`, `fdist_d30`. big_watch's `season_iter`
rebuilds from **1 Jan** using only `firms_<S>.csv`. Today, 20 Oct, fires from 1–12 Oct 2026 can no longer be fetched from
the 7-day files. In past seasons those days were 0.6–2.8% of the early-burn window's cell-days. If the runner first runs
in February, the whole early-burn window is empty and the inputs are wrong without any error.
`scripts/viirs_backfill_laads.py` (NASA granules, sets type 2 next to past static sources) can fill gaps, but the runner
never calls it.

Reproduced (data check):
```
fire_celldays 2014-01-01 .. 2026-06-03
2025: early-burn window cell-days 112183, of which 1-12 Oct 622 (0.6%)   2023: 2126 (2.8%)
```
Patch: (1) schedule the runner daily from 1 Oct (see Operations). (2) Run a coverage check before scoring:
```diff
@@ -124,2 +124,8 @@
     fires["date"] = pd.to_datetime(fires.date); fires = fires[fires.date <= t]
+    have = set(fires.date[fires.date >= pd.Timestamp(f"{S - 1}-10-01")].dt.normalize())
+    gaps = [str(d.date()) for d in pd.date_range(f"{S - 1}-10-01", t - pd.Timedelta(days=1)) if d not in have]
+    if gaps:     # a day with no fire anywhere in MP is rare in Oct-May; runs of empty days mean a missed download
+        STATUS["fire_days_missing"] = gaps
+        print("WARNING fire history has", len(gaps), "empty days since 1 Oct, e.g.", gaps[:5],
+              "- backfill with scripts/viirs_backfill_laads.py", flush=True)
```
(3) Load `data/viirs_backfill/*.csv` (as `app/cloud_features.archive_points` already does) into `fires` and into the
big_watch `--firms` list.

### H6. 2027 prerequisites are not checked. Static and calibration files fall back silently to last season's; the big-fire step fails only after the daily list has been posted.
`scripts/cloud_daily.py:133, 153, 166-176`

- `static_inputs.parquet` is read every season. `make_static_season.py` writes `static_inputs_<S>.parquet` (AlphaEarth
  S-1), but the runner never reads it. 2027 would score with the 2025 embedding, and nothing says so.
- All 87 `calibration/*.json` say `fitted_on: 2025 season`. The app's rule says the % must come from the previous season,
  which is 2026 for 2027. The runner does not read `fitted_on`.
- `research/large-fires/watch/scar_hist_2027.npz` does not exist. big_watch fails in 6 s, *after* the daily POST, so the
  run exits 1 even though the daily list went out (M4).
- `mp_dry_2027.npz` is created by the runner's copy (and stays stale, H3).

Reproduced:
```
$ python big_watch.py 2027-03-01 --out /tmp/claude-0/audit_runner/out_bw
FileNotFoundError: ... research/large-fires/watch/scar_hist_2027.npz      (real 5.8 s)
Counter({'2025 season (15 Feb-31 May issue days 13 Feb-30 May)': 87})       (calibration fitted_on)
```
```diff
@@ -131,5 +131,22 @@ def main():
     t = pd.Timestamp(a.date or datetime.now(IST).date()); S = t.year if t.month < 10 else t.year + 1
     meta = json.loads((P / "meta.json").read_text())
-    static = pd.read_parquet(P / "static_inputs.parquet"); clim = pd.read_parquet(P / "modis_clim.parquet")
+    sf = P / f"static_inputs_{S}.parquet"
+    if not sf.exists() and S > 2026:
+        raise SystemExit(f"{sf.name} missing: run pc_models/make_static_season.py --season {S} (AlphaEarth {S - 1})")
+    static = pd.read_parquet(sf if sf.exists() else P / "static_inputs.parquet"); clim = pd.read_parquet(P / "modis_clim.parquet")
+    bad = [dv for dv in meta["divisions"]
+           if not json.loads((P / "calibration" / f"{dv}.json").read_text())["fitted_on"].startswith(str(S - 1))]
+    if bad and S > 2026 and not os.environ.get("CD_ALLOW_OLD_CAL"):
+        raise SystemExit(f"calibration not refitted on season {S - 1} for {len(bad)} divisions, e.g. {bad[:3]}")
+    W = Path("/mnt/project-files/research/large-fires/watch")
+    big_ok = (W / f"scar_hist_{t.year}.npz").exists()
+    if not big_ok:
+        print(f"WARNING big-fire watch disabled: {W}/scar_hist_{t.year}.npz missing (research/large-fires/scripts/l9_package.py)", flush=True)
```
In the big_watch call, skip it when `not big_ok`, and exit with a distinct code (M4).

### H7. Three divisions get an empty list in the app because their names differ: the runner uses underscores, the beats map uses spaces.
`scripts/cloud_daily.py:154-155, 178-180` (names from `meta.json` / `squares.npz`); `app/daily_list.py:198`, `app/brief.py:117`

`meta.json` names are `Barghat_Project`, `Kanha_Tiger_Reserve` and `PTR_MP`. In `data/beats_mp.geojson` they are
`Barghat Project`, `Kanha Tiger Reserve` and `PTR MP`. The other 84 match. The app stores the body's `division` as sent,
but `brief.statewide` and the officials' pages ask by beat division name. Those three divisions see 0 squares and
`own_count` 0. Their squares still take part in the statewide pool, so the work is assigned but nobody sees it. The
big-fire body has the same problem (it uses `squares.npz` divnames, which also have underscores).

Reproduced (`tests/t5_app_contract.py`, scratch SQLite):
```
division_view('Guna'): squares 997, own_count 992
division_view('Kanha Tiger Reserve'): squares 0, own_count 0
division_view('Kanha_Tiger_Reserve'): squares 849, own_count 847
division_view('PTR MP'): squares 0 | division_view('Barghat Project'): squares 0
```
```diff
@@ -33,2 +33,4 @@
 IST = timezone(timedelta(hours=5, minutes=30))
+# meta.json / squares.npz name -> the app's beat-map division name (data/beats_mp.geojson)
+APP_NAME = {"Barghat_Project": "Barghat Project", "Kanha_Tiger_Reserve": "Kanha Tiger Reserve", "PTR_MP": "PTR MP"}
@@ -154 +156 @@
-        cell += X.cell.tolist(); div += [dv] * len(X); ...
+        cell += X.cell.tolist(); div += [APP_NAME.get(dv, dv)] * len(X); ...
@@ -179,1 +181,1 @@
-    body = dict(..., division=D.division.tolist(), ...)
+    body = dict(..., division=D.division.map(lambda d: APP_NAME.get(d, d)).tolist(), ...)
```
A better fix is in the app: normalise `_` to space when the list is stored. That belongs to the app auditor; this patch works either way.

### H8. The officials' brief shows the list only from about 17:30 to midnight on its issue day, never on the two days it covers.
`app/brief.py:106` (contract with the runner's 17:00–18:00 IST timing; `app/daily_list.py:165`)

`_check_list` asks for `issue_date = today (IST)`. The runner posts day *t*'s list at about 17:30 IST, after the 16:00
brief. On *t*+1, which is the list's first day, the brief asks for *t*+1, and that list does not exist until 17:30. So the
morning and 4 pm briefs always show "no list". `/api/v1/daily_list` with no `day` uses `max(issue_date)`, which is correct.

Reproduced (`tests/t5_app_contract.py`; at 16:00 on day *t* the list does not exist yet in real use):
```
brief check_list at 10 Mar 18:30 IST (after the runner): 997 squares (issue 2027-03-10)
brief check_list at 11 Mar 07:00 IST (next morning, day 1 of the 2-day list): None
brief check_list at 11 Mar 16:00 IST (day 2 brief): None
```
```diff
--- a/app/brief.py
+++ b/app/brief.py
@@ -105,2 +105,5 @@ def _check_list(con, division, now_utc, beats):
     try:
-        v = daily_list.division_view(con, (now_utc + IST).strftime("%Y-%m-%d"), division, beats)
+        today = (now_utc + IST).strftime("%Y-%m-%d")
+        day = con.execute("SELECT max(issue_date) FROM daily_list_meta WHERE issue_date <= ? AND issue_date >= date(?, '-1 day')",
+                          (today, today)).fetchone()[0]
+        v = daily_list.division_view(con, day, division, beats) if day else None
```
(This is in the app's area, so it is flagged here for the app auditor. The runner's timing is what causes it.)

---

## MEDIUM

### M1. Stale inputs are never reported. Soil is carried forward without a limit, and nobody is told.
`scripts/cloud_daily.py:66-71, 148, 155`

The soil download catches every exception with `pass`. `w.swvl1.ffill()` has no limit. Stale MODIS, a failed HLS step, a
FIRMS gap or a GFS fallback are not printed and not in the body. Reproduced (`tests/t7_gfs_hole_soil_stale.py`):
`soil last observed 2027-01-29 -> swvl1 used on 2027-03-10 = 0.21 (no limit, no warning)`. Live ARCO today:
`valid_time_stop_era5t: 2026-10-13`, with a 404 hole on 2026-10-10 (probes in this audit). In live runs the soil age is
about 7 days. Replay validated with 15. ARCO ERA5T has paused for weeks in the past.

Patch: collect a `STATUS` dict and send it in the body. The app ignores unknown keys (`daily_list.build` reads only
named ones). Also write it to `CD_OUT/status_<date>.json` and exit 3 when an input is past its limit.
```diff
@@ -146,3 +146,4 @@
         w = G.weather_table(...)
-        w["swvl1"] = w.swvl1.ffill()
+        w["swvl1"] = w.swvl1.ffill(limit=20)              # 5-day shift + up to ~15 days old, as validated
+        STATUS.setdefault("soil_age_days", {})[dv] = int((t - sw[sw.division == dv].date.max()).days) if (sw.division == dv).any() else None
@@ -155 +156,6 @@
-    body = dict(issue_date=..., score=score)
+    STATUS["modis_newest"] = str(mz["dates"][-1]) if len(mz["dates"]) else None
+    STATUS["hls_newest"] = str(hz["steps"][-1]) if len(hz["steps"]) else None
+    body = dict(issue_date=..., score=score, inputs=STATUS)
+    stale = (max(v for v in STATUS["soil_age_days"].values() if v is not None) > 20 or
+             (t - pd.Timestamp(STATUS["modis_newest"])).days > 40 or STATUS.get("firms_failed_all"))
```
The app should show the officials a line such as "inputs stale: soil 25 days".

### M2. Series files are written in place, with no lock. An interrupted run or two runs at once leave a torn file, and every later run then crashes.
`scripts/cloud_daily.py:53, 84, 93, 98, 103`

`np.savez_compressed`, `to_csv` and `to_parquet` write straight to the target path. An OOM kill, a timeout, a full disk
(the shared folder is near its 10 GB cap) or a second run (cron plus a manual run) can leave half a file.
Reproduced (`tests/t6_torn_write.py`):
```
next run, update_inputs line 75 np.load(modis): BadZipFile File is not a zip file
torn gfs csv reads; bad date values in have: ['2026-0']   -> later: AttributeError Can only use .dt accessor
```
```diff
+def savez_atomic(f, z):
+    tmp = f.with_name(f.stem + ".tmp.npz"); np.savez_compressed(tmp, **z); os.replace(tmp, f)
+def write_atomic(f, df, fmt):
+    tmp = f.with_name(f.name + ".tmp"); (df.to_parquet(tmp, index=False) if fmt == "parquet" else df.to_csv(tmp, index=False)); os.replace(tmp, f)
@@ def main():
+    import fcntl
+    lock = open(CS / ".cloud_daily.lock", "w")
+    try:
+        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
+    except BlockingIOError:
+        raise SystemExit("another cloud_daily run holds the lock")
```
Then use `savez_atomic` and `write_atomic` at lines 53, 84, 93, 98 and 103.

### M3. Network: several calls have no retry or no sleep, and MODIS is all-or-nothing.
- FIRMS (`cloud_daily.py:95`): no retry (H4).
- The MODIS CMR query (`cloud_modis.py:29`) and Planetary Computer STAC search (`:20-24`) have no retry. pystac_client
  has no timeout by default (read only). A PC 503 crashes the run, as reproduced in `t1`: `[modis_down] CRASH ConnectionError`.
- `cloud_modis.load` keeps every composite in memory and saves only at the end. On a bootstrap with about 22 composites
  (a first run in February), a failure late in the run loses all of it. The PC hrefs are signed at search time, and the
  tokens can expire during a long run (read only).
- `cloud_soil._hour` retries 5 times with no sleep between tries (`cloud_soil.py:18-25`).
- The two POSTs (`cloud_daily.py:162-164, 185-187`) have no retry. The body is about 27 MB of JSON (see runtime) with a
  600 s timeout. If the POST fails, the list is in `CD_OUT/body_<date>.json.gz` and nothing resends it.
- Proxy and CA: urllib calls depend on `SSL_CERT_FILE` / `HTTPS_PROXY` being in the environment (they are in this
  container). The code sets only `CURL_CA_BUNDLE` / `GDAL_CURL_CA_BUNDLE` (`cloud_hls.py:16-18`). cron and systemd do not
  pass these variables on, so a scheduled run would fail TLS on every call (read only).

Patch: one shared helper, used by FIRMS, CMR and the POSTs:
```diff
+def http(url, data=None, headers=None, timeout=120, tries=4, method=None):
+    import time, ssl
+    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt") \
+        if os.path.exists(os.environ.get("SSL_CERT_FILE", "/root/.ccr/ca-bundle.crt")) else None
+    for k in range(tries):
+        try:
+            req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
+            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
+                return r.read()
+        except urllib.error.HTTPError as e:
+            if e.code in (400, 401, 403, 404) or k == tries - 1: raise
+        except Exception:
+            if k == tries - 1: raise
+        time.sleep(20 * (k + 1))
```
In `cloud_modis.load`, save after each composite: return a generator, or let the runner pass a callback.

### M4. Operations: one exit code for every failure, no status file, no alert. A big-fire failure looks the same as a daily-list failure.
`scripts/cloud_daily.py:128-188`

Any exception gives a traceback and exit 1. When the daily POST succeeds and big_watch fails (scar_hist missing, June
day, subprocess error), the run still exits 1. A re-run downloads and scores everything again. When `--post` is left out,
nothing is sent and the run exits 0. Output goes only to stdout, so there is no log file and no record of what went out.

Patch: exit codes 0 = list sent; 2 = daily list not sent; 3 = list sent but inputs stale; 4 = daily sent, big-fire failed.
Write `CD_OUT/status_<date>.json` (`posted`, `squares`, `inputs`, `errors`). Run big_watch in a `try`, and don't use
`check=True` to turn its error into a crash.

### M5. A first run takes too long for the 17:00–18:00 IST window, and runtime is not limited anywhere.
Measured or estimated for a first run on 20 Feb with no series:
- GFS: 13.6 s/day measured × 143 days ≈ 33 min.
- MODIS bootstrap: about 22 composites × 2 products × 6 tiles. PC is missing many Sep–Dec composites, so about 100 MB HDF
  downloads from NASA (read only), easily 30–60 min.
- HLS: 6 steps × 4–7 min (README) ≈ 30–40 min.
- Scoring and big_watch: see "Replay run" below.

That adds up to well over 1.5 h, so the list would go out after 19:00 IST. Fix: run daily from 1 Oct, which needs H1 and
C3 fixed, so that each evening fetches only one GFS day, at most one composite and at most one step. Add a cap
(`CD_DEADLINE`, for example 19:30 IST) after which the runner scores with what it has and flags it in `inputs`.

### M6. Public FIRMS files have no `type` column, so industrial and static heat sources count as vegetation fires.
`scripts/cloud_daily.py:96`

In the 2026 archive, type 2/3 points add 12,470 cell-days, 5.3% more than type 0 alone (525 cells, mostly outside
division squares). Those cells get `dsl` about 0 and `cell_d*` > 0 every week, and 350–700 squares a day are wrongly not
quiet. Reproduced (`t_type2.py`):
```
type-0 cell-days 235359  runner cell-days 247829  extra 12470 (5.3%)
2026-03-15 quiet squares PC-definition 205081  runner 204735  lost 346
2026-04-05 ... lost 402
```
Patch: use the same rule as `scripts/viirs_backfill_laads.py`. A point within 200 m of a past FIRMS type-2 point gets type 2:
```diff
-    v["type"] = v.get("type", 0)
+    if "type" not in v:
+        from scipy.spatial import cKDTree
+        st = static_points()        # cached: archive alerts_mp rows with type == 2, projected to EPSG:32643
+        x, y = TF.transform(v.longitude.values, v.latitude.values)
+        v["type"] = np.where(cKDTree(st).query(np.c_[x, y], distance_upper_bound=200)[0] < 200, 2, 0)
```

### M7. Live input ages differ from the replay that was validated.
In live mode soil is about 7 days old (replay 15), MODIS is whatever has been published (replay 21), and HLS is used on
the step day (replay 10 days late, see H2). The validated live-rule numbers (66.7/47.3/82.1) are for replay ages. After
H2 the HLS ages match. Soil and MODIS are fresher in live, which is closer to training, but it has not been tested.
Read only. Suggestion: replay one day with `CD_AGES=14,7,10` to compare.

### M8. Rows that come back as NaN are counted as done and never fetched again.
`scripts/cloud_daily.py:59,63-73`; `app/cloud_soil.py:34`

`have` is the set of dates in the file. A row of NaNs (for example an ARCO chunk filled with NaN) or a partial day is
never fetched again. ffill then hides it. Read only: no NaN chunk turned up in the probes, and holes come back as 404,
which is handled. Patch: `have = set(df.dropna(subset=[value col]).date)`.

---

## LOW

- **L1.** `firms_<S>.csv` (`cloud_daily.py:97-98`) keeps all of South Asia. Only 19.3% of today's 28,341 rows are inside
  the MP box, and in peak season South Asia has many times more points. The file is read and rewritten in full every
  day, and growing toward hundreds of MB it also slows big_watch. Its dedup key leaves out `satellite`. Fix: clip to the
  MP bbox (in the H4 patch), and add `satellite` to the key.
- **L2.** Replay needs `CD_HLS` because no `hls_2025/2026.npz` is in cloud_series, but the docstring doesn't say so.
  `w.loc[t]` raises a bare `KeyError` when GFS has no row for `t` (a replay past the file's end, or a live day after C2).
  It should say "no GFS for <date>".
- **L3.** `pct` units are correct: the body sends `np.interp(score, x, y)`, which is 0–1 (calibration y max 0.079 for
  Guna), and the app expects 0–1. But `calibration/*.json` say `"apply": "pct = 100 * numpy.interp(...)"` and
  `live_score.py` multiplies by 100. Anyone reusing those would send percents. Make the json match the API.
- **L4.** ERA5T values are never refreshed when final ERA5 replaces them (the window is only t-20..t). This is minor
  after soil_map. Live probe: hole on 2026-10-10 (404), filled later inside the window or carried forward.
- **L5.** big_watch's caches are hard-coded to other sessions' scratch paths (`lf_common.SC`, `system_rebuild/common.SC`
  under `/tmp/claude-0/-home-user/<other session>/`). On a fresh container they are rebuilt (`det_all.parquet` from every
  alerts_mp CSV) on the first run. `C.load_det()` keeps seasons 2014–2026 only, which is fine because 2027 rows come in
  via `--firms`. Read only (not edited, as instructed).
- **L6.** `big_watch()` rebinds `S` (the season) as a DataFrame (`cloud_daily.py:182`). It is harmless today but a trap
  for later edits.
- **L7.** `leaf_loss` is ±inf where `ndvi_peak == 0` (replay warning). This matches the PC. Leave it unless the models
  are retrained.

---

## Correctness checks that passed
- swvl1 carry-forward against `weather_table`'s `shift(5)`: the value used on *t* is the newest soil day *L* (shift then
  ffill). Live age is *t − L* (about 7 days), and replay is cut at *t − 15*, as intended. Holes are carried over. No limit (M1).
- The MODIS age filter is correct in both modes. Live keeps all stored composites and the builder adds the 9-day lag.
  Replay requires start + 21 ≤ t, which is stricter than the lag.
- The HLS step grid (2 Jan + 10 d to 21 Jun) is identical to `mp_dry_2026.npz` (18 steps). Values ≤ -10000 and clear
  outside 0–100 become NaN in the builder. The `ok` mask is too permissive (H2).
- soil_map is applied per division after the replay cut. All 87 divisions are in `soil_map.csv`, and values outside the
  fit are clamped by `np.interp`.
- FIRMS NRT satellite codes are `N`, `N20` and `N21` (checked in today's files), and big_watch maps all three. The NRT
  files have `daynight` and `frp`, which big_watch's control-burn flag needs. The confidence words
  (`nominal/low/high`) are not used with `cfg={}`.
- Division group names (EARLY/LATE) all exist in meta.json. 7 + 71 + 9 = 87.
- Re-running on the same day: GFS, soil and HLS are skipped, FIRMS and fires_live dedupe, and the app replaces the day
  (`DELETE ... WHERE issue_date`). The exception is MODIS (C1).

## Replay run (CD_OUT=/tmp/claude-0/audit_runner/out, 2026-04-05, CD_BIG=1)
Command: `CD_OUT=... CD_HLS=/tmp/claude-0/cloud_dry_2026.npz CD_BIG=1 python run_replay.py --date 2026-04-05 --replay`.
`run_replay.py` is runpy plus `getrusage`.
- Finished with exit 0. All 87 divisions, 430,776 squares, big-fire top1 4,232 / top2 8,422 (the same as the watch README).
- Wall time: **483 s in total**. Inputs and scoring took about 6 min, big_watch about 3 min.
- Peak RSS: runner **1.35 GB**, big_watch subprocess **6.23 GB**. That fits in 15 GB, but not with a statewide HLS step
  in the same container at the same time. Run the steps one after another, which is what the code does.
- The body is **28.6 MB** of JSON (5.3 MB gzipped), sent uncompressed in one POST with a 600 s timeout and no retry
  (M3). Add `Content-Encoding: gzip` or a gzip upload if the app accepts it.
- `RuntimeWarning: divide by zero` in `build_day_features.py:140`: `leaf_loss = 1 - ndvi / ndvi_peak` is ±inf where the
  peak is 0, and that value goes into the model. The PC code does the same, so it is not a regression. Noted as L7.

## Scheduling proposal (no cron exists; `crontab` is not even installed here)
1. A wrapper `scripts/cloud_daily.sh` that sources an env file (`HTTPS_PROXY`, `SSL_CERT_FILE`, `FS_SERVICE_KEY`, the
   app URL), sets `CD_OUT`, and runs `flock -n /var/lock/cloud_daily python cloud_daily.py --post $FS_URL`, appending to
   `logs/cloud_daily_<date>.log`.
2. A systemd timer (or cron with `CRON_TZ=Asia/Kolkata`) **every day from 1 Oct to 31 May** at 17:15 IST, with retries
   at 18:15 and 19:15 that exit at once if `status_<date>.json` says `posted`. Running from 1 Oct keeps the 7-day FIRMS
   window, GFS, soil and MODIS current (H5, M5). H1 and C3 must be fixed first.
3. A dead-man check in the app: if `daily_list_meta` has no row for today by 19:45 IST during the season, alert the
   control room and the operator (the app already has its notification path). Also alert when the body's `inputs` says
   stale. A cron exit code alone goes unnoticed.
4. A preflight on 1 Feb: static_inputs_<S>, calibration fitted on S-1, scar_hist_<S> (H6). Exit 2 with a clear message
   if any is missing.
