"""Validation sample for all MP: up to 40 forest fire events per forest division (2017-25 fire season),
each with a control point: the same date, 3 km away in a random direction, inside a beat, forest >= 10%,
and no FIRMS alert (any land) within 1.5 km and 30 days. Controls should rarely get a scar.
Writes mp/out/set_sample.csv (kind = fire | control)."""
import sys, glob
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts"); sys.path.insert(0, "/mnt/project-files/field-system/app")
import numpy as np, pandas as pd, geopandas as gpd
from scipy.spatial import cKDTree
from pyproj import Transformer
from run_all import build_events
from landcover import WorldCover
M = "/mnt/project-files/fire-alert-scars/mp/"
TO = Transformer.from_crs(4326, 32643, always_xy=True); FROM = Transformer.from_crs(32643, 4326, always_xy=True)
rng = np.random.default_rng(7)
R = pd.read_csv(M + "alerts/mp_season_beats.csv"); R["acq_time"] = R.acq_time.astype(str).str.zfill(4)
R, E = build_events(R)
B = gpd.read_file("/mnt/project-files/ratapani/beats/mp_beats.geojson")[["Division", "Range", "Beat", "beat_uid", "geometry"]]
P = gpd.sjoin(gpd.GeoDataFrame(E, geometry=gpd.points_from_xy(E.longitude, E.latitude), crs=4326), B, predicate="within", how="left")
P = P[~P.index.duplicated()].drop(columns=["index_right", "geometry"])
wc = WorldCover(3000)
# all FIRMS points in the MP box, any land, all year (to keep controls away from any fire)
A = pd.concat([pd.read_csv(f, usecols=["latitude", "longitude", "acq_date"]) for f in glob.glob("/tmp/firms/*_20*.csv")], ignore_index=True)
A["x"], A["y"] = TO.transform(A.longitude.values, A.latitude.values); A["t"] = pd.to_datetime(A.acq_date).values.astype("datetime64[D]").astype(int)
tree = cKDTree(np.c_[A.x, A.y])
rows = []
for div, g in P.groupby("Division"):
    g = g.sample(frac=1, random_state=1)
    k = 0
    for _, r in g.iterrows():
        if k >= 40: break
        if wc.share(r.latitude, r.longitude, 0.375)[1] < 0.10: continue
        rows.append({**r.to_dict(), "kind": "fire"}); k += 1
        x, y = TO.transform(r.longitude, r.latitude); t0 = np.datetime64(r.acq_date, "D").astype(int)
        for _ in range(12):
            a = rng.uniform(0, 2 * np.pi); cx, cy = x + 3000 * np.cos(a), y + 3000 * np.sin(a)
            near = tree.query_ball_point([cx, cy], 1500)
            if any(abs(A.t.values[j] - t0) <= 30 for j in near): continue
            lo, la = FROM.transform(cx, cy)
            hit = B[B.contains(gpd.points_from_xy([lo], [la])[0])]
            if not len(hit) or wc.share(la, lo, 0.375)[1] < 0.10: continue
            rows.append({**r.to_dict(), "event_id": "C_" + r.event_id, "latitude": la, "longitude": lo, "kind": "control",
                         "Division": hit.Division.iloc[0], "Range": hit.Range.iloc[0], "Beat": hit.Beat.iloc[0], "beat_uid": hit.beat_uid.iloc[0]})
            break
    print(div, k, flush=True)
S = pd.DataFrame(rows)
print(S.kind.value_counts())
S.to_csv(M + "out/set_sample.csv", index=False)
