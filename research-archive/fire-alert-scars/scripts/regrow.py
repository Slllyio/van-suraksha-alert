"""Re-run every historic scar with grow_to_check (scar grown into ground that has dropped by the later check
look; Wayback test: added ground darker than its surroundings 86% vs 42% for ground next to the scar that
was not added). Resumable. Out: out/event_scars_grown.csv (event_id, scar_ha_post, scar_ha_grown, geometry_grown)"""
import os, sys, json, csv
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
os.chdir("/tmp")   # pystac calls os.getcwd(); the network mount sometimes loses it
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alert_scar
R = "/mnt/project-files/fire-alert-scars/"
fn = R + os.environ.get("REGROW_OUT", "out/event_scars_grown.csv")
E = pd.read_csv(R + os.environ.get("REGROW_IN", "out/event_scars.csv"))
E = E[(E.status == "scar") & E.check_date.notna()]
done = set(pd.read_csv(fn).event_id) if os.path.exists(fn) else set()
E = E[~E.event_id.isin(done)]
def one(r):
    try:
        o = alert_scar.alert_scar(r["lat"], r["lon"], r["date"], "modis" if r["sensor"] == "modis" else "viirs", radius_m=r.get("radius_m"))
        return dict(event_id=r["event_id"], status=o.get("status"), scar_ha_post=o.get("scar_ha_post", o.get("scar_ha")),
                    scar_ha_grown=o.get("scar_ha"), geometry_grown=json.dumps(o["geometry"]) if o.get("geometry") else None)
    except Exception as e:
        return dict(event_id=r["event_id"], status="error", geometry_grown=None, scar_ha_post=None, scar_ha_grown=None)
cols = ["event_id", "status", "scar_ha_post", "scar_ha_grown", "geometry_grown"]
new = not os.path.exists(fn)
with open(fn, "a", newline="") as f, ThreadPoolExecutor(8) as ex:
    w = csv.DictWriter(f, cols)
    if new: w.writeheader()
    for i, res in enumerate(ex.map(one, E.to_dict("records"))):
        w.writerow(res); f.flush()
        if i % 200 == 0: print(i, len(E), flush=True)
print("done")
