"""Burn scar for every alert FSI itself sent for the 2025-26 season (FSI portal Fire Point Search exports for
Obedullahganj, Raisen, Sehore and Bhopal; ratapani/fsi/fsi_portal/), with FSI's own beat and compartment.
Resumable. Writes fsi/fsi_alert_events.csv (one row per event) and fsi/fsi_alert_scar_lookup.csv (one row per alert).
Usage: python fsi_alerts.py <workers>
"""
import os, sys, glob, warnings
from multiprocessing import Pool
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_all import build_events, run, COLS

SRC = "/mnt/project-files/ratapani/fsi/fsi_portal/"
OUT = "/mnt/project-files/fire-alert-scars/fsi/"


def load():
    a = pd.concat([pd.read_csv(f) for f in glob.glob(SRC + "fsi_pts_*.csv") + [SRC + "obd_2026.csv"]], ignore_index=True)
    a = a.drop_duplicates(["Fire_Date", "Fire_Time", "Source_Type", "Lat", "Lon"]).reset_index(drop=True)
    a = a.rename(columns={"Lat": "latitude", "Lon": "longitude", "Fire_Date": "acq_date", "Fire_Time": "acq_time"})
    a["sensor"] = a.Source_Type.str.lower().map({"viirs": "viirs-snpp", "modis": "modis"}).fillna("viirs-snpp")
    a["scan"] = a["track"] = 1.0
    a.insert(0, "fsi_alert_id", [f"F{d.replace('-', '')}-{i:05d}" for i, d in enumerate(a.acq_date)])
    return a


def main(workers):
    os.makedirs(OUT, exist_ok=True)
    A = load()
    A2 = A.rename(columns={"fsi_alert_id": "alert_id"})
    A2, E = build_events(A2)
    fn = OUT + "fsi_alert_events.csv"
    done = set(pd.read_csv(fn).event_id) if os.path.exists(fn) else set()
    todo = E[~E.event_id.isin(done)].to_dict("records")
    print("alerts", len(A), "events", len(E), "todo", len(todo), flush=True)
    with Pool(workers) as p:
        buf = []
        for i, r in enumerate(p.imap_unordered(run, todo, chunksize=1)):
            buf.append(r)
            if len(buf) >= 50 or i == len(todo) - 1:
                pd.DataFrame(buf).reindex(columns=COLS).to_csv(fn, mode="a", header=not os.path.exists(fn), index=False)
                buf = []
                print(i + 1, flush=True)
    R = pd.read_csv(fn).drop_duplicates("event_id", keep="last")
    L = A2.merge(R.drop(columns=["geometry", "lat", "lon", "date", "sensor"]), on="event_id", how="left")
    L["scar_found"] = L.status.map({"scar": "yes", "scar_faint": "faint", "no_scar_seen": "none_visible"}).fillna("unknown")
    L.rename(columns={"alert_id": "fsi_alert_id", "status": "scar_status"}).to_csv(OUT + "fsi_alert_scar_lookup.csv", index=False)
    print(L.scar_found.value_counts().to_dict())


if __name__ == "__main__":
    main(int(sys.argv[1]))
