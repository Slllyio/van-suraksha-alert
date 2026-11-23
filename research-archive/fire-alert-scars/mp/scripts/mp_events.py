"""All-MP fire-season events (15 Feb - 15 Jun, 2017-25) from FIRMS points inside MP beats.
Groups alerts into events like run_all.py (same day, within 1 km), tags beat/range/division,
and keeps events with >= 10% tree+shrub (ESA WorldCover) within 375 m of the seed point, like the field system.
Writes mp/out/mp_events.csv and mp/out/mp_alert_event.csv."""
import sys, os
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts"); sys.path.insert(0, "/mnt/project-files/field-system/app")
import pandas as pd, geopandas as gpd, numpy as np
from run_all import build_events
from landcover import WorldCover
M = "/mnt/project-files/fire-alert-scars/mp/"
os.makedirs(M + "out", exist_ok=True)
R = pd.read_csv(M + "alerts/mp_season_beats.csv")
R["acq_time"] = R.acq_time.astype(str).str.zfill(4)
R, E = build_events(R)
print("alerts", len(R), "events", len(E), flush=True)
B = gpd.read_file("/mnt/project-files/ratapani/beats/mp_beats.geojson")[["beat_uid", "Division", "Range", "Beat", "geometry"]]
P = gpd.GeoDataFrame(E, geometry=gpd.points_from_xy(E.longitude, E.latitude), crs=4326)
P = gpd.sjoin(P, B, predicate="within", how="left")
P = P[~P.index.duplicated()].drop(columns=["index_right", "geometry"])
wc = WorldCover(max_blocks=3000)
P = P.sort_values(["latitude", "longitude"])
fs = []
for k, (la, lo) in enumerate(zip(P.latitude, P.longitude)):
    try:
        fs.append(wc.share(la, lo, 0.375)[1])
    except Exception as ex:
        fs.append(np.nan)
    if k % 5000 == 0:
        print(k, flush=True)
P["forest_share"] = fs
P["forest"] = P.forest_share >= 0.10
P.to_csv(M + "out/mp_events.csv", index=False)
R.to_csv(M + "out/mp_alert_event.csv", index=False)
print(P.forest.mean(), P.groupby("Division").forest.sum().sort_values().tail(20))
