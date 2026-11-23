"""Does a wider search around the alert (block edge + ~250 m) find more scars, and at what false-alarm cost?
Same points, same imagery (cached per point), radii 200 m (current), 450 m, and block half-diagonal + 250 m."""
import sys, json, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
OUT = sys.argv[1]

def run(r):
    import alert_scar as A
    cache = {}
    orig = A.look
    def look(items, sensor, tr, n):
        k = (tuple(sorted(i.id for i in items)), sensor)
        if k not in cache:
            cache[k] = orig(items, sensor, tr, n)
        return cache[k]
    A.look = look
    edge = 0.5 * np.hypot(r["scan"], r["track"]) * 1000 + 250
    res = dict(event_id=r["event_id"], kind=r["kind"], acq_date=r["acq_date"], Division=r["Division"], scan=r["scan"], edge_r=round(edge))
    for name, rad in (("r200", 200), ("r450", 450), ("redge", edge)):
        try:
            o = A.alert_scar(r["latitude"], r["longitude"], r["acq_date"], "viirs", r["scan"], r["track"], radius_m=rad, auto_expand=False)
        except Exception as ex:
            o = dict(status="error")
        res[name + "_status"] = o.get("status")
        res[name + "_ha"] = o.get("scar_ha")
        res[name + "_dist"] = o.get("dist_m")
        res[name + "_patches"] = o.get("n_patches")
    return res

if __name__ == "__main__":
    s = pd.read_csv("/mnt/project-files/fire-alert-scars/mp/out/set_sample.csv")
    f = s[(s.kind == "fire") & s.sensor.str.startswith("viirs")].sample(250, random_state=7)
    c = s[s.kind != "fire"].sample(250, random_state=7).copy()
    jobs = pd.concat([f, c]).sample(frac=1, random_state=1).to_dict("records")
    rows = []
    with Pool(int(sys.argv[2])) as p:
        for i, x in enumerate(p.imap_unordered(run, jobs)):
            rows.append(x)
            if i % 25 == 0:
                pd.DataFrame(rows).to_csv(OUT, index=False); print(i, flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False); print("done")
