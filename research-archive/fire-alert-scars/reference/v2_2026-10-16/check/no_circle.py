"""What if burned patches did not have to touch the 200 m circle round an alert?
For the all-MP check sample (fire events and control points 3 km away with no alert within 1.5 km / 30 days), rebuild the
persistent burn mask on the 3 km chip and measure, inside 1 km of the point:
  with_rule  = burned area of patches touching the 200 m circle (v1 rule, before growth)
  no_rule    = burned area of all patches >= 0.5 ha
Around control points every no_rule patch is ground with no alert within 1.5 km / 30 days: either an unalerted burn
or a false patch (shadow, harvest, haze). Out: v2_work/no_circle.csv"""
import os, sys, numpy as np, pandas as pd
from scipy.ndimage import label
from concurrent.futures import ThreadPoolExecutor
os.chdir("/tmp"); sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import alert_scar
D = pd.read_csv("/mnt/project-files/fire-alert-scars/mp/out/set_sample.csv")   # all-MP sample: fires + controls 3 km away
D = D.rename(columns={"kind": "in_kind", "event_id": "in_alert_id", "latitude": "in_latitude", "longitude": "in_longitude",
                      "acq_date": "in_acq_date", "sensor": "in_sensor"})
S = pd.concat([g.sample(min(len(g), 200), random_state=2) for _, g in D.groupby("in_kind")])
def one(r):
    try:
        o = alert_scar.alert_scar(r.in_latitude, r.in_longitude, r.in_acq_date, "modis" if r.in_sensor == "modis" else "viirs",
                                  keep_stack=True, grow_to_check=False)
    except Exception as e:
        return dict(kind=r.in_kind, status="error")
    res = dict(kind=r.in_kind, status=o.get("status"), id=r.in_alert_id)
    if "_burn" not in o:
        return res
    b = o["_burn"]; n = b.shape[0]; yy, xx = np.mgrid[0:n, 0:n]; c = n / 2 - 0.5
    r1 = (xx - c) ** 2 + (yy - c) ** 2 <= (1000 / 20) ** 2
    disk = (xx - c) ** 2 + (yy - c) ** 2 <= (200 / 20) ** 2
    lab, _ = label(b, structure=np.ones((3, 3))); sz = np.bincount(lab.ravel())
    big = np.where(sz * 400 / 1e4 >= 0.5)[0]; big = big[big > 0]
    allp = np.isin(lab, big); hit = np.isin(lab, np.intersect1d(np.unique(lab[disk]), big))
    res.update(no_rule_ha=(allp & r1).sum() * 0.04, with_rule_ha=(hit & r1).sum() * 0.04, n_patches_1km=len(np.unique(lab[r1 & allp])) - (0 if (r1 & allp).any() else 0))
    return res
with ThreadPoolExecutor(4) as ex:
    R = pd.DataFrame(list(ex.map(one, [r for r in S.itertuples()])))
R.to_csv("/mnt/project-files/fire-alert-scars/reference/v2_work/no_circle.csv", index=False)
v = R.dropna(subset=["no_rule_ha"])
print(v.groupby("kind")[["with_rule_ha", "no_rule_ha", "n_patches_1km"]].agg(["mean", "median"]).round(2))
print(v.groupby("kind").apply(lambda g: pd.Series(dict(n=len(g), any_patch=(g.no_rule_ha > 0).mean(), rule_patch=(g.with_rule_ha > 0).mean()))).round(3))
