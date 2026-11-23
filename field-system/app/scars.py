"""Burn scar for each alert, from the burn-scar thread's published lookups (/mnt/project-files/fire-alert-scars/).

scar_found is yes / faint / none_visible / unknown. none_visible is NOT a false alert: fires of
~0.15 ha, litter-only burns and burns under green canopy leave nothing a 20 m sensor can see.
So the scar can support a visit, never overrule one.
"""
import csv, json, math, os
from datetime import date, timedelta
from . import config

csv.field_size_limit(10 ** 9)
ROOT = os.environ.get("FS_SCAR_DIR", "/mnt/project-files/fire-alert-scars")
# Daily live results: the Ratapani-only folder (to 15 Oct 2026), then the all-MP folder (config.SCAR_LIVE_DIR).
LIVE_DIRS = list(dict.fromkeys([os.path.join(ROOT, "live"), config.SCAR_LIVE_DIR]))
LIVE_ALERTS = {os.path.join(d, "alerts.csv"): os.path.join(d, "events.csv") for d in LIVE_DIRS}
# (lookup file, file with the scar outlines by event_id); later files win: live results are the newest.
# FIRMS and FSI event ids can collide (both E{date}-NNN), so outlines are looked up per source.
FILES = [
    (os.path.join(ROOT, "alert_scar_lookup.csv"), os.path.join(ROOT, "out/event_scars.csv")),
    (os.path.join(ROOT, "fsi/fsi_alert_scar_lookup.csv"), os.path.join(ROOT, "fsi/fsi_alert_events.csv")),
] + [(os.path.join(d, "alerts.csv"), os.path.join(d, "scars.geojson")) for d in LIVE_DIRS]   # status from live events.csv
RANK = {"yes": 3, "faint": 2, "none_visible": 1, "unknown": 0}
WAITING = ("waiting", "no_pre")
_cache, _stamp = {}, None
_geo_lock = __import__('threading').Lock()


_stat = {}


def _mtimes(paths):
    """File change times, re-read at most once a minute (the files sit on a slow network mount)."""
    import time
    key = tuple(paths)
    if key not in _stat or time.time() - _stat[key][0] > 60:
        _stat[key] = (time.time(), tuple(os.path.getmtime(p) if os.path.exists(p) else 0 for p in paths))
    return _stat[key][1]


def _load():
    global _cache, _stamp
    stamp = _mtimes([f[0] for f in FILES] + list(LIVE_ALERTS.values()))
    if stamp == _stamp:
        return _cache
    idx = {}
    for src, (p, _) in enumerate(FILES):
        if not os.path.exists(p):
            continue
        ev = {}
        if p in LIVE_ALERTS and os.path.exists(LIVE_ALERTS[p]):
            with open(LIVE_ALERTS[p], newline="") as f:
                ev = {r["event_id"]: r for r in csv.DictReader(f)}
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                if p in LIVE_ALERTS:
                    e = ev.get(r.get("event_id"))
                    if not e:
                        continue
                    st = str(e.get("status", ""))
                    r = {**e, **{k: r[k] for k in ("latitude", "longitude", "acq_date")}, "scar_status": st,
                         "scar_found": "faint" if st.startswith("scar_faint") else "yes" if st.startswith("scar")
                         else "none_visible" if st.startswith("no_scar") else "unknown"}
                r["_src"] = src
                try:
                    k = (r["acq_date"][:10], round(float(r["latitude"]), 3), round(float(r["longitude"]), 3))
                except (KeyError, ValueError):
                    continue
                idx[k] = r
    _cache, _stamp = idx, stamp
    return idx


def _simplify(g):
    """Drop vertices closer than ~5 m and round to 5 decimals: outlines stay exact enough for a map."""
    try:
        from shapely.geometry import shape, mapping
        s = shape(g).simplify(0.00005, preserve_topology=True)
        return json.loads(json.dumps(mapping(s)), parse_float=lambda v: round(float(v), 5))
    except Exception:
        return g


def _geo_db():
    """Scar outlines, simplified, in a small SQLite file next to the database (rebuilt when the burn-scar
    files change). Loading the ~200 MB outline files into the server's memory instead would cost ~0.5 GB."""
    import sqlite3
    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = os.path.join(config.DATA_DIR, "scar_outlines.sqlite")
    stamp = json.dumps(_mtimes([f[1] for f in FILES]))
    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS g (src INTEGER, event_id TEXT, geom TEXT, PRIMARY KEY (src, event_id))")
    con.execute("CREATE TABLE IF NOT EXISTS meta (stamp TEXT)")
    row = con.execute("SELECT stamp FROM meta").fetchone()
    if (row and row[0] == stamp) or _geo_lock.locked():
        return con
    with _geo_lock:
        con.execute("DELETE FROM g")
        for src, (_, p) in enumerate(FILES):
            if not os.path.exists(p):
                continue
            if p.endswith(".geojson"):
                rows = ((src, f["properties"]["event_id"], f["geometry"]) for f in json.load(open(p))["features"])
            else:
                rows = ((src, r["event_id"], json.loads(r["geometry"]))
                        for r in csv.DictReader(open(p, newline="")) if r.get("geometry"))
            con.executemany("INSERT OR REPLACE INTO g VALUES (?,?,?)",
                            ((a, b, json.dumps(_simplify(g))) for a, b, g in rows if g))
        con.execute("DELETE FROM meta")
        con.execute("INSERT INTO meta VALUES (?)", (stamp,))
        con.commit()
    return con


def warm():
    """Build the outline file in the background at startup."""
    import threading
    threading.Thread(target=lambda: _geo_db().close(), daemon=True).start()


def _geom(src, event_id):
    if _geo_lock.locked():   # outline file still being built (~20 s after start): no outline yet, not an error
        return None
    con = _geo_db()
    try:
        r = con.execute("SELECT geom FROM g WHERE src=? AND event_id=?", (src, event_id)).fetchone()
        return json.loads(r[0]) if r else None
    finally:
        con.close()


def _near(g, lat, lon, km=3.0):
    """True when an outline's first vertex is within km of the alert (guards against event id mix-ups)."""
    c = g["coordinates"]
    while isinstance(c[0], list):
        c = c[0]
    return math.hypot((c[0] - lon) * 111 * math.cos(math.radians(lat)), (c[1] - lat) * 111) <= km


def for_points(points, with_geometry=False):
    """Best scar result over an alert's satellite points, or None if no point is in the lookups."""
    idx = _load()
    best, at = None, None
    for p in points:
        lat, lon = round(p["lat"], 3), round(p["lon"], 3)
        d0 = p["acq_utc"][:10]
        d1 = (date.fromisoformat(d0) + timedelta(days=1)).isoformat()   # FSI dates are IST (night passes)
        r = None
        for d in (d0, d1):
            for dl in (0, -0.001, 0.001):          # lookups round coordinates a little differently
                for dn in (0, -0.001, 0.001):
                    r = r or idx.get((d, round(lat + dl, 3), round(lon + dn, 3)))
        if r and (best is None or RANK.get(r.get("scar_found"), 0) > RANK.get(best.get("scar_found"), 0)):
            best, at = r, p
    if not best:
        return None
    num = lambda v: float(v) if v not in (None, "") else None
    st = str(best.get("scar_status") or "")
    found = best.get("scar_found") or "unknown"
    out = {"scar_found": found, "scar_ha": num(best.get("scar_ha")),
           "severity": best.get("severity") or None, "dist_m": num(best.get("dist_m")),
           "pre_date": best.get("pre_date") or None, "post_date": best.get("post_date") or None,
           "event_id": best.get("event_id") or None,
           # provisional: scar seen but not yet confirmed by a later clear image (usually within 5 days).
           "provisional": found in ("yes", "faint") and str(best.get("persist_checked")) != "True",
           # waiting: no clear satellite image since the fire yet (the scar usually shows within 5 days)
           "live_status": "waiting" if st in WAITING else (st or None)}
    if config.DEMO_NOW:   # a replay must not show what images taken after the demo clock found
        today = config.DEMO_NOW[:10]
        if out["post_date"] and out["post_date"] > today:
            out.update(scar_found="unknown", scar_ha=None, severity=None, dist_m=None, pre_date=None,
                       post_date=None, provisional=False, live_status="waiting")
        elif found in ("yes", "faint") and (best.get("check_date") or "") > today:
            out["provisional"] = True
    if with_geometry:
        out["geometry"] = None
        if out["scar_found"] in ("yes", "faint") and out["event_id"]:
            g = _geom(best["_src"], out["event_id"])
            if g and _near(g, at["lat"], at["lon"]):
                out["geometry"] = g
    return out
