"""Run alert_scar on a set of all-MP events (resumable, threads). Same method as Ratapani (grow_to_check on).
Usage: python mp_run.py <set_csv> <out_csv> [threads]
set_csv needs event_id, latitude, longitude, acq_date, sensor, scan, track."""
import os, sys, json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
os.chdir("/tmp")
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import alert_scar
import shapely
from shapely.geometry import shape
from pyproj import Transformer
_T = Transformer.from_crs(4326, 32643, always_xy=True)
_B = Transformer.from_crs(32643, 4326, always_xy=True)


def slim(g):
    """Outline as WKT, simplified 10 m in UTM and rounded to 1e-5 deg (~1 m): ~10x smaller, area within 1%."""
    u = shapely.transform(shape(g), lambda xy: __import__("numpy").column_stack(_T.transform(xy[:, 0], xy[:, 1])))
    w = shapely.transform(u.simplify(10), lambda xy: __import__("numpy").column_stack(_B.transform(xy[:, 0], xy[:, 1])))
    return shapely.to_wkt(shapely.set_precision(w, 1e-5), rounding_precision=5)
src, fn = sys.argv[1], sys.argv[2]
th = int(sys.argv[3]) if len(sys.argv) > 3 else 8
E = pd.read_csv(src)
done = set(pd.read_csv(fn).event_id) if os.path.exists(fn) else set()
E = E[~E.event_id.isin(done)]
cols = ["event_id", "status", "pre_date", "post_date", "gap_days", "check_date", "scar_ha_core", "scar_ha_post", "scar_ha",
        "n_patches", "dist_m", "rdnbr_median", "severity", "touches_chip_edge", "chip_km", "grew_into_large_burn", "error", "geometry"]
def one(r):
    try:
        o = alert_scar.alert_scar(r["latitude"], r["longitude"], r["acq_date"], "modis" if r["sensor"] == "modis" else "viirs",
                                  r.get("scan", 1.0), r.get("track", 1.0))
        g = o.pop("geometry", None)
        o["geometry"] = slim(g) if g else None
    except Exception as e:
        o = dict(status="error", error=str(e)[:200])
    o["event_id"] = r["event_id"]
    return {k: o.get(k) for k in cols}
print("todo", len(E), flush=True)
# stats (no geometry) go to out_csv; outlines go to <out>_geom/ as one small gzip file per batch, written to a
# temp name and renamed, so a killed run or a mount outage never leaves a half-written outline file behind
# (18 Oct: the old single appended file got a corrupt member). The outline file is written first: if it
# fails neither is written and those events are simply redone on the next run. Read with read_geom.read_hist_geom.
gdir = fn.replace(".csv", "_geom")
os.makedirs(gdir, exist_ok=True)
buf = []
def flush():
    global buf
    if buf:
        B = pd.DataFrame(buf).reindex(columns=cols)
        name = f"{gdir}/{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M%S%f}_{B.event_id.iloc[0]}.csv.gz"
        try:
            B[["event_id", "geometry"]].dropna().to_csv(name + ".tmp", index=False, compression="gzip")
            os.replace(name + ".tmp", name)
            B.drop(columns="geometry").to_csv(fn, mode="a", header=not os.path.exists(fn), index=False)
        except OSError as e:
            print("write failed, batch will be redone next run:", e, flush=True)
        buf = []
with ThreadPoolExecutor(th) as ex:
    for i, res in enumerate(ex.map(one, E.to_dict("records"))):
        buf.append(res)
        if len(buf) >= 50: flush()
        if i % 100 == 0: print(i, len(E), flush=True)
flush()
print("done", flush=True)
