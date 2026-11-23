"""Join per-event scar results (run_all.py) back onto every alert and write the stable lookup.

Outputs (in /mnt/project-files/fire-alert-scars/):
  alert_scar_lookup.csv   one row per FIRMS alert inside Ratapani, keyed by alert identity
                          (latitude, longitude, acq_date, acq_time, sensor) and by event_id
  event_scars.geojson     one scar polygon per fire event (status scar or scar_faint)
"""
import json
import pandas as pd

D = "/mnt/project-files/fire-alert-scars/"
A = pd.read_csv(D + "out/alert_scars.csv", dtype={"acq_time": str, "version": str})
A = A[A.in_aoi]
AE = pd.read_csv(D + "out/alert_event.csv")
E = pd.read_csv(D + "out/event_scars.csv").drop_duplicates("event_id", keep="last")
A = A.merge(AE, on="alert_id", how="left")
ev = E.reindex(columns=["event_id", "status", "scar_ha", "scar_ha_core", "severity", "rdnbr_median", "link_conf", "dist_m",
        "pre_date", "post_date", "gap_days", "pre_sensor", "post_sensor", "check_date", "persist_checked",
        "touches_chip_edge", "n_alerts", "sensors"])
L = A.rename(columns={"status": "map_status", "scar_id": "map_scar_id", "scar_ha": "map_scar_ha",
                      "win_start": "map_win_start", "win_end": "map_win_end", "dist_m": "map_dist_m",
                      "link_conf": "map_link_conf"}).merge(ev, on="event_id", how="left")
L["scar_found"] = L.status.map({"scar": "yes", "scar_faint": "faint", "no_scar_seen": "none_visible"}).fillna("unknown")
L = L.rename(columns={"status": "scar_status", "n_alerts": "event_n_alerts", "sensors": "event_sensors"})
cols = ["alert_id", "event_id", "latitude", "longitude", "acq_date", "acq_time", "sensor", "confidence", "frp",
        "beat_uid", "division", "range", "beat", "scar_found", "scar_status", "scar_ha", "scar_ha_core", "severity",
        "rdnbr_median", "link_conf", "dist_m", "pre_date", "post_date", "gap_days", "pre_sensor", "post_sensor",
        "check_date", "persist_checked", "touches_chip_edge", "event_n_alerts", "event_sensors",
        "map_status", "map_scar_id", "map_scar_ha", "map_win_start", "map_win_end", "map_dist_m", "map_link_conf"]
L[cols].sort_values(["acq_date", "alert_id"]).to_csv(D + "alert_scar_lookup.csv", index=False)

feats = []
for r in E[E.geometry.notna()].itertuples():
    p = {k: (None if pd.isna(v) else v) for k, v in r._asdict().items() if k not in ("Index", "geometry", "error")}
    feats.append({"type": "Feature", "geometry": json.loads(r.geometry), "properties": p})
json.dump({"type": "FeatureCollection", "features": feats}, open(D + "event_scars.geojson", "w"))
print(L.scar_found.value_counts().to_dict(), "events with polygons", len(feats))
