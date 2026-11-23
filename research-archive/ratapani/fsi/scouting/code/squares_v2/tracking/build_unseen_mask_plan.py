"""Pass list for the VIIRS fire-mask pull over the spread thread's unseen fires that the tracking plan does not cover
(ratapani/spread/unseen_validation/unseen_fires_not_in_mask_plan.csv, 472 fires).

Same columns as results/fire_mask_pull_plan.csv. Box = the fire's alert extent + 1.5 km. Time = first alert - 36 h to
last alert + 36 h (the tracking plan starts ~1.5 days before the first alert). Passes come from CMR (metadata only):
every VNP14IMG / VJ114IMG / VJ214IMG granule touching the box in that window; granules of one satellite < 15 min apart
are one pass. flagged = that satellite has an alert of this fire within 10 min of the pass.
pass_key = sensor|U<first granule start yyyymmddHHMM>|f<fire> (one crop per fire, so fires far apart never share a window).
Output: results/fire_mask_pull_plan_unseen.csv
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pull_fire_masks import cmr_granules, FIRE

HERE = os.path.dirname(os.path.abspath(__file__))
PF = '/mnt/project-files'
SAT = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}
A = pd.read_csv(f'{PF}/research/big-fires/results/fire_alerts.csv', usecols=['fire', 'sat', 't', 'latitude', 'longitude'], parse_dates=['t'])
U = pd.read_csv(f'{PF}/ratapani/spread/unseen_validation/unseen_fires_not_in_mask_plan.csv')
A = A[A.fire.isin(U.fire)]


def one(fire):
    g = A[A.fire == fire]; lat = g.latitude.mean()
    dy = 1.5 / 111.0; dx = 1.5 / (111.0 * np.cos(np.radians(lat)))
    box = (g.longitude.min() - dx, g.latitude.min() - dy, g.longitude.max() + dx, g.latitude.max() + dy)
    t0, t1 = g.t.min() - pd.Timedelta(hours=36), g.t.max() + pd.Timedelta(hours=36)
    s = requests.Session(); rows = []
    for sensor, prod in FIRE.items():
        gr = cmr_granules(s, prod, t0, t1, box)
        if not gr: continue
        st = pd.Series([x['start'] for x in gr]).sort_values().reset_index(drop=True)
        grp = (st.diff().dt.total_seconds().fillna(1e9) > 900).cumsum()
        va = g[g.sat.map(SAT) == sensor].t
        for _, ss in st.groupby(grp):
            t = ss.iloc[0] + (ss.iloc[-1] - ss.iloc[0]) / 2 + pd.Timedelta(minutes=3)
            rows.append(dict(fire=fire, photo=False, big=False, pass_key=f'{sensor}|U{ss.iloc[0]:%Y%m%d%H%M}|f{fire}', sensor=sensor,
                             daynight='D' if 4 <= (t + pd.Timedelta(hours=5.5)).hour < 18 else 'N', t_utc=t,
                             flagged=bool(((va - t).abs() < pd.Timedelta(minutes=10)).any()),
                             lon0=box[0], lat0=box[1], lon1=box[2], lat1=box[3]))
    return rows


with ThreadPoolExecutor(8) as ex:
    R = [r for rs in ex.map(one, sorted(A.fire.unique())) for r in rs]
R = pd.DataFrame(R)
R.to_csv(f'{HERE}/results/fire_mask_pull_plan_unseen.csv', index=False)
print(len(R), 'passes on', R.fire.nunique(), 'fires;', R.flagged.sum(), 'flagged;', R.sensor.value_counts().to_dict())
