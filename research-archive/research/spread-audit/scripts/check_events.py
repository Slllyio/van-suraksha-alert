"""Spread audit: how the learned restart's fire events and forecast steps are built (data only, no models).
1. Event grouping (events_multi.py) links detections over the fire's whole life (single linkage, 1.2 km and 30 h), so the
   set of detections "known" at a step can include clusters that are tied to the fire only through LATER detections.
   Count steps where the known detections split into several groups using only what was known, and next-pass target
   detections that are not within 1.2 km of any known detection.
2. lead_h is the time to the next pass that DETECTED this fire. Count satellite overpasses (any detection anywhere in the
   sanctuary marks a pass) in between that saw nothing of it.
Writes ../results/check_events.json"""
import numpy as np, pandas as pd, json
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
D = '/mnt/project-files/ratapani/spread/data_shared'
v = pd.read_parquet(f'{D}/events_viirs.parquet'); v = v[v.t.dt.month <= 6]
allpass = np.sort(v.overpass.unique())
rows = []
for e, ev in v.groupby('event'):
    ev = ev.sort_values('t'); ev = ev[ev.t <= ev.t.min() + pd.Timedelta(hours=47)]
    passes = sorted(ev.overpass.unique())
    if len(passes) < 2:
        continue
    for k in range(1, len(passes)):
        kn = ev[ev.overpass <= passes[k - 1]]; tg = ev[ev.overpass == passes[k]]
        x, y, th = kn.x.values, kn.y.values, (kn.t - kn.t.min()).dt.total_seconds().values / 3600
        dd = np.hypot(x[:, None] - x[None], y[:, None] - y[None]); dt = np.abs(th[:, None] - th[None])
        A = coo_matrix(((dd <= 1200) & (dt <= 30)).astype(int)); ncomp = connected_components(A, directed=False)[0]
        dmin = np.array([np.hypot(x - a, y - b).min() for a, b in zip(tg.x, tg.y)])
        between = ((allpass > passes[k - 1]) & (allpass < passes[k])).sum()
        lead = (tg.t.min() - kn[kn.overpass == passes[k - 1]].t.max()).total_seconds() / 3600
        rows.append(dict(event=e, k=k, n_known=len(kn), known_groups=ncomp, n_target=len(tg), target_far=int((dmin > 1200).sum()),
                         lead_h=lead, empty_passes_between=int(between)))
r = pd.DataFrame(rows)
r.to_parquet('/mnt/project-files/research/spread-audit/results/check_events_steps.parquet')
out = dict(steps=len(r), fires=int(r.event.nunique()),
           steps_known_split=int((r.known_groups > 1).sum()), share_steps_known_split=round(float((r.known_groups > 1).mean()), 3),
           target_dets=int(r.n_target.sum()), target_far_1200m=int(r.target_far.sum()), share_target_far=round(float(r.target_far.sum() / r.n_target.sum()), 3),
           steps_with_empty_passes_between=int((r.empty_passes_between > 0).sum()),
           by_lead={b: dict(steps=len(g), share_with_empty_pass=round(float((g.empty_passes_between > 0).mean()), 3), median_empty=float(g.empty_passes_between.median()))
                    for b, g in r.groupby(pd.cut(r.lead_h, [0, 3, 9, 18, 72], labels=['<3h', '3-9h', '9-18h', '>18h']).astype(str))})
json.dump(out, open('/mnt/project-files/research/spread-audit/results/check_events.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
