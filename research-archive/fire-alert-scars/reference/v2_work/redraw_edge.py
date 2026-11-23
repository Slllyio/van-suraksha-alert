"""v2: redraw v1 outlines that touch the 3 km chip edge on a bigger chip (6 km, then 12 km if still at the edge).
Same method otherwise (alert_scar.py, grow_to_check). Resumable. Out: v2_work/redraw_edge.csv"""
import os, sys, json, csv
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor
os.chdir("/tmp")
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import alert_scar
W = "/mnt/project-files/fire-alert-scars/reference/v2_work/"
fn = W + "redraw_edge.csv"
EDGE = pd.read_csv(W + "edge_v1.csv"); EDGE = EDGE[EDGE.edge]
A = pd.read_csv("/mnt/project-files/fire-alert-scars/out/event_scars.csv", usecols=["event_id", "lat", "lon", "date", "sensor", "radius_m"]).assign(src="firms")
B = pd.read_csv("/mnt/project-files/fire-alert-scars/fsi/fsi_alert_events.csv", usecols=["event_id", "lat", "lon", "date", "sensor", "radius_m"]).assign(src="fsi")
E = EDGE.merge(pd.concat([A, B]).drop_duplicates(["src", "event_id"]), on=["src", "event_id"], suffixes=("_v1", ""))
done = set(pd.read_csv(fn).key) if os.path.exists(fn) else set()
E["key"] = E.src + ":" + E.event_id
E = E[~E.key.isin(done)].sort_values("ha_v1" if "ha_v1" in E else "ha")
def one(r):
    res = dict(key=r["key"], src=r["src"], event_id=r["event_id"], ha_v1=r["ha"])
    for hk in (3.0, 6.0):
        try:
            o = alert_scar.alert_scar(r["lat"], r["lon"], r["date"], "modis" if r["sensor"] == "modis" else "viirs",
                                      radius_m=r["radius_m"] if r["src"] == "fsi" else None, half_km=hk)
        except Exception as e:
            res.update(status="error", error=str(e)[:150]); return res
        res.update(chip_km=2 * hk, status=o.get("status"), scar_ha=o.get("scar_ha"), scar_ha_post=o.get("scar_ha_post"),
                   touches_edge=o.get("touches_chip_edge"), pre_date=o.get("pre_date"), post_date=o.get("post_date"),
                   check_date=o.get("check_date"), geometry=json.dumps(o["geometry"]) if o.get("geometry") else None)
        if not o.get("touches_chip_edge"):
            break
    return res
cols = ["key", "src", "event_id", "ha_v1", "chip_km", "status", "scar_ha", "scar_ha_post", "touches_edge", "pre_date", "post_date", "check_date", "error", "geometry"]
print("todo", len(E), flush=True)
buf = []
def flush():
    global buf
    if buf:   # open, append, close each batch: the shared mount loses rows held in a file left open
        pd.DataFrame(buf).reindex(columns=cols).to_csv(fn, mode="a", header=not os.path.exists(fn), index=False)
        buf = []
with ThreadPoolExecutor(int(os.environ.get("TH", "6"))) as ex:
    for i, res in enumerate(ex.map(one, E.to_dict("records"))):
        buf.append(res)
        if len(buf) >= 20: flush()
        if i % 50 == 0: print(i, len(E), flush=True)
flush()
print("done", flush=True)
