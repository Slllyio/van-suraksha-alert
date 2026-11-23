"""Burn scar for one fire alert, straight from Sentinel-2 L2A + Landsat 8/9 (Microsoft Planetary Computer).

Works for any alert point and date (new alerts as they arrive, or historic ones), anywhere imagery exists.
Reads a small chip (default 3 km x 3 km, 20 m) around the alert for every scene from 30 days before to
40 days after, then:
  pre   = last clear look on or before the alert day (>= 70% of the alert disk clear)
  post  = first clear look after the alert day
  check = a later clear look within 25 days of post (persistence: leaf fall / haze / shadow recover)
A pixel is burned when its NBR drop pre->post beats the chip's median drop (the surroundings) by >= DNBR,
NIR also darkens relative to the surroundings, and the drop still holds at the check look (if one exists).
Because a thermal alert already says a fire happened here, scars down to MIN_HA are kept (the season
detector drops < 2 ha, which removes most real Ratapani fires: FSI's Melghat notes put the median < 3 ha).
The scar is every connected burned patch (>= 0.5 ha) within 200 m of a VIIRS alert point (600 m for MODIS).
Checked on 300 alerts vs 200 control points (eval_chip.py): ~90% of alerts get a scar, 6.5% of controls.

status: scar | no_scar_seen (clear before and after, nothing burned) | waiting (no clear look after yet)
        | no_pre (no clear look before) .
Usage: python alert_scar.py <lat> <lon> <YYYY-MM-DD> [sensor=viirs|modis] [outdir]
"""
import os, sys, json, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.features import shapes
from scipy.ndimage import binary_dilation, label
from shapely.geometry import shape, Point, mapping
from shapely.ops import unary_union
from pyproj import Transformer

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
                  GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE")
CRS, RES = "EPSG:32643", 20.0
P = dict(grow_min=0.05, grow_frac=0.5, faint=0.07, faint_persist=0.04, faint_ha=1.0, dnbr=0.10, dnbr_jan=0.15, dnir=0.005, persist=0.06, min_ha=0.5, half_km=1.5,
         before=30, after=40, max_gap=30, persist_days=25, disk_clear=0.7)
S2_TO_LS = dict(nir=0.955, swir1=0.91, swir2=0.88)  # same scaling as the season detector
BANDS = {"s2": dict(nir="B8A", swir2="B12", qa="SCL"), "ls": dict(nir="nir08", swir2="swir22", qa="qa_pixel")}
_cat = None


def catalog():
    global _cat
    if _cat is None:
        _cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                         modifier=pc.sign_inplace)
    return _cat


def read(href, tr, n, resamp):
    err = None
    for _ in range(4):
        try:
            with rasterio.open(href) as src, WarpedVRT(src, crs=CRS, transform=tr, width=n, height=n,
                                                       resampling=resamp, src_nodata=src.nodata) as v:
                return v.read(1)
        except Exception as e:
            err = e
    raise err


def look(items, sensor, tr, n):
    """One date: mosaic scenes onto the chip; returns nbr, nir (Landsat scale) and clear mask."""
    b = BANDS[sensor]
    nbr = np.full((n, n), np.nan, np.float32)
    nir_o = np.full((n, n), np.nan, np.float32)
    for it in items:
        qa = read(it.assets[b["qa"]].href, tr, n, Resampling.nearest)
        if sensor == "s2":
            ok = np.isin(qa, [2, 3, 4, 5, 6, 7]) & ~binary_dilation(np.isin(qa, [8, 9, 10]), iterations=25)
        else:
            cl = (qa & (1 << 1) > 0) | (qa & (1 << 3) > 0) | (qa & (1 << 4) > 0)
            ok = (qa > 0) & (qa & 1 == 0) & ~binary_dilation(cl, iterations=17)
        ok &= np.isnan(nbr)
        if not ok.any():
            continue
        r = {}
        for k in ("nir", "swir2"):
            a = read(it.assets[b[k]].href, tr, n, Resampling.bilinear).astype(np.float32)
            if sensor == "s2":
                off = 1000 if float(it.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
                r[k] = (a - off) / 10000.0 * S2_TO_LS[k]
            else:
                r[k] = a * 0.0000275 - 0.2
        s = r["nir"] + r["swir2"]
        ok &= s > 0.02
        nbr[ok] = ((r["nir"] - r["swir2"]) / s)[ok]
        nir_o[ok] = r["nir"][ok]
    return nbr, nir_o


def rel(x, ok):
    """Change relative to the chip's surroundings (median of clear pixels)."""
    return x - np.nanmedian(x[ok]) if ok.sum() > 200 else np.full_like(x, np.nan)


def _alert_scar(lat, lon, date, sensor="viirs", scan=1.0, track=1.0, keep_stack=False, radius_m=None, grow_to_check=True, half_km=None):
    d = dt.date.fromisoformat(str(date)[:10])
    scan = 1.0 if scan is None or not np.isfinite(scan) else scan
    track = 1.0 if track is None or not np.isfinite(track) else track
    x, y = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(lon, lat)
    half = (half_km or P["half_km"]) * 1000   # v2: outlines touching the chip edge are redrawn on a bigger chip
    x0, y1 = np.floor((x - half) / RES) * RES, np.ceil((y + half) / RES) * RES  # snap to the season grid's 20 m
    n = int(2 * half / RES)
    tr = rasterio.transform.from_origin(x0, y1, RES, RES)
    # search radius from the control test (eval_chip.py): VIIRS scars within 200 m of the alert point are
    # found for ~90% of alerts but only 6.5% of control points; MODIS pixels are 1 km, so 600 m
    radius = 600.0 * max(scan, track, 1) ** 0.5 if sensor == "modis" else 200.0
    if radius_m:  # e.g. FSI S-NPP points sit ~250 m from NASA's (Nov 2025 - Apr 2026)
        radius = float(radius_m)
    yy, xx = np.mgrid[0:n, 0:n]
    cx, cy = (x - x0) / RES - 0.5, (y1 - y) / RES - 0.5
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= (radius / RES) ** 2
    out = dict(lat=lat, lon=lon, date=d.isoformat(), sensor=sensor, radius_m=round(radius))

    bbox = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform_bounds(x0, y1 - n * RES, x0 + n * RES, y1)
    rng = f"{d - dt.timedelta(P['before'])}/{d + dt.timedelta(P['after'])}"
    groups = {}
    for col, s in (("sentinel-2-l2a", "s2"), ("landsat-c2-l2", "ls")):
        q = {"eo:cloud_cover": {"lt": 80}}
        if s == "ls":
            q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        for it in catalog().search(collections=[col], bbox=bbox, datetime=rng, query=q).items():
            groups.setdefault((it.datetime.date(), s), []).append(it)
    keys = sorted(groups)
    with ThreadPoolExecutor(8) as ex:
        stack = list(ex.map(lambda k: look(groups[k], k[1], tr, n), keys))
    # one look per date: keep the clearer one over the disk
    looks = {}
    for (dd, s), (nb, ni) in zip(keys, stack):
        c = (~np.isnan(nb))[disk].mean()
        if c > 0 and (dd not in looks or c > looks[dd][2]):
            looks[dd] = (nb, ni, c, s)
    dates = sorted(looks)
    good = [t for t in dates if looks[t][2] >= P["disk_clear"]]
    pre = [t for t in good if t <= d and (d - t).days <= P["max_gap"]]
    post = [t for t in good if t > d]
    out["n_looks"] = len(dates)
    if not pre:
        out["status"] = "no_pre"
        return out
    if not post:
        out["status"] = "waiting"
        out["pre_date"] = pre[-1].isoformat()
        return out
    t0, t1 = pre[-1], post[0]
    later = [t for t in good if t1 < t <= t1 + dt.timedelta(P["persist_days"])]
    nb0, ni0 = looks[t0][:2]
    nb1, ni1 = looks[t1][:2]
    ok = ~np.isnan(nb0) & ~np.isnan(nb1)
    rdn = rel(nb0 - nb1, ok)
    rdr = rel(ni0 - ni1, ok)
    thr = P["dnbr_jan"] if d.month == 1 else P["dnbr"]
    burn = ok & (rdn >= thr) & (rdr >= P["dnir"])
    persist_checked = False
    rdf = np.zeros_like(rdn)
    ok2 = np.zeros_like(ok)
    if later:
        nb2 = looks[later[0]][0]
        ok2 = ~np.isnan(nb0) & ~np.isnan(nb2)
        rdf = rel(nb0 - nb2, ok2)
        burn &= ~ok2 | (rdf >= P["persist"])
        persist_checked = True
    lab, _ = label(burn, structure=np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())
    big = np.where(sizes * RES * RES / 1e4 >= P["min_ha"])[0]
    big = big[big > 0]
    hit = np.intersect1d(np.unique(lab[disk]), big)
    out.update(pre_date=t0.isoformat(), post_date=t1.isoformat(), gap_days=(t1 - t0).days,
               pre_sensor=looks[t0][3], post_sensor=looks[t1][3],
               check_date=later[0].isoformat() if later else None, persist_checked=persist_checked)
    status, conf = "scar", None
    if len(hit):
        # pass 2 (FireCCI-style): learn this fire's own drop from the core and grow the scar into
        # connected pixels that drop at least half as much (edges and lightly burned litter)
        core = np.isin(lab, hit)
        thr2 = max(P["grow_min"], P["grow_frac"] * float(np.median(rdn[core])))
        grow = ok & (rdn >= thr2) & (rdr >= 0) & (~ok2 | (rdf >= thr2 / 2)) | core
        glab, _ = label(grow, structure=np.ones((3, 3)))
        m = np.isin(glab, np.unique(glab[core]))
        out["scar_ha_core"] = round(core.sum() * RES * RES / 1e4, 2)
    else:
        # faint scar: a weaker but persistent drop, accepted only because a thermal alert sits on it
        faint = ok & (rdn >= P["faint"]) & (rdr >= 0) & (~ok2 | (rdf >= P["faint_persist"]))
        flab, _ = label(faint, structure=np.ones((3, 3)))
        fs = np.bincount(flab.ravel())
        fbig = np.where(fs * RES * RES / 1e4 >= P["faint_ha"])[0]
        hit = np.intersect1d(np.unique(flab[disk]), fbig[fbig > 0])
        if not len(hit):
            out["status"] = "no_scar_seen"
            out["disk_burn_px"] = int((burn & disk).sum())
            if keep_stack:
                out["_tr"], out["_burn"] = tr, burn
            return out
        m = np.isin(flab, hit)
        status, conf = "scar_faint", "low"
        out["scar_ha_core"] = 0.0
    if grow_to_check and status == "scar" and ok2.any():
        # the fire may still be spreading at post_date: grow into ground that has
        # dropped by the later check look as much as pass 2 asks, connected to the scar
        g2 = ok2 & (rdf >= thr2) | m
        g2lab, _ = label(g2, structure=np.ones((3, 3)))
        mg = np.isin(g2lab, np.unique(g2lab[m]))
        out["scar_ha_post"] = round(m.sum() * RES * RES / 1e4, 2)
        m = mg
    geom = unary_union([shape(g) for g, v in shapes(m.astype(np.uint8), m, transform=tr) if v])
    to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    from shapely.ops import transform as stx
    sev = rdn[m]
    out.update(status=status, scar_ha=round(m.sum() * RES * RES / 1e4, 2), n_patches=int(len(hit)),
               dist_m=round(geom.distance(Point(x, y))), rdnbr_median=round(float(np.median(sev)), 3),
               link_conf=conf or ("high" if geom.distance(Point(x, y)) <= 100 else "medium"),
               severity=("low" if np.median(sev) < 0.27 else "moderate" if np.median(sev) < 0.44 else "high"),
               touches_chip_edge=bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any()),
               geometry=mapping(stx(lambda a, b: to_ll.transform(a, b), geom.simplify(10))))
    if keep_stack:
        out["_mask"], out["_tr"], out["_burn"] = m, tr, burn
    return out


def alert_scar(lat, lon, date, sensor="viirs", scan=1.0, track=1.0, keep_stack=False, radius_m=None, grow_to_check=True,
               half_km=None, auto_expand=True):
    """As _alert_scar, but an outline that touches the 3 km chip edge is redrawn on a 6 km, then 12 km chip
    (v2, 16 Oct: 38% of v1 outlines were cut at the edge). A bigger chip can take in a neighbouring fire that burned
    in the same image gap, so a redraw more than 3x the 3 km outline is not used: the 3 km one is kept, flagged
    grew_into_large_burn."""
    o = _alert_scar(lat, lon, date, sensor, scan, track, keep_stack, radius_m, grow_to_check, half_km)
    if not auto_expand or half_km or not o.get("touches_chip_edge"):
        return o
    base = o
    for hk in (3.0, 6.0):
        o2 = _alert_scar(lat, lon, date, sensor, scan, track, keep_stack, radius_m, grow_to_check, hk)
        if o2.get("status") != base.get("status") or not o2.get("scar_ha"):
            break
        if o2["scar_ha"] > 3 * base["scar_ha"]:
            base["grew_into_large_burn"] = True
            break
        o2["chip_km"] = 2 * hk
        o = o2
        if not o2.get("touches_chip_edge"):
            break
    return o


if __name__ == "__main__":
    lat, lon, date = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    sensor = sys.argv[4] if len(sys.argv) > 4 else "viirs"
    r = alert_scar(lat, lon, date, sensor)
    g = r.pop("geometry", None)
    print(json.dumps(r, indent=1))
    if g and len(sys.argv) > 5:
        os.makedirs(sys.argv[5], exist_ok=True)
        fn = os.path.join(sys.argv[5], f"scar_{date}_{lat:.4f}_{lon:.4f}.geojson")
        json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": r, "geometry": g}]},
                  open(fn, "w"))
        print("wrote", fn)
