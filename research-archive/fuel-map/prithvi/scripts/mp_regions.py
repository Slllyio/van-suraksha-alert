"""Statewide Prithvi test: pick one 40 km box per division (densest fire area, 2022-25 events after 15 Feb), on the all-MP grid
(EPSG:32643, aligned to 500 m cells and 30 m HLS pixels). Out: scratch mp/regions.json"""
import json, numpy as np, pandas as pd
O = '/mnt/project-files/fire-alert-scars/mp/out/'
DIVS = ['Khandwa', 'Dewas', 'South_Betul', 'South_Chhindwara', 'South_Balaghat', 'Dindori', 'Umaria', 'Chhatarpur', 'Panna_TR', 'Satpura_TR']
cols = ['event_id', 'acq_date', 'x', 'y', 'Division']
e = pd.concat([pd.read_csv(O + 'set_rest_of_mp.csv', usecols=cols), pd.read_csv(O + 'set_tiger_reserves.csv', usecols=cols)])
h = pd.concat([pd.read_csv(O + 'scars_mp_hist.csv', usecols=['event_id', 'status']), pd.read_csv(O + 'scars_tiger_reserves.csv', usecols=['event_id', 'status'])])
e = e.merge(h, on='event_id', how='left'); e['d'] = pd.to_datetime(e.acq_date)
e = e[(e.d.dt.year >= 2022) & (e.d.dt.year <= 2025) & (e.d.dt.dayofyear >= 46)]
SZ = 1344 * 30.0                                          # 40.32 km = 6 x 224 px chips
out = {}
for dv in DIVS:
    d = e[e.Division == dv]
    best = None
    for x0 in np.arange(np.floor(d.x.min() / 5000) * 5000 - SZ, d.x.max(), 2500):
        for y0 in np.arange(np.floor(d.y.min() / 5000) * 5000 - SZ, d.y.max(), 2500):
            m = (e.x >= x0) & (e.x < x0 + SZ) & (e.y >= y0) & (e.y < y0 + SZ)
            n = int(((d.x >= x0) & (d.x < x0 + SZ) & (d.y >= y0) & (d.y < y0 + SZ)).sum())
            if best is None or n > best[0]: best = (n, x0, y0)
    n, x0, y0 = best
    x0 = 399000 + round((x0 - 399000) / 500) * 500; y1 = 2996000 - round((2996000 - (y0 + SZ)) / 500) * 500   # snap to 500 m cells (also on 30 m? no: HLS grid offset handled by reprojection)
    m = (e.x >= x0) & (e.x < x0 + SZ) & (e.y >= y1 - SZ) & (e.y < y1)
    out[dv] = dict(X0=float(x0), Y1=float(y1), W=1344, H=1344, events=int(m.sum()), done=round(float(e[m].status.notna().mean()), 3),
                   divisions=e[m].Division.value_counts().head(3).to_dict())
    print(dv, out[dv], flush=True)
json.dump(out, open('/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad/mp/regions.json', 'w'), indent=1)
