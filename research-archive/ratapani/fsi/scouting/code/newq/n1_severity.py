"""New question 1. Does a February fire damage the forest less than a late-March one? Burn severity (RdNBR, median over the scar,
from the all-MP scar run) by the fortnight the fire started, overall, within division (demeaned), by forest type and by fire size.
Out: out/n1_severity.csv, out/n1_severity_div.csv"""
import os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; os.makedirs(OUT, exist_ok=True)
E = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/mp_events.csv', usecols=['event_id', 'acq_date', 'Division', 'forest', 'frp'])
H = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/scars_mp_hist.csv', usecols=['event_id', 'status', 'scar_ha', 'rdnbr_median', 'severity', 'gap_days', 'post_date', 'pre_date'])
T = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/division_types_final.csv')[['Division', 'dominant', 'sal']]
M = E[E.forest].merge(H[H.status == 'scar'], on='event_id').merge(T, on='Division', how='left')
M = M[M.rdnbr_median.notna()].copy(); M['doy'] = pd.to_datetime(M.acq_date).dt.dayofyear; M['year'] = M.acq_date.str[:4].astype(int)
M['period'] = pd.cut(M.doy, [0, 45, 59, 74, 90, 105, 121, 170], labels=['Jan-14 Feb', '15-28 Feb', '1-15 Mar', '16-31 Mar', '1-15 Apr', '16-30 Apr', 'May-Jun'])
M = M[M.period.notna()]
M['post_gap'] = (pd.to_datetime(M.post_date) - pd.to_datetime(M.acq_date)).dt.days
print('fires with RdNBR', len(M)); print(M.severity.value_counts().to_dict())
print(M.groupby('period', observed=True).post_gap.median())
# within division-year demeaned RdNBR (so a hot division or year does not drive it)
M['rd_dm'] = M.rdnbr_median - M.groupby(['Division', 'year']).rdnbr_median.transform('mean')
g = M.groupby('period', observed=True).agg(fires=('event_id', 'size'), rdnbr_median=('rdnbr_median', 'median'), rdnbr_mean=('rdnbr_median', 'mean'), rdnbr_within_division_year=('rd_dm', 'mean'),
                                           high_severity=('severity', lambda s: (s.isin(['high', 'moderate-high'])).mean()), scar_ha_median=('scar_ha', 'median'), frp_median=('frp', 'median')).reset_index()
print(g.round(3).to_string(index=False))
rows = [g.assign(split='all')]
for by in ('dominant',):
    for k, d in M.groupby(by):
        if len(d) < 500: continue
        h = d.groupby('period', observed=True).agg(fires=('event_id', 'size'), rdnbr_median=('rdnbr_median', 'median'), rdnbr_mean=('rdnbr_median', 'mean'), rdnbr_within_division_year=('rd_dm', 'mean'),
                                                   high_severity=('severity', lambda s: (s.isin(['high', 'moderate-high'])).mean()), scar_ha_median=('scar_ha', 'median'), frp_median=('frp', 'median')).reset_index()
        rows.append(h.assign(split=k))
M['size'] = pd.cut(M.scar_ha, [0, 10, 50, 200, 1e9], labels=['<10 ha', '10-50', '50-200', '200+'])
for k, d in M.groupby('size', observed=True):
    h = d.groupby('period', observed=True).agg(fires=('event_id', 'size'), rdnbr_median=('rdnbr_median', 'median'), rdnbr_mean=('rdnbr_median', 'mean'), rdnbr_within_division_year=('rd_dm', 'mean'),
                                               high_severity=('severity', lambda s: (s.isin(['high', 'moderate-high'])).mean()), scar_ha_median=('scar_ha', 'median'), frp_median=('frp', 'median')).reset_index()
    rows.append(h.assign(split='size ' + str(k)))
R = pd.concat(rows); R.to_csv(OUT + 'n1_severity.csv', index=False)
print(R[R.split != 'all'].round(3).to_string(index=False))
# per division: Feb minus late-March median RdNBR
D = M.groupby(['Division', 'period'], observed=True).rdnbr_median.median().unstack()
D['feb_minus_lateMar'] = D['15-28 Feb'] - D['16-31 Mar']; D['n'] = M.groupby('Division').size(); D.to_csv(OUT + 'n1_severity_div.csv')
print('divisions where Feb fires are milder than late-March fires:', int((D.feb_minus_lateMar < 0).sum()), 'of', int(D.feb_minus_lateMar.notna().sum()))
