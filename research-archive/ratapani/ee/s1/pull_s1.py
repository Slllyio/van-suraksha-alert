"""Sentinel-1 GRD (IW, VV+VH, dB) mean backscatter per 500 m grid cell per acquisition over Ratapani,
Dec-Jun seasons 2017..2026 -> E:\FIRE\ratapani\ee\s1\s1_cells_<season>.csv
Purpose (research thread): date burn scars more tightly than optical windows allow (radar sees through cloud).
Usage: python pull_s1.py 2017 2026
"""
import ee, json, sys, time, pandas as pd
ee.Initialize(project="van-suraksha-alert")
OUT = r"E:\FIRE\ratapani\ee\s1"
gj = json.load(open(r"E:\FIRE\ratapani\grid_500m.geojson"))
props = [(f["properties"]["cell_id"], f["properties"]["x0"], f["properties"]["y0"]) for f in gj["features"]]
c0 = gj["features"][0]["geometry"]["coordinates"][0]
lat0 = sum(p[1] for p in c0[:4]) / 4; lon0 = sum(p[0] for p in c0[:4]) / 4
def grid(up):
    def mk(t):
        t = ee.List(t); x = ee.Number(t.get(1)); y = ee.Number(t.get(2))
        r = ee.Geometry.Rectangle([x, y, x.add(500), y.add(500)], "EPSG:32643", False) if up else \
            ee.Geometry.Rectangle([x, y.subtract(500), x.add(500), y], "EPSG:32643", False)
        return ee.Feature(r, {"cell_id": t.get(0)})
    return ee.FeatureCollection(ee.List([list(p) for p in props]).map(mk))
# pick the y orientation whose cell 0 centroid matches the geojson centroid
best = None
for up in (True, False):
    g = grid(up); c = ee.Feature(g.first()).geometry().centroid(1).coordinates().getInfo()
    d = abs(c[0] - lon0) + abs(c[1] - lat0); print("orientation up=%s centroid %s vs %s d=%.5f" % (up, c, (lon0, lat0), d), flush=True)
    if best is None or d < best[0]: best = (d, up, g)
G = best[2]; print("using up=%s" % best[1], flush=True)
aoi = G.geometry(1).bounds(1)
ic = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi)
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
for y in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    out = rf"{OUT}\s1_cells_{y}.csv"
    col = ic.filterDate(f"{y-1}-12-01", f"{y}-07-01")
    ids = col.aggregate_array("system:index").getInfo()
    meta = col.toList(col.size()).map(lambda im: ee.Image(im).toDictionary(["orbitProperties_pass", "relativeOrbitNumber_start", "system:time_start"])).getInfo()
    print(y, "images", len(ids), flush=True)
    frames = []
    for k, (iid, m) in enumerate(zip(ids, meta)):
        img = ee.Image(f"COPERNICUS/S1_GRD/{iid}").select(["VV", "VH"])
        for attempt in range(4):
            try:
                fc = img.reduceRegions(G, ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True), 20).getInfo(); break
            except Exception as e:
                print("retry", iid, e, flush=True); time.sleep(10 * (attempt + 1))
        rows = [dict(f["properties"]) for f in fc["features"]]
        df = pd.DataFrame(rows)
        if "VV_mean" not in df: continue
        df = df[df.VV_count > 0]
        df["image"] = iid; df["date"] = pd.to_datetime(m["system:time_start"], unit="ms").strftime("%Y-%m-%d")
        df["orbit"] = m.get("orbitProperties_pass"); df["rel_orbit"] = m.get("relativeOrbitNumber_start")
        frames.append(df[["date", "image", "orbit", "rel_orbit", "cell_id", "VV_mean", "VH_mean", "VV_count"]])
        if k % 10 == 0: print(y, k, iid, len(df), flush=True)
    if frames:
        allf = pd.concat(frames); allf.to_csv(out, index=False)
        print("wrote", out, len(allf), "images", allf.image.nunique(), flush=True)
print("S1 DONE", flush=True)
