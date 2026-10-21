"""Evening cloud run of the officials' 2-day list: no PC, no Earth Engine (pc_models/CLOUD_PLAN.md).
Run every day from 1 Oct to 31 May at ~17:15 IST (scripts/cloud_daily.sh), after the afternoon VIIRS pass and that day's
GFS 00Z. Outside the issue window (13 Feb-30 May; per division from 20 Feb / 1 Mar / 20 Mar) it only keeps the input
series current, which the fire history and the first issue days need.

  1. inputs   brings pc_models/cloud_series/ up to the issue day, each source on its own (a failing source is logged and
              the run goes on): GFS (NOAA S3, 00Z; 18Z of the day before when 00Z is missing), ERA5 soil (ARCO; mapped to
              ERA5-Land with pc_models/soil_map), MODIS 8-day composites (Planetary Computer / NASA; the last 3 re-read and
              merged by date, so late tiles replace early ones), HLS 10-day steps (NASA; built 10 days after the step, as
              validated, and rebuilt while under half the state has a clear look), VIIRS fire cell-days (FIRMS public 7-day
              files, MP only; a point within 200 m of a past FIRMS static heat source is typed 2, as in
              viirs_backfill_laads.py, because the public files carry no 'type')
  2. features pc_models/build_day_features.build per division, with only what has arrived by issue time
  3. scores   shipped models + previous-season calibration -> POST /api/v1/daily_scores (the app applies the floor +
              quiet + statewide-pool rule and keeps the season's running state). The body's `inputs` says how old each
              input is and what failed.
  4. big-fire watch list (research/large-fires/watch/big_watch.py, top 1-2% per division) -> POST /api/v1/big_watch_scores,
              its own layer; it never changes the daily list. CD_BIG=0 skips it (replays: CD_BIG=1 adds it).

Usage: python cloud_daily.py [--date YYYY-MM-DD] [--replay] [--post http://host:port]
  --replay  past day: download nothing, cut every series at what would have arrived (MODIS start + 21 d, soil
            t - 15 d, HLS step + 10 d; PIPELINE's real delays, which cost ~1 pt: 66.7/47.3/82.1 vs 67.5/47.6/82.3).
            Needs CD_HLS=<hls npz> when cloud_series has no hls_<season>.npz; CD_ALL_DIVISIONS=1 scores all divisions.
  --post    send the bodies to the app (X-Api-Key from env FS_SERVICE_KEY); they are always written to CD_OUT too
            (default cloud_series/daily/), with status_<date>.json.
Exit codes: 0 list sent (or nothing to issue today), 2 daily list not sent, 3 sent but an input is stale or failed,
4 daily list sent but the big-fire watch list failed. Two runs never overlap (lock file)."""
import argparse, gzip, json, lzma, os, sys, time, traceback, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

FS = Path(__file__).resolve().parent.parent; P = FS / "pc_models"; CS = P / "cloud_series"
sys.path[:0] = [str(FS), str(P), str(P / "soil_map")]
import build_day_features as B, gfs_features as G, soil_map as SM
from app import cloud_gfs, cloud_soil, cloud_modis, cloud_hls
from app.cloud_build import hull
from app.cloud_inputs import bbox, modis_frames
IST = timezone(timedelta(hours=5, minutes=30))
MODIS_AGE, SOIL_AGE, HLS_LATE = (int(v) for v in os.environ.get("CD_AGES", "21,15,10").split(","))   # replay delays
STALE = dict(soil=20, modis=40)          # days: beyond these the body says stale and the run exits 3
# when each division's list starts (Akkshay's card in the Prithvi thread, 20 Oct 12:41Z; groups research/fire-timing/README.md
# section 6: early 7, mid 71, late 9). "Early March" is read as 1 Mar and "late March" as 20 Mar. Names are matched to meta.json.
EARLY = {"Alirajpur", "Burhanpur", "Sehore", "Dewas", "Dhar", "Lamta_Proj_N_Balaghat", "Lamta_Proj_S_Balaghat"}
LATE = {"North_Panna", "Panna_TR", "South_Panna", "Dindori", "Anuppur", "SANJAY_DUBRI", "Kuno_Palpur", "Shivpuri", "Gwalior"}
START, END = {"early": "02-20", "mid": "03-01", "late": "03-20"}, "05-30"     # END: last issue day the models were built for
# meta.json / squares.npz name -> the app's beat-map division name (data/beats_mp.geojson); the other 84 are the same
APP_NAME = {"Barghat_Project": "Barghat Project", "Kanha_Tiger_Reserve": "Kanha Tiger Reserve", "PTR_MP": "PTR MP"}
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/{p}/csv/{f}_South_Asia_7d.csv"
FEEDS = [("suomi-npp-viirs-c2", "SUOMI_VIIRS_C2"), ("noaa-20-viirs-c2", "J1_VIIRS_C2"), ("noaa-21-viirs-c2", "J2_VIIRS_C2")]
MP_BOX = (73.5, 20.5, 83.5, 27.5)
ARCH = Path("/mnt/project-files/fire-alert-scars/alerts_mp")
BIG = Path("/mnt/project-files/research/large-fires/watch")
STATUS = {"errors": [], "warnings": []}


def started(dv, t):
    g = "early" if dv in EARLY else "late" if dv in LATE else "mid"
    md = f"{t.month:02d}-{t.day:02d}"
    return t.month < 10 and START[g] <= md <= END


def warn(kind, msg):
    STATUS[kind].append(msg); print(kind[:-1].upper(), msg, flush=True)


def write_atomic(f, obj):
    """npz (dict), parquet or csv (DataFrame) written to a temp file and moved in, so a killed run never leaves half a file."""
    tmp = f.with_name(f.name + ".tmp")
    if isinstance(obj, dict):
        with open(tmp, "wb") as h:
            np.savez_compressed(h, **obj)
    elif f.suffix == ".parquet":
        obj.to_parquet(tmp, index=False)
    else:
        obj.to_csv(tmp, index=False)
    os.replace(tmp, f)


def http(url, data=None, headers=None, timeout=120, tries=4):
    """GET (or POST with data) with retries; 4xx other than 429 is not retried."""
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if (400 <= e.code < 500 and e.code != 429) or k == tries - 1:
                raise
        except Exception:
            if k == tries - 1:
                raise
        time.sleep(20 * (k + 1))


def append_csv(f, new, keys):
    old = pd.read_csv(f, parse_dates=["date"]) if f.exists() else new.iloc[:0]
    new = new.assign(date=pd.to_datetime(new.date))
    write_atomic(f, pd.concat([old, new]).drop_duplicates(keys, keep="last").sort_values(keys[::-1]))


def have_days(f, col):
    """dates already in a series file with a real value (NaN rows are fetched again)."""
    if not f.exists():
        return set()
    d = pd.read_csv(f, usecols=["date", col]).dropna()
    return set(d.date.astype(str).str[:10])


def given_up(name, day=None, add=False):
    """past days a source has failed 3 times on are not tried every evening (cloud_series/missing.json)."""
    f = CS / "missing.json"; m = json.loads(f.read_text()) if f.exists() else {}
    if add:
        m.setdefault(name, {}); m[name][day] = m[name].get(day, 0) + 1
        f.write_text(json.dumps(m, indent=1))
        return False
    return m.get(name, {}).get(day, 0) >= 3 if day else m.get(name, {})


def update_gfs(t, S, hulls):
    f = CS / f"gfs_daily_{S}.csv"; have = have_days(f, "t_mean"); new = []
    for d in pd.date_range(f"{S - 1}-10-01", t):
        ds = str(d.date())
        if ds in have or (d < t and given_up("gfs", ds)):
            continue
        try:
            new.append(cloud_gfs.daily(d, hulls))
        except Exception as e:
            given_up("gfs", ds, add=True); warn("warnings", f"GFS {ds} not available: {str(e)[:80]}")
        if len(new) >= 10 or (new and d == t):              # save as it goes: a later failure keeps what was fetched
            append_csv(f, pd.concat(new), ["division", "date"]); new = []


def update_soil(t, S, hulls):
    f = CS / f"swvl1_{S}.csv"; have = have_days(f, "swvl1"); rows = []
    W = {dv: cloud_gfs.weights(h) for dv, h in hulls.items()}
    first = pd.Timestamp(f"{S - 1}-09-24")
    for d in pd.date_range(max(first, t - pd.Timedelta(days=SOIL_AGE + 15)) if have else first, t):
        ds = str(d.date())
        if ds in have:
            continue
        try:
            rows += [dict(division=k, date=d, swvl1=v) for k, v in cloud_soil.daily(d, W).items()]
        except Exception:                                    # ERA5T runs ~6-7 days behind: recent days 404 until then
            pass
        if len(rows) >= 87 * 10:
            append_csv(f, pd.DataFrame(rows), ["division", "date"]); rows = []
    if rows:
        append_csv(f, pd.DataFrame(rows), ["division", "date"])


def update_modis(t, S, cells):
    f = CS / f"modis_{S}.npz"; z = dict(np.load(f)) if f.exists() else None
    if z is not None and not np.array_equal(z["cells"], cells):
        raise RuntimeError(f"{f.name}: cell list differs from static_inputs; rebuild the MODIS series")
    # the STAC search returns the composite overlapping d0, and late tiles / a late MOD11A2 must replace what was stored:
    # re-read the last 3 composites and merge by composite start, never append blindly
    d0 = (pd.Timestamp(str(z["dates"][-1])) - pd.Timedelta(days=16)) if z is not None else pd.Timestamp(f"{S - 1}-09-01")
    vals = cloud_modis.load(cells, bbox(cells), str(d0.date()), str(t.date()))
    if not vals:
        return
    q = lambda a, s: np.where(np.isfinite(a), np.round(a * s), -32768).astype(np.int16)
    ks = sorted(vals); V = np.stack([vals[k] for k in ks])
    add = dict(dates=np.array([str(k.date()) for k in ks]), ndvi=q(V[..., 0], 1e4), ndmi=q(V[..., 1], 1e4), lst=q(V[..., 2] - 250, 50))
    if z is not None:
        old = ~np.isin(z["dates"], add["dates"])
        add = {k: np.concatenate([z[k][old], add[k]]) for k in add}
        o = np.argsort(add["dates"], kind="stable"); add = {k: v[o] for k, v in add.items()}
    write_atomic(f, add | {"cells": cells.astype(np.int32)})


def update_hls(t, S, cells):
    f = CS / f"hls_{S}.npz"
    steps = pd.date_range(f"{S}-01-02", f"{S}-06-21", freq="10D")
    z = dict(np.load(f)) if f.exists() else dict(cells=cells.astype(np.int32), steps=np.array([str(s.date()) for s in steps]),
                                                  X=np.full((len(steps), len(cells), 4), -32768, np.int16))
    for k, s in enumerate(steps):
        clear = z["X"][k, :, 3]
        due = s + pd.Timedelta(days=HLS_LATE) <= t           # looks for [s-15, s) are on NASA by s+10 (lag ~44 h, max ~4 d)
        weak = (clear == -32768).all() or ((clear > 0).mean() < 0.5 and t <= s + pd.Timedelta(days=HLS_LATE + 10))
        if not (due and weak):
            continue
        o = cloud_hls.step_fast(z["cells"], s)
        if not np.isfinite(o[:, 0]).any():
            warn("warnings", f"HLS step {s.date()} has no clear looks yet; tried again next run"); continue
        z["X"][k] = np.where(np.isfinite(o), np.round(o * np.array([1e4, 1e4, 1e4, 1], np.float32)), -32768).astype(np.int16)
        write_atomic(f, z)
    dry = Path(f"/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_{S}.npz")    # big_watch reads HLS from here
    if f.exists() and (not dry.exists() or dry.stat().st_mtime < f.stat().st_mtime) and S > 2026:   # never touch the PC's files
        import shutil; tmp = dry.with_name(dry.name + ".tmp"); shutil.copy(f, tmp); os.replace(tmp, dry)


def static_heat():
    """x, y (EPSG:32643) of past FIRMS type-2 (static land source) VIIRS points in MP, cached in cloud_series."""
    f = CS / "static_heat_xy.npy"
    if not f.exists():
        from pyproj import Transformer
        st = pd.concat([pd.read_csv(g, usecols=["latitude", "longitude", "type"]) for g in ARCH.glob("viirs-*.csv")])
        st = st[st.type == 2].drop_duplicates()
        x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(st.longitude.values, st.latitude.values)
        np.save(f, np.c_[x, y].astype(np.float32))
    return np.load(f)


def update_fires(S):
    from make_fire_celldays import to_celldays
    parts = []
    for p, n in FEEDS:
        try:
            raw = http(FIRMS.format(p=p, f=n))
            if raw.strip():
                import io; parts.append(pd.read_csv(io.BytesIO(raw)))
        except Exception as e:
            warn("errors", f"FIRMS {n} failed: {str(e)[:80]}")
    if not parts:
        STATUS["firms_failed_all"] = True
        return
    v = pd.concat(parts, ignore_index=True)
    v = v[v.longitude.between(MP_BOX[0], MP_BOX[2]) & v.latitude.between(MP_BOX[1], MP_BOX[3])].copy()
    if "type" not in v:
        from scipy.spatial import cKDTree
        from pyproj import Transformer
        x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(v.longitude.values, v.latitude.values)
        d, _ = cKDTree(static_heat()).query(np.c_[x, y], distance_upper_bound=200)
        v["type"] = np.where(np.isfinite(d), 2, 0)
    f = CS / f"firms_{S}.csv"                                  # raw rows, for the big-fire watch list
    keys = ["latitude", "longitude", "acq_date", "acq_time", "satellite"]
    write_atomic(f, (pd.concat([pd.read_csv(f), v]) if f.exists() else v).drop_duplicates(keys))
    f = CS / "fires_live.parquet"; new = to_celldays(v)
    write_atomic(f, (pd.concat([pd.read_parquet(f), new]) if f.exists() else new).drop_duplicates())


def update_inputs(t, S, divs):
    """download whatever is missing up to issue day t; each source on its own."""
    hulls = {dv: hull(c) for dv, c in divs.items()}
    cells = np.unique(np.concatenate(list(divs.values())))
    for name, fn in (("fires", lambda: update_fires(S)), ("gfs", lambda: update_gfs(t, S, hulls)),
                     ("soil", lambda: update_soil(t, S, hulls)), ("modis", lambda: update_modis(t, S, cells)),
                     ("hls", lambda: update_hls(t, S, cells))):
        t0 = time.time()
        try:
            fn()
        except Exception as e:
            warn("errors", f"{name} update failed: {type(e).__name__}: {str(e)[:120]}"); traceback.print_exc()
        print("inputs", name, f"{time.time() - t0:.0f}s", flush=True)


def inputs_asof(t, S, replay):
    """series as they stood at issue time on day t, and how old each one is (STATUS)."""
    gfs = pd.read_csv(CS / f"gfs_daily_{S}.csv", parse_dates=["date"]); gfs = gfs[gfs.date <= t]
    if not (gfs.date == t).any():
        raise RuntimeError(f"no GFS for {t.date()} (00Z and 18Z of the day before both missing)")
    sf = CS / f"swvl1_{S}.csv"
    sw = pd.read_csv(sf, parse_dates=["date"]).dropna() if sf.exists() else pd.DataFrame(columns=["division", "date", "swvl1"])
    if replay:
        sw = sw[sw.date <= t - pd.Timedelta(days=SOIL_AGE)]
    M = SM.load()
    for dv, i in sw.groupby("division").groups.items():
        sw.loc[i, "swvl1"] = SM.apply(M, dv, sw.loc[i, "swvl1"].to_numpy())
    STATUS["soil_newest"] = str(sw.date.max().date()) if len(sw) else None
    mz = dict(np.load(CS / f"modis_{S}.npz"))
    _, first = np.unique(mz["dates"][::-1], return_index=True); last = np.sort(len(mz["dates"]) - 1 - first)
    mz = {k: (v[last] if k != "cells" else v) for k, v in mz.items()}          # one row per composite, the newest copy
    keep = pd.to_datetime(mz["dates"]) + pd.Timedelta(days=MODIS_AGE if replay else 0) <= t
    mz = {k: (v[keep] if k != "cells" else v) for k, v in mz.items()}
    STATUS["modis_newest"] = str(mz["dates"][-1]) if len(mz["dates"]) else None
    hf = CS / f"hls_{S}.npz" if (CS / f"hls_{S}.npz").exists() else Path(os.environ.get("CD_HLS", "/nonexistent"))
    if not hf.exists():
        raise RuntimeError(f"no HLS series for season {S} ({CS / f'hls_{S}.npz'}; replays: set CD_HLS)")
    hz = dict(np.load(hf))
    ok = (hz["X"][:, :, 3] > 0).any(1) & (pd.to_datetime(hz["steps"]) + pd.Timedelta(days=HLS_LATE) <= t)
    hz = dict(cells=hz["cells"], steps=hz["steps"][ok], X=hz["X"][ok])
    STATUS["hls_newest"] = str(hz["steps"][-1]) if len(hz["steps"]) else None
    fires = [pd.read_parquet(P / "fire_celldays.parquet")]
    if (CS / "fires_live.parquet").exists():
        fires.append(pd.read_parquet(CS / "fires_live.parquet"))
    from make_fire_celldays import to_celldays
    for g in sorted((FS / "data/viirs_backfill").glob("*.csv")):             # gap fills from NASA granules
        fires.append(to_celldays(pd.read_csv(g)))
    fires = pd.concat(fires, ignore_index=True)
    fires["date"] = pd.to_datetime(fires.date); fires = fires[fires.date <= t].drop_duplicates()
    have = set(fires.date[fires.date >= pd.Timestamp(f"{S - 1}-10-01")])
    gaps = [str(d.date()) for d in pd.date_range(f"{S - 1}-10-01", t - pd.Timedelta(days=1)) if d not in have]
    if gaps:     # a day with no VIIRS point anywhere in MP is rare in Oct-May; empty days mean a missed download
        STATUS["fire_days_missing"] = gaps
        warn("warnings", f"fire history has {len(gaps)} empty days since 1 Oct, e.g. {gaps[:5]}: backfill with scripts/viirs_backfill_laads.py")
    return gfs, sw, mz, hz, fires


def preflight(S, t):
    """files a new season needs; returns the static table path."""
    sf = P / f"static_inputs_{S}.parquet"
    if S > 2026 and not sf.exists():
        raise RuntimeError(f"{sf.name} missing: run pc_models/make_static_season.py for season {S} (AlphaEarth {S - 1})")
    meta = json.loads((P / "meta.json").read_text())
    old = [dv for dv in meta["divisions"] if str(S - 1) not in json.loads((P / "calibration" / f"{dv}.json").read_text()).get("fitted_on", "")]
    if S > 2026 and old and not os.environ.get("CD_ALLOW_OLD_CAL"):
        raise RuntimeError(f"calibration not refitted on season {S - 1} for {len(old)} divisions, e.g. {old[:3]} (CD_ALLOW_OLD_CAL=1 to go on)")
    return sf if sf.exists() else P / "static_inputs.parquet"


def post(a, path, body):
    if not a.post:
        return None
    r = http(a.post.rstrip("/") + path, data=json.dumps(body).encode(), timeout=600, tries=3,
             headers={"Content-Type": "application/json", "X-Api-Key": os.environ.get("FS_SERVICE_KEY", "")})
    return r[:300].decode(errors="replace")


def score_day(t, S, a, out, divs, static, meta, live):
    gis = pd.read_parquet("/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet")
    clim = pd.read_parquet(P / "modis_clim.parquet")
    gfs, sw, mz, hz, fires = inputs_asof(t, S, a.replay)
    cell, div, pct, score, soil_age = [], [], [], [], {}
    for dv, info in sorted(meta["divisions"].items()):
        if dv not in live:
            continue
        w = G.weather_table(gfs[gfs.division == dv].set_index("date"), sw[sw.division == dv].set_index("date").swvl1)
        w["swvl1"] = w.swvl1.ffill(limit=STALE["soil"])        # 5-day shift + carried forward, at most ~25 days old
        last = sw.date[sw.division == dv].max()
        soil_age[dv] = int((t - last).days) if pd.notna(last) else None
        sr, lst = modis_frames(mz, divs[dv], S)
        X = B.build(B.Division(dv, divs[dv]), t, static, gis, fires, sr, lst, clim[clim.division == dv], hz, w.loc[t], info["features"])
        m = lgb.Booster(model_str=lzma.decompress((P / "models" / f"{dv}.txt.xz").read_bytes()).decode())
        s = m.predict(X.reindex(columns=info["features"]))
        cal = json.loads((P / "calibration" / f"{dv}.json").read_text())
        cell += X.cell.tolist(); div += [APP_NAME.get(dv, dv)] * len(X); score += s.tolist()
        pct += np.interp(s, cal["x"], cal["y"]).tolist()                       # 0-1, as the API takes it
    ages = [v for v in soil_age.values() if v is not None]
    STATUS["soil_age_days"] = max(ages) if ages else None
    STATUS["modis_age_days"] = int((t - pd.Timestamp(STATUS["modis_newest"])).days) if STATUS["modis_newest"] else None
    STATUS["hls_age_days"] = int((t - pd.Timestamp(STATUS["hls_newest"])).days) if STATUS["hls_newest"] else None
    stale = [k for k in ("soil", "modis") if STATUS[f"{k}_age_days"] is None or STATUS[f"{k}_age_days"] > STALE[k]]
    if STATUS.get("firms_failed_all"):
        stale.append("fires")
    STATUS["stale"] = stale
    body = dict(issue_date=str(t.date()), model_version="pc_models cloud", cell=cell, division=div, pct=pct, score=score,
                inputs={k: v for k, v in STATUS.items() if k != "errors"} | {"errors": STATUS["errors"]})
    if a.replay:
        body["as_of_utc"] = (t + pd.Timedelta(hours=11, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")   # 17:00 IST
    with gzip.open(out / f"body_{t.date()}.json.gz", "wt") as f:
        json.dump(body, f)
    STATUS["daily_squares"] = len(cell)
    STATUS["daily_posted"] = post(a, "/api/v1/daily_scores", body)
    print(t.date(), "squares", len(cell), "stale", stale, flush=True)


def big_watch(t, S, out, a, live):
    """the big-fire watch list (research/large-fires/watch): its own layer, never touches the daily list."""
    import subprocess
    if not (BIG / f"scar_hist_{t.year}.npz").exists():
        raise RuntimeError(f"scar_hist_{t.year}.npz missing: build it with research/large-fires/scripts/l9_package.py")
    firms = [str(CS / f"firms_{S}.csv")] if (CS / f"firms_{S}.csv").exists() and not a.replay else []
    subprocess.run([sys.executable, str(BIG / "big_watch.py"), str(t.date()), "--out", str(out)] + (["--firms"] + firms if firms else []),
                   check=True, cwd=str(BIG), timeout=3600)
    A = pd.read_parquet(out / f"big_watch_{t.date()}.parquet")
    D = A[A.top2 & A.division.isin(live)]                # same division start dates as the daily list
    body = dict(issue_date=str(t.date()), model_version="large-fires watch", cell=D.cell.tolist(),
                division=[APP_NAME.get(d, d) for d in D.division], rank_in_division=D.rank_in_division.tolist(),
                top1=D.top1.tolist(), top2=D.top2.tolist())
    if "size_score" in A:                          # every square, for the officials' new-fire order (app/big_fire.py)
        U = A.drop_duplicates("cell")
        body.update(size_cell=U.cell.tolist(), size_score=U.size_score.round(5).tolist())
    STATUS["big_posted"] = post(a, "/api/v1/big_watch_scores", body)
    print(t.date(), "big-fire watch top1", int(D.top1.sum()), "top2", len(D), flush=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date"); ap.add_argument("--replay", action="store_true"); ap.add_argument("--post")
    a = ap.parse_args()
    t = pd.Timestamp(a.date or datetime.now(IST).date()); S = t.year if t.month < 10 else t.year + 1
    out = Path(os.environ.get("CD_OUT", CS / "daily")); out.mkdir(exist_ok=True, parents=True)
    import fcntl
    lock = open((out if a.replay else CS) / ".cloud_daily.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another cloud_daily run holds the lock", flush=True); return 2
    STATUS.update(date=str(t.date()), season=S, started_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    code = 0
    try:
        meta = json.loads((P / "meta.json").read_text())
        live = {dv for dv in meta["divisions"] if started(dv, t) or (a.replay and os.environ.get("CD_ALL_DIVISIONS"))}
        STATUS["divisions_issuing"] = len(live)
        static_f = preflight(S, t) if live else P / "static_inputs.parquet"
        static = pd.read_parquet(static_f)
        divs = {dv: np.sort(static.loc[static.division == dv, "cell"].to_numpy()) for dv in meta["divisions"]}
        if not a.replay:
            if not a.post:
                warn("warnings", "live run without --post: lists are written to disk only, the app gets nothing")
            update_inputs(t, S, divs)
        print(t.date(), "divisions issuing", len(live), "of", len(meta["divisions"]), flush=True)
        if not live:
            return 0                                         # inputs kept current; nothing to issue today
        try:
            score_day(t, S, a, out, divs, static, meta, live)
        except Exception as e:
            warn("errors", f"daily list not sent: {type(e).__name__}: {str(e)[:200]}"); traceback.print_exc()
            return 2
        code = 3 if STATUS["stale"] or STATUS["errors"] else 0
        if os.environ.get("CD_BIG", "0" if a.replay else "1") == "1":         # replays skip it unless CD_BIG=1
            try:
                big_watch(t, S, out, a, live)
            except Exception as e:
                warn("errors", f"big-fire watch list not sent: {type(e).__name__}: {str(e)[:200]}"); traceback.print_exc()
                code = 4
        return code
    finally:
        STATUS["finished_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (out / f"status_{t.date()}.json").write_text(json.dumps(STATUS, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
