"""Run alert_scar.py on every historic Ratapani fire event (alerts on the same day within 1 km = one event).
Resumable: results are appended to out/event_scars.csv and done events are skipped on restart.
Writes out/event_scars.csv (one row per event), out/event_scars.geojson, and adds event_id to out/alert_scars.csv
as out/alert_event.csv.
Usage: python run_all.py <workers>
"""
import os, sys, json, warnings
from multiprocessing import Pool
import numpy as np, pandas as pd
from scipy.spatial import cKDTree

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_chip import TO

OUT = "/mnt/project-files/fire-alert-scars/out/"
COLS = ["event_id", "n_alerts", "sensors", "lat", "lon", "date", "sensor", "radius_m", "n_looks", "status", "pre_date",
        "post_date", "gap_days", "pre_sensor", "post_sensor", "check_date", "persist_checked", "scar_ha_core", "scar_ha", "n_patches",
        "dist_m", "rdnbr_median", "link_conf", "severity", "touches_chip_edge", "disk_burn_px", "error", "geometry"]
SENS_RANK = {"viirs-snpp": 0, "viirs-jpss1": 1, "modis": 2}  # seed each event with a VIIRS point when there is one


def build_events(R):
    R = R.copy()
    R["x"], R["y"] = TO.transform(R.longitude.values, R.latitude.values)
    R["rank"] = R.sensor.map(SENS_RANK)
    R = R.sort_values(["acq_date", "rank", "acq_time"])
    R["event_id"] = None
    for day, g in R.groupby("acq_date"):
        xy = g[["x", "y"]].values
        t = cKDTree(xy)
        eid = np.full(len(g), None, object)
        for i in range(len(g)):
            if eid[i] is not None:
                continue
            nb = [j for j in t.query_ball_point(xy[i], 1000) if eid[j] is None]
            eid[nb] = f"E{day.replace('-', '')}-{i:03d}"
        R.loc[g.index, "event_id"] = eid
    seeds = R.groupby("event_id").head(1)
    n = R.groupby("event_id").size().rename("n_alerts")
    sens = R.groupby("event_id").sensor.agg(lambda s: "+".join(sorted(set(s)))).rename("sensors")
    return R.drop(columns=["x", "y", "rank"]), seeds.set_index("event_id").join(n).join(sens).reset_index()


def run(row):
    import alert_scar
    try:
        r = alert_scar.alert_scar(row["latitude"], row["longitude"], row["acq_date"],
                                  "modis" if row["sensor"] == "modis" else "viirs", row["scan"], row["track"])
    except Exception as ex:
        r = dict(status="error", error=str(ex)[:200])
    g = r.pop("geometry", None)
    r["geometry"] = json.dumps(g) if g else None
    return {"event_id": row["event_id"], "n_alerts": row["n_alerts"], "sensors": row["sensors"], **r}


def main(workers):
    R = pd.read_csv(OUT + "alert_scars.csv")
    R = R[R.in_aoi]
    R, E = build_events(R)
    R[["alert_id", "event_id"]].to_csv(OUT + "alert_event.csv", index=False)
    fn = OUT + "event_scars.csv"
    done = set(pd.read_csv(fn).event_id) if os.path.exists(fn) else set()
    todo = E[~E.event_id.isin(done)].to_dict("records")
    print("events", len(E), "todo", len(todo), flush=True)
    with Pool(workers) as p:
        buf = []
        for i, r in enumerate(p.imap_unordered(run, todo, chunksize=1)):
            buf.append(r)
            if len(buf) >= 50 or i == len(todo) - 1:
                pd.DataFrame(buf).reindex(columns=COLS).to_csv(fn, mode="a", header=not os.path.exists(fn), index=False)
                buf = []
                print(i + 1, flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
