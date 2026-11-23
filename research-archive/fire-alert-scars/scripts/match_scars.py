"""Link every satellite fire alert over Ratapani (FIRMS MODIS + VIIRS S-NPP / NOAA-20 / NOAA-21,
the same detections FSI forwards) to the burn scar it left, using the season scar rasters built by
the research thread (research/ratapani-burn-labels/rasters, 20 m, scars >= 2 ha).

An alert on day d matches scar pixels whose burn window (start, end] can hold d (start <= d, end >= d-1)
and that lie within the alert's footprint plus geolocation slack (VIIRS: 375 m pixel grown by scan/track,
MODIS: 1 km pixel grown by scan/track). The scar reported is the full connected patch (8-neighbour) of
date-compatible scar pixels touching that search disk, so a fire that ran beyond the alert pixel is kept whole.

Every alert gets a status:
  scar            a scar was found
  no_scar_seen    no scar, but the spot was seen clear both before (<=20 d) and after (<=25 d) the alert:
                  the fire left < 2 ha of visible scar, burned under the canopy, or was not a forest fire
  no_scar_cloud   no scar and no usable clear look before/after: can't tell
  not_forest      alert pixel is mostly crop/built/water (WorldCover), outside the detector's mask
  outside_aoi     alert centre is outside the Ratapani boundary
  no_scar_season  alert date outside Jan 1 - Jun 20, when scars are not dated

Usage: python match_scars.py   (writes out/alert_scars.csv, out/scars.geojson, out/summary.json)
"""
import os, sys, glob, json, datetime as dt
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import shapes
from scipy.ndimage import label
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from pyproj import Transformer

P = "/mnt/project-files/"
LAB = P + "research/ratapani-burn-labels/"
OUT = os.environ.get("SCAR_OUT", P + "fire-alert-scars/out/")
ALERTS = os.environ.get("SCAR_ALERTS", P + "fire-alert-scars/alerts/")
sys.path.insert(0, LAB + "scripts")
import fetch  # grid (TR, INSIDE) shared with the detector

SLACK_M = 375  # geolocation slack beyond the pixel half-width
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def load_alerts():
    fr = []
    for f in sorted(glob.glob(ALERTS + "*.csv")):
        a = pd.read_csv(f, dtype={"acq_time": str, "confidence": str})
        if not len(a):
            continue
        a["sensor"] = os.path.basename(f).split("_")[0]
        # *_2026.csv came from Earth Engine LANCE rasters (Dec 2025 - Jun 2026, no scan/track); the FIRMS
        # yearly 2025 files already hold December 2025, so keep only 2026 dates from them
        if f.endswith("_2026.csv"):
            a = a[a.acq_date >= "2026-01-01"]
        fr.append(a)
    a = pd.concat(fr, ignore_index=True)
    a = a.drop_duplicates(["latitude", "longitude", "acq_date", "acq_time", "sensor"])
    a["date"] = pd.to_datetime(a.acq_date)
    # low-confidence detections are kept but flagged; FSI forwards nominal/high VIIRS and MODIS >= 30
    c = a.confidence.astype(str).str.lower()
    a["conf_ok"] = np.where(a.sensor == "modis", pd.to_numeric(c, errors="coerce") >= 30, c != "l")
    a["x"], a["y"] = TO_UTM.transform(a.longitude.values, a.latitude.values)
    pix = np.where(a.sensor == "modis", 1000.0, 375.0)
    a["radius_m"] = pix / 2 * np.maximum(a.scan, a.track).fillna(1).clip(lower=1) + SLACK_M
    a["season"] = a.date.dt.year
    a = a.sort_values(["date", "acq_time", "sensor"]).reset_index(drop=True)
    a.insert(0, "alert_id", [f"R{d:%Y%m%d}-{i:05d}" for i, d in enumerate(a.date)])
    return a


def clear_lookup():
    c = pd.read_parquet(LAB + "clear_calendar.parquet")
    c = c[c.clear_frac >= 0.5]
    c["date"] = pd.to_datetime(c.date)
    return {k: np.sort(g.date.values) for k, g in c.groupby(["season", "cell_id"])}


def tag_beats(R):
    """Division / range / beat of each alert point (MP Forest Department beat outlines)."""
    b = gpd.read_file(P + "ratapani/beats/beats_ratapani.geojson").to_crs(4326)
    b["beat_uid"] = b.DID + "-" + b.RID + "-" + b.BID
    pts = gpd.GeoDataFrame(R[["alert_id"]], geometry=gpd.points_from_xy(R.longitude, R.latitude), crs=4326)
    j = gpd.sjoin(pts, b[["beat_uid", "Division", "Range", "Beat", "geometry"]], how="left", predicate="within")
    j = j.drop_duplicates("alert_id").set_index("alert_id")
    R = R.drop(columns=[c for c in ("beat_uid", "division", "range", "beat") if c in R], errors="ignore")
    for a, c in (("beat_uid", "beat_uid"), ("division", "Division"), ("range", "Range"), ("beat", "Beat")):
        R[a] = R.alert_id.map(j[c])
    return R


def finalize(R, G):
    """Link confidence from the control run (alerts moved 3 km, same dates): a scar within 100 m of the
    alert is 3.3% likely by chance vs 52% for real alerts (~83% of links causal); 100-300 m about half;
    beyond 300 m real alerts match no more often than controls, so those links are dropped."""
    far = (R.status == "scar") & (R.dist_m > 300)
    R.loc[far, "status"] = "no_scar_seen"
    R.loc[far, ["scar_id", "scar_ha", "win_start", "win_end", "dist_m"]] = np.nan
    R["link_conf"] = np.where(R.status != "scar", None, np.where(R.dist_m <= 100, "high", "medium"))
    n = R[R.status == "scar"].scar_id.value_counts()
    G = G[G.scar_id.isin(n.index)].copy()
    G["n_alerts"] = G.scar_id.map(n).astype(int)
    return R, G


def main():
    os.makedirs(OUT, exist_ok=True)
    A = load_alerts()
    aoi = gpd.read_file(P + "ratapani/ratapani_aoi.geojson").to_crs(32643).union_all()
    A["in_aoi"] = [aoi.contains(Point(x, y)) for x, y in zip(A.x, A.y)]
    grid = gpd.read_file(P + "ratapani/grid_500m.geojson").to_crs(32643)
    gi = gpd.sjoin(gpd.GeoDataFrame(A[["alert_id"]], geometry=gpd.points_from_xy(A.x, A.y), crs=32643),
                   grid[["cell_id", "geometry"]], how="left", predicate="within")
    A["cell_id"] = gi.drop_duplicates("alert_id").cell_id.values
    lc_full = np.zeros(fetch.INSIDE.shape, np.int16)
    lc_full[fetch.INSIDE] = np.load(fetch.WORLDCOVER)
    clear = clear_lookup()
    H, W = fetch.INSIDE.shape
    inv = ~fetch.TR
    rows, scars = [], {}
    for season, S in A.groupby("season"):
        tif = LAB + f"rasters/burn_{season}.tif"
        if not os.path.exists(tif):
            continue
        with rasterio.open(tif) as r:
            end, start = r.read(1).astype(np.int32), r.read(2).astype(np.int32)
        has = end > -999
        d0 = dt.date(season, 1, 1)
        cache = {}
        for a in S.itertuples():
            doy = (a.date.date() - d0).days
            col, row = inv * (a.x, a.y)
            col, row = int(col), int(row)
            rpx = int(np.ceil(a.radius_m / fetch.RES))
            r0, r1, c0, c1 = max(row - rpx, 0), min(row + rpx + 1, H), max(col - rpx, 0), min(col + rpx + 1, W)
            rec = dict(alert_id=a.alert_id, status=None, scar_id=None, scar_ha=np.nan, scar_px_in_disk=0,
                       win_start=None, win_end=None, dist_m=np.nan)
            if not a.in_aoi:
                rec["status"] = "outside_aoi"
            elif not (0 <= doy <= 171):
                rec["status"] = "no_scar_season"
            else:
                yy, xx = np.mgrid[r0:r1, c0:c1]
                disk = (yy - row) ** 2 + (xx - col) ** 2 <= rpx ** 2
                lc = lc_full[r0:r1, c0:c1][disk & fetch.INSIDE[r0:r1, c0:c1]]
                forest = np.isin(lc, (10, 20, 30)).mean() if lc.size else 0
                if doy not in cache:  # date-compatible scar mask and its patches
                    comp = has & (start <= doy) & (end >= doy - 1)
                    lab, _ = label(comp, structure=np.ones((3, 3)))
                    cache[doy] = lab
                lab = cache[doy]
                hit = np.unique(lab[r0:r1, c0:c1][disk])
                hit = hit[hit > 0]
                if len(hit):
                    m = np.isin(lab, hit)
                    key = (season, int(np.flatnonzero(m)[0]), int(m.sum()))
                    if key not in scars:
                        rr, cc = np.where(m)
                        sub = m[rr.min():rr.max() + 1, cc.min():cc.max() + 1]
                        tr = fetch.TR * rasterio.Affine.translation(cc.min(), rr.min())
                        geom = unary_union([shape(g) for g, v in shapes(sub.astype(np.uint8), sub, transform=tr) if v])
                        st, en = start[m], end[m]
                        scars[key] = dict(scar_id=f"S{season}-{len(scars):05d}", season=season, geometry=geom,
                                          ha=round(m.sum() * 0.04, 2),
                                          win_start=(d0 + dt.timedelta(int(np.median(st)))).isoformat(),
                                          win_end=(d0 + dt.timedelta(int(np.median(en)))).isoformat(),
                                          n_alerts=0)
                    s = scars[key]
                    s["n_alerts"] += 1
                    rec.update(status="scar", scar_id=s["scar_id"], scar_ha=s["ha"], win_start=s["win_start"],
                               win_end=s["win_end"], scar_px_in_disk=int(np.isin(lab[r0:r1, c0:c1][disk], hit).sum()),
                               dist_m=round(s["geometry"].distance(Point(a.x, a.y)), 0))
                elif forest < 0.5:
                    rec["status"] = "not_forest"
                else:
                    t = np.datetime64(a.date.date())
                    looks = clear.get((season, a.cell_id), np.array([], "datetime64[ns]")).astype("datetime64[D]")
                    before = looks[(looks <= t) & (looks >= t - np.timedelta64(20, 'D'))]
                    after = looks[(looks > t) & (looks <= t + np.timedelta64(25, 'D'))]
                    rec["status"] = "no_scar_seen" if len(before) and len(after) else "no_scar_cloud"
                rec["forest_frac"] = round(float(forest), 2)
            rows.append(rec)
    R = A.drop(columns=["x", "y"]).merge(pd.DataFrame(rows), on="alert_id", how="left")
    R["status"] = R.status.fillna("no_scar_raster")
    G = gpd.GeoDataFrame([{k: v for k, v in s.items()} for s in scars.values()], geometry="geometry", crs=32643)
    G["geometry"] = G.geometry.simplify(10)
    R, G = finalize(R, G)
    R = tag_beats(R)
    R.to_csv(OUT + "alert_scars.csv", index=False)
    G.to_crs(4326).to_file(OUT + "scars.geojson", driver="GeoJSON")
    print(R.groupby(["sensor"]).status.value_counts().unstack(fill_value=0).to_string())
    return R, G


if __name__ == "__main__":
    main()
