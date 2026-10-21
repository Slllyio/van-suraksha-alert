"""Direction hint from a 30 m Sentinel-2 / Landsat scene that caught the fire burning (Akkshay said yes, 18 Oct 2026, to the
Big fires thread's hand-over; method research/big-fires/README.md sections 15e-15f, scripts/b19b_statewide_direction.py).

Arrow = centre of the burnt patch -> centre of the scene's 30 m hot pixels. Statewide it pointed within 45 deg of where the scar
grew next in 65% of scenes (58-72), against 25% by chance and 47% from VIIRS dots, and most of all early in a fire.
RE-TEST AT ARRIVAL (20 Oct 2026, research/big-fires/results/arrow_at_arrival.md): the scene is online ~16:00-17:00 IST, after
the 13:30 IST VIIRS look. On burning after that, arrow 58% vs VIIRS dots incl. the afternoon look 56% (+2, CI -6 to +11):
live it adds about nothing over the dots.
A hint on the alert card only: it never reshapes any forecast area (leaning the area along the arrow made maps worse).
No clear scene on a burning fire -> no hint. Officials only for now: guards keep searching on all sides.

Same rules as b19b:
  mid-fire scene: Sentinel-2 L2A or Landsat 8/9 C2 L2 (Planetary Computer, no login) taken after the fire's first VIIRS look;
  hot pixels: NDFI = (SWIR2 - NIR) / (SWIR2 + NIR) > 0.5, NIR - red in (-0.05, 0.15), SWIR2 > 0.10 (Landsat also the
    SWIR2/NIR > 2.5 rule); at least 3;
  before-fire scene: same collection, 3-40 days before the first alert, cloud < 40%, >= 70% clear in the window;
  burnt patch: NBR(before) - NBR(mid) >= 0.10, plus hot pixels; only patches touching a hot pixel or within 300 m of a VIIRS
    dot seen before the scene; at least 10 pixels (0.4 ha) at 20 m.
"""
import json, math, os
from datetime import timedelta

import numpy as np

RES, MAX_WIN = 20.0, 12000.0
BANDS = {"s2": dict(red="B04", nir="B8A", swir2="B12"), "ls": dict(red="red", nir="nir08", swir2="swir22")}
COL = {"s2": "sentinel-2-l2a", "ls": "landsat-c2-l2"}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
[os.environ.setdefault(k, os.environ['CURL_CA_BUNDLE']) for k in ('GDAL_CURL_CA_BUNDLE', 'PROJ_CURL_CA_BUNDLE') if os.environ.get('CURL_CA_BUNDLE')]   # rasterio otherwise uses certifi only
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF")


def _read(it, sensor, tr, W, H):
    if sensor == "s2c":                   # same-day scene from Copernicus Data Space
        from . import cdse
        return cdse.read(it, tr, W, H)
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    b = {}
    for k, a in BANDS[sensor].items():
        with rasterio.open(it.assets[a].href) as src, WarpedVRT(src, crs="EPSG:32643", transform=tr, width=W, height=H,
                                                                 resampling=Resampling.bilinear, nodata=0) as v:
            x = v.read(1).astype(np.float32)
        if sensor == "s2":
            off = 1000 if float(it.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
            b[k] = np.where(x > 0, (x - off) / 1e4, np.nan)
        else:
            b[k] = np.where(x > 0, x * 0.0000275 - 0.2, np.nan)
    qa, bad_of = ("qa_pixel", lambda q: (q & (1 << 3) | q & (1 << 4) | q & 1) > 0) if sensor == "ls" else \
                 ("SCL", lambda q: np.isin(q, [0, 1, 3, 8, 9, 10]))
    if qa in it.assets:
        with rasterio.open(it.assets[qa].href) as src, WarpedVRT(src, crs="EPSG:32643", transform=tr, width=W, height=H,
                                                                  resampling=Resampling.nearest, nodata=1 if sensor == "ls" else 0) as v:
            bad = bad_of(v.read(1).astype(np.int64))
        for k in b:
            b[k][bad] = np.nan
    return b


def _hot(mid, sensor):
    with np.errstate(all="ignore"):
        ndfi = (mid["swir2"] - mid["nir"]) / (mid["swir2"] + mid["nir"])
        dnr = mid["nir"] - mid["red"]
        hot = (ndfi > 0.5) & (dnr > -0.05) & (dnr < 0.15) & (mid["swir2"] > 0.10)
        if sensor == "ls":
            hot |= (mid["swir2"] / mid["nir"] > 2.5) & (mid["swir2"] - mid["nir"] > 0.3) & (mid["swir2"] > 0.5)
    return np.nan_to_num(hot).astype(bool)


def _tile(scene_id):
    """MGRS tile of a Sentinel-2 scene id (T43REK); ids differ between Planetary Computer and CDSE, the tile does not."""
    return next((p for p in scene_id.split("_") if len(p) == 6 and p[0] == "T"), scene_id)


def compass(bearing):
    return COMPASS[int((bearing % 360 + 22.5) // 45) % 8]


def arrow(dots, t_end, cat=None, max_scenes=4, debug=False):
    """dots: VIIRS points [(lat, lon, utc datetime)] of one fire. Looks for scenes from the first dot to t_end.
    Returns {status, ...}: status 'found' (with bearing_deg, heading, scene, sensor, scene_utc, hot_px, burnt_ha, arrow_m),
    or 'no_scene', 'no_fire_in_scene', 'no_before_scene', 'too_big'."""
    import planetary_computer as pc, pystac_client
    from pyproj import Transformer
    from rasterio.transform import from_origin
    from scipy import ndimage
    from scipy.spatial import cKDTree
    to43 = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
    try:
        os.getcwd()                       # pystac resolves links against the working folder; a long-running process
    except FileNotFoundError:             # on the network mount can lose it
        os.chdir(os.path.expanduser("~"))
    lat = np.array([d[0] for d in dots]); lon = np.array([d[1] for d in dots]); ts = [d[2] for d in dots]
    x, y = to43(lon, lat)
    x0, x1, y0, y1 = x.min() - 800, x.max() + 800, y.min() - 800, y.max() + 800
    if x1 - x0 > MAX_WIN or y1 - y0 > MAX_WIN:
        return {"status": "too_big"}
    W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
    tr = from_origin(x0, y1, RES, RES)
    rr, cc = np.mgrid[0:H, 0:W]
    Px = np.c_[(x0 + (cc + .5) * RES).ravel(), (y1 - (rr + .5) * RES).ravel()]
    cat = cat or pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    t0 = min(ts)
    pt = {"type": "Point", "coordinates": [float(lon.mean()), float(lat.mean())]}
    items = []
    for sensor in ("s2", "ls"):
        q = {"platform": {"in": ["landsat-8", "landsat-9"]}} if sensor == "ls" else {}
        for it in cat.search(collections=[COL[sensor]], intersects=pt, query=q,
                             datetime=f"{t0:%Y-%m-%dT%H:%M:%SZ}/{t_end:%Y-%m-%dT%H:%M:%SZ}").items():
            if it.datetime > t0:
                items.append((it.datetime, sensor, it))
    from . import cdse
    if cdse.available():                  # scenes Planetary Computer has not got yet (same day): from CDSE
        have = {(i.datetime.strftime("%Y%m%dT%H%M%S"), _tile(i.id)) for _, s, i in items if s == "s2"}
        try:
            for it in cdse.search(pt, t0, t_end):
                if it.datetime > t0 and (it.datetime.strftime("%Y%m%dT%H%M%S"), _tile(it.id)) not in have:
                    items.append((it.datetime, "s2c", it))
        except Exception:
            pass                          # CDSE down: Planetary Computer alone, as before
    if not items:
        return {"status": "no_scene"}
    status = "no_fire_in_scene"
    for when, sensor, it in sorted(items, key=lambda z: z[0], reverse=True)[:max_scenes]:   # newest scene with fire first
        mid = _read(it, sensor, tr, W, H)
        if sensor == "s2c":
            sensor = "s2"                 # same rules and before-fire scenes as Planetary Computer's Sentinel-2
        hot = _hot(mid, sensor)
        if hot.sum() < 3:
            continue
        q = {"eo:cloud_cover": {"lt": 40}}
        if sensor == "ls":
            q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        cands = sorted(cat.search(collections=[COL[sensor]], intersects=pt, query=q,
                                  datetime=f"{t0 - timedelta(days=40):%Y-%m-%d}/{t0 - timedelta(days=3):%Y-%m-%d}").items(),
                       key=lambda i: i.datetime, reverse=True)
        pre = None
        for c in cands[:6]:
            b = _read(c, sensor, tr, W, H)
            if np.isfinite(b["nir"]).mean() >= .7:
                pre = b
                break
        if pre is None:
            status = "no_before_scene"
            continue
        with np.errstate(all="ignore"):
            nbr = lambda b: (b["nir"] - b["swir2"]) / (b["nir"] + b["swir2"])
            dmid = nbr(pre) - nbr(mid)
        BL = (np.isfinite(dmid) & (dmid >= 0.10)) | hot
        before = np.array([t < when for t in ts])
        xy = np.c_[x, y][before] if before.any() else np.c_[x, y]
        lb, nl = ndimage.label(BL)
        if nl:
            lx = lb.ravel()
            d0 = cKDTree(xy).query(Px)[0]
            keep = set(np.unique(lx[hot.ravel() & (lx > 0)])) | set(np.unique(lx[(d0 <= 300) & (lx > 0)]))
            BL = np.isin(lb, list(keep))
        br = BL.ravel()
        if br.sum() < 10:
            continue
        v = Px[hot.ravel()].mean(0) - Px[br].mean(0)
        bearing = math.degrees(math.atan2(v[0], v[1])) % 360      # UTM 43N grid north, within ~1-3 deg of true north in MP
        return {"status": "found", "bearing_deg": round(bearing), "heading": compass(bearing), "scene": it.id,
                "sensor": "Sentinel-2" if sensor == "s2" else "Landsat", "scene_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "hot_px": int(hot.sum()), "burnt_ha": round(float(br.sum()) * RES * RES / 1e4, 1), "arrow_m": round(float(np.hypot(*v))),
                **({"_grid": (tr, W, H), "_burnt": br, "_vec": v, "_cb": Px[br].mean(0)} if debug else {})}
    return {"status": status}


# ---------- in the app: check recent alerts, keep the newest arrow, show it on the officials' card ----------
ON = os.environ.get("FS_DIRECTION", "1") == "1"
LOOK_DAYS, RECHECK_H, SHOW_H, PER_RUN = 3, 6, 72, int(os.environ.get("FS_DIRECTION_PER_RUN", "30"))
def recheck_h():
    """Same-day scenes land ~16:00 IST on CDSE: with it, look again every 2 h, not 6."""
    from . import cdse
    return 2 if cdse.available() else RECHECK_H
NOTE = "Hint only: on past MP fires an arrow like this pointed the right way about 2 times in 3. Keep searching on all sides."


def run_due(now_utc, limit=PER_RUN, ids=None):
    """Check alerts seen by VIIRS in the last 3 days whose last check is 6 h old or more (newest alerts first).
    A 'found' arrow is kept until a newer scene gives a new one. Returns how many were checked."""
    from . import db, firms
    lo, re = firms.iso(now_utc - timedelta(days=LOOK_DAYS)), firms.iso(now_utc - timedelta(hours=recheck_h()))
    with db.tx() as con:
        todo = [r["id"] for r in con.execute(
            """SELECT i.id FROM incidents i LEFT JOIN fire_direction f ON f.incident_id=i.id
               WHERE COALESCE(i.kind,'alert')='alert' AND i.last_seen_utc >= ? AND i.first_seen_utc <= ?
               AND (f.checked_utc IS NULL OR f.checked_utc <= ?)
               AND EXISTS (SELECT 1 FROM detections d WHERE d.incident_id=i.id AND d.instrument='VIIRS' AND d.satellite<>'FSI')
               ORDER BY f.checked_utc IS NOT NULL, i.last_seen_utc DESC LIMIT ?""",
            (lo, firms.iso(now_utc), re, limit))] if ids is None else list(ids)
    cat = None
    for iid in todo:
        with db.tx() as con:
            dots = [(r["lat"], r["lon"], firms.parse_utc(r["acq_utc"])) for r in con.execute(
                """SELECT lat, lon, acq_utc FROM detections WHERE incident_id=? AND instrument='VIIRS' AND satellite<>'FSI'
                   AND acq_utc <= ?""", (iid, firms.iso(now_utc)))]
            old = con.execute("SELECT status, data FROM fire_direction WHERE incident_id=?", (iid,)).fetchone()
        if not dots:
            res = {"status": "no_viirs_yet"}            # MODIS- or FSI-only so far
        else:
            try:
                if cat is None:
                    import planetary_computer as pc, pystac_client
                    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
                res = arrow(dots, now_utc, cat)
            except Exception as e:
                res = {"status": "error", "error": str(e)[:200]}
        if res["status"] != "found" and old and old["status"] == "found":
            res = dict(json.loads(old["data"]), status="found")      # keep the last arrow; only a newer scene replaces it
        with db.tx() as con:
            con.execute("INSERT OR REPLACE INTO fire_direction VALUES (?,?,?,?)",
                        (iid, firms.iso(now_utc), res["status"], json.dumps(res)))
    return len(todo)


def for_incident(con, iid, now_utc):
    """Officials' card: {heading, bearing_deg, sensor, scene_utc, text, note} when a scene of the last 3 days caught this
    fire burning; else None (no hint: nothing is said)."""
    if not ON:
        return None
    r = con.execute("SELECT status, data FROM fire_direction WHERE incident_id=?", (iid,)).fetchone()
    if not r or r["status"] != "found":
        return None
    d = json.loads(r["data"])
    from . import firms
    t = firms.parse_utc(d["scene_utc"])
    if (now_utc - t).total_seconds() > SHOW_H * 3600:
        return None
    ist = t + timedelta(hours=5, minutes=30)
    return {"heading": d["heading"], "bearing_deg": d["bearing_deg"], "sensor": d["sensor"], "scene": d["scene"],
            "scene_utc": d["scene_utc"], "burnt_ha": d["burnt_ha"],
            "text": f"Heading {d['heading']} (from the 30 m {d['sensor']} scene of {ist:%d %b %H:%M} IST)", "note": NOTE}
