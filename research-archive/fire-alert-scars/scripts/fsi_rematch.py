"""Re-run FSI 2025-26 events (Nov 2025 - 26 Apr 2026, FSI's S-NPP months, whose positions sit a median 250 m from
NASA's) that found no scar at 200 m, with a 400 m search radius. Updates fsi/fsi_alert_events.csv rows in place
(radius_m=400 marks them) and rewrites fsi/fsi_alert_scar_lookup.csv. Usage: python fsi_rematch.py <workers>"""
import sys, json, warnings
from multiprocessing import Pool
import pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import fsi_alerts
from run_all import build_events, COLS

def run(row):
    import alert_scar
    try:
        r = alert_scar.alert_scar(row["latitude"], row["longitude"], row["acq_date"],
                                  "modis" if row["sensor"] == "modis" else "viirs", 1.0, 1.0, radius_m=400)
    except Exception as ex:
        r = dict(status="error", error=str(ex)[:200])
    g = r.pop("geometry", None)
    r["geometry"] = json.dumps(g) if g else None
    return {"event_id": row["event_id"], "n_alerts": row["n_alerts"], "sensors": row["sensors"], **r}

if __name__ == "__main__":
    fn = fsi_alerts.OUT + "fsi_alert_events.csv"
    R = pd.read_csv(fn).drop_duplicates("event_id", keep="last")
    A2, E = build_events(fsi_alerts.load().rename(columns={"fsi_alert_id": "alert_id"}))
    E = E.merge(R[["event_id", "status"]], on="event_id")
    todo = E[(E.acq_date < "2026-04-27") & (E.sensor != "modis") & (E.status == "no_scar_seen")]
    print("events to redo", len(todo), flush=True)
    with Pool(int(sys.argv[1])) as p:
        new = pd.DataFrame(p.map(run, todo.to_dict("records"), chunksize=1)).reindex(columns=COLS)
    print(new.status.value_counts().to_dict())
    R = pd.concat([R[~R.event_id.isin(new.event_id)], new], ignore_index=True)
    R.to_csv(fn, index=False)
    L = A2.merge(R.drop(columns=["geometry", "lat", "lon", "date", "sensor"]), on="event_id", how="left")
    L["scar_found"] = L.status.map({"scar": "yes", "scar_faint": "faint", "no_scar_seen": "none_visible"}).fillna("unknown")
    old = pd.read_csv(fsi_alerts.OUT + "fsi_alert_scar_lookup.csv")
    L = L.rename(columns={"alert_id": "fsi_alert_id", "status": "scar_status"})
    L.to_csv(fsi_alerts.OUT + "fsi_alert_scar_lookup.csv", index=False)
    m = old[["fsi_alert_id", "scar_found"]].merge(L[["fsi_alert_id", "scar_found"]], on="fsi_alert_id", suffixes=("_old", "_new"))
    print("alert rows changed", int((m.scar_found_old != m.scar_found_new).sum()))
    print(pd.crosstab(m.scar_found_old, m.scar_found_new))
