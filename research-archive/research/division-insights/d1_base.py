# Base table: MP forest fire events 2017-25 (15 Feb-15 Jun, same day within 1 km = one event; burn-scar thread's mp_events)
# plus each event's scar (scars_mp_hist) and simple per-event features. Writes events.parquet.
import numpy as np, pandas as pd
from pathlib import Path
O = Path("/mnt/project-files/fire-alert-scars/mp/out"); D = Path(__file__).parent
e = pd.read_csv(O / "mp_events.csv", usecols=["event_id", "latitude", "longitude", "acq_date", "acq_time", "satellite", "daynight",
                                             "frp", "x", "y", "n_alerts", "sensors", "beat_uid", "Division", "Range", "Beat", "forest"])
e = e[e.forest.astype(str) == "True"].copy()
e["date"] = pd.to_datetime(e.acq_date); e["year"] = e.date.dt.year; e["doy"] = e.date.dt.dayofyear
h = pd.read_csv(O / "scars_mp_hist.csv", usecols=["event_id", "status", "scar_ha", "scar_ha_core"])
e = e.merge(h, on="event_id", how="left")
e["has_snpp"] = e.sensors.str.contains("viirs-snpp")
# 1 km cell
e["cx"], e["cy"] = (e.x // 1000).astype(int), (e.y // 1000).astype(int)
e = e.sort_values(["date", "acq_time"]).reset_index(drop=True)
# continuing: another forest event within 1.5 km on the next day (fire still burning or re-lit)
from scipy.spatial import cKDTree
nxt = np.zeros(len(e), bool); prev = np.zeros(len(e), bool)
by = {d: g for d, g in e.groupby("date")}
for d, g in by.items():
    n = by.get(d + pd.Timedelta(days=1)); p = by.get(d - pd.Timedelta(days=1))
    if n is not None:
        nxt[g.index] = np.isfinite(cKDTree(n[["x", "y"]].values).query(g[["x", "y"]].values, distance_upper_bound=1500)[0])
    if p is not None:
        prev[g.index] = np.isfinite(cKDTree(p[["x", "y"]].values).query(g[["x", "y"]].values, distance_upper_bound=1500)[0])
e["next_day"], e["prev_day"] = nxt, prev
e["new_start"] = ~e.prev_day
e.to_parquet(D / "events.parquet")
print(len(e), e.year.value_counts().sort_index().to_dict())
print("continuing next day", e.next_day.mean().round(3), "scar status", e.status.value_counts().to_dict())
