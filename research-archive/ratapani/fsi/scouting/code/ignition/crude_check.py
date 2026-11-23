"""For first-day-of-fire scars that the crude 1 km / 7 day rule calls 'spread', where are the earlier detections?
Usage: python -I crude_check.py <prepdir> <ignition_points.csv> <run_all.csv>"""
import sys
import numpy as np, pandas as pd
from shapely import points
PREP, T, RA = sys.argv[1:4]
S = pd.read_pickle(PREP + "/scars.pkl").set_index("event_id")
D = pd.read_pickle(PREP + "/dets.pkl"); EP = pd.Timestamp(0, tz="UTC")
D["th"] = (D.t - EP) / pd.Timedelta(hours=1); F = D[D.src == "firms"]
E = pd.read_csv(T); A = pd.read_csv(RA).set_index("event_id")
E = E[(E.event_role == "first_day_of_fire")]
rows = []
for _, e in E.iterrows():
    g = S.loc[e.event_id].geometry; t1 = A.loc[e.event_id].t_first
    x0, y0 = A.loc[e.event_id].e0_x, A.loc[e.event_id].e0_y
    m = (F.th < t1 - 1) & (F.th >= t1 - 168) & (np.hypot(F.x - x0, F.y - y0) <= 1000)
    if not m.any():
        rows.append(dict(crude=1)); continue
    f = F[m]
    dist = g.distance(points(f.x.values, f.y.values))
    dt = t1 - f.th.values
    rows.append(dict(crude=e.crude_rule_new, d_scar_min=dist.min(), dt_min=dt.min(),
                     adj48=bool(((dist <= 200) & (dt <= 48)).any())))
R = pd.DataFrame(rows)
s = R[R.crude == 0]
print("first-day scars called spread by the crude rule:", len(s))
print("  an earlier detection within 200 m of the scar and 48 h before:", round(s.adj48.mean(), 3))
print("  nearest earlier detection to scar polygon, m:", s.d_scar_min.describe(percentiles=[.25, .5, .75]).round(0).to_dict())
print("  hours since the most recent earlier detection:", s.dt_min.describe(percentiles=[.25, .5, .75]).round(1).to_dict())
