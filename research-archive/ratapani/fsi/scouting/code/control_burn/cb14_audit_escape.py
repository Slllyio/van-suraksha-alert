"""Step 14. (a) Audit from orbit: is a fire that starts in 15-28 Feb seen as a scar at the same rate as a March fire?
(scars_mp_hist status by start fortnight, forest events, and by dominant forest type of the division.)
(b) Escape risk per patch: fires 2017-25 that started inside a tr3 patch in 15-28 Feb: how far they ran outside the patch, against
March starts in the same patches. Out: out/cb14_audit.csv, out/cb14_escape_patches.csv, out/cb14_escape_summary.csv"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
E = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/mp_events.csv', usecols=['event_id', 'acq_date', 'Division', 'forest'])
H = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/scars_mp_hist.csv', usecols=['event_id', 'status', 'scar_ha', 'gap_days'])
T = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/division_types_final.csv')[['Division', 'dominant', 'sal']]
M = E[E.forest].merge(H, on='event_id', how='inner').merge(T, on='Division', how='left')
M['doy'] = pd.to_datetime(M.acq_date).dt.dayofyear
M['period'] = pd.cut(M.doy, [0, 45, 59, 74, 90, 105, 121, 170, 400], labels=['Jan-14 Feb', '15-28 Feb', '1-15 Mar', '16-31 Mar', '1-15 Apr', '16-30 Apr', 'May-Jun', 'Jul+'])
M['seen'] = M.status.isin(['scar', 'scar_faint']); M['clear'] = M.status == 'scar'; M['faint'] = M.status == 'scar_faint'
M['sal_div'] = np.where(M.sal >= 0.3, 'sal >= 30%', np.where(M.sal < 0.1, 'sal < 10%', 'mixed'))
rows = []
for by in (None, 'sal_div', 'dominant'):
    g = M.groupby(['period'] + ([by] if by else []), observed=True).agg(fires=('seen', 'size'), scar_seen=('seen', 'mean'), clear=('clear', 'mean'), faint=('faint', 'mean'), median_scar_ha=('scar_ha', 'median'), median_gap_days=('gap_days', 'median')).reset_index()
    g['split'] = by or 'all'; rows.append(g)
A = pd.concat(rows); A.to_csv(B.OUT + 'cb14_audit.csv', index=False)
print(A[A.split == 'all'].round(3).to_string(index=False)); print(A[A.split == 'sal_div'].round(3).to_string(index=False))
# (b) escapes
F = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j2_fires.csv')
F = F[F.start_patch > 0].copy(); F['doy'] = pd.to_datetime(F.t0).dt.dayofyear
F['out_ha'] = (F.forest_ha - F.in_patch_forest_ha).clip(lower=0)
F['per'] = pd.cut(F.doy, [0, 45, 59, 74, 90, 400], labels=['Jan-14 Feb', '15-28 Feb', '1-15 Mar', '16-31 Mar', 'Apr+'])
s = F.groupby('per', observed=True).agg(fires=('ha', 'size'), median_ha=('forest_ha', 'median'), left_patch_over_10ha=('out_ha', lambda s: (s > 10).mean()), over_50_out=('out_ha', lambda s: (s > 50).mean()),
                                        over_200_out=('out_ha', lambda s: (s > 200).mean()), mean_out_ha=('out_ha', 'mean'), reach_200=('forest_ha', lambda s: (s >= 200).mean())).reset_index()
s.to_csv(B.OUT + 'cb14_escape_summary.csv', index=False); print(s.round(3).to_string(index=False))
P = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j1_patches.csv')[['key', 'patch', 'division', 'forest_ha', 'rank', 'tier', 'cum_ha', 'boundary_km', 'line_km']]
fb = F[F.per == '15-28 Feb'].groupby(['key', 'start_patch']).agg(feb_fires=('ha', 'size'), feb_left_patch=('out_ha', lambda s: int((s > 10).sum())), feb_max_out_ha=('out_ha', 'max'), feb_mean_out_ha=('out_ha', 'mean')).reset_index().rename(columns={'start_patch': 'patch'})
fm = F[F.per.isin(['1-15 Mar', '16-31 Mar'])].groupby(['key', 'start_patch']).agg(mar_fires=('ha', 'size'), mar_max_out_ha=('out_ha', 'max'), mar_mean_out_ha=('out_ha', 'mean')).reset_index().rename(columns={'start_patch': 'patch'})
fa = F.groupby(['key', 'start_patch']).agg(all_fires=('ha', 'size'), all_max_out_ha=('out_ha', 'max'), all_mean_out_ha=('out_ha', 'mean')).reset_index().rename(columns={'start_patch': 'patch'})
P = P.merge(fb, on=['key', 'patch'], how='left').merge(fm, on=['key', 'patch'], how='left').merge(fa, on=['key', 'patch'], how='left').fillna({'feb_fires': 0, 'feb_left_patch': 0, 'feb_max_out_ha': 0, 'feb_mean_out_ha': 0, 'mar_fires': 0, 'mar_max_out_ha': 0, 'mar_mean_out_ha': 0, 'all_fires': 0, 'all_max_out_ha': 0, 'all_mean_out_ha': 0})
P['escape_flag'] = np.where(P.all_max_out_ha >= 200, 'high: a fire from here ran 200+ ha outside', np.where(P.all_max_out_ha >= 50, 'medium: 50-200 ha outside', 'low'))
P.sort_values('rank').to_csv(B.OUT + 'cb14_escape_patches.csv', index=False)
B3 = P[P.cum_ha <= 100000]; print('first 100k ha patches:', len(B3), 'with a Feb start on record', int((B3.feb_fires > 0).sum()), 'escape flag:', B3.escape_flag.value_counts().to_dict())
print('all patches escape flag:', P.escape_flag.value_counts().to_dict())
