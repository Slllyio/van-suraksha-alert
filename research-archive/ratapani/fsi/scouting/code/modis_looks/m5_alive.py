"""Test 3. Does a MODIS look between two VIIRS looks (mainly Terra 22:30 IST between the 13:30 and 01:30 VIIRS looks)
tell whether a fire is still alive better than VIIRS alone? Stopping-model idea of fire_stopping_and_tracking.md, Part A,
but the label is "seen at the NEXT VIIRS look".
States: every all-MP forest fire (m1, 1 km / 48 h) at every VIIRS slot from its first detection to 3 slots after its last.
VIIRS features: silent slots since last detection, FRP at this slot / last / max so far, slots seen so far, age, points
at this slot, hour (day/night). MODIS features (only what is known >1 h before the next VIIRS look): Terra/Aqua seen on the
fire between this slot and the next, their max FRP, Aqua at this slot, any MODIS since the last VIIRS detection.
Model: HistGradientBoosting, seasons held out one at a time (as the stopping note). Out: results/alive.csv"""
import os, numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier as H
from sklearn.metrics import roc_auc_score, brier_score_loss
S = os.environ['ML_SCRATCH']; OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
F = pd.read_parquet(f'{S}/fires_mp.parquet'); T = pd.read_parquet(f'{S}/fire_slots_mp.parquet'); M = pd.read_parquet(f'{S}/modis_fire_mp.parquet')
SCH = pd.read_parquet(f'{S}/schedule.parquet'); st = SCH.t.values
M = M[M.fire >= 0].copy()
T = T.sort_values(['fire', 'slot']).reset_index(drop=True)
T['det'] = T.nv > 0
g = T.groupby('fire')
T['label'] = g.det.shift(-1)
T = T[T.label.notna()].copy(); T['label'] = T.label.astype(bool); g = T.groupby('fire')
T['seen_so_far'] = g.det.cumsum()
last_det_slot = T.slot.where(T.det); T['last_det'] = last_det_slot.groupby(T.fire).ffill()
T['k'] = T.slot - T.last_det
T['frp_now'] = T.frp.fillna(0); T['frp_last'] = T.frp.groupby(T.fire).ffill(); T['frp_max'] = T.frp.fillna(0).groupby(T.fire).cummax()
T['age'] = T.slot - g.slot.transform('min'); T['day'] = T.h > 8
# MODIS: slot index just before each MODIS point; usable for state s if t > t_s + 1 h and t < t_{s+1} - 1 h, or |t - t_s| <= 1.5 h (Aqua with VIIRS)
k = np.searchsorted(st, M.t.values, side='right') - 1
aft = (M.t.values - st[k]) / np.timedelta64(1, 'h'); bef = (st[np.minimum(k + 1, len(st) - 1)] - M.t.values) / np.timedelta64(1, 'h')
M['slot'] = k
btw = M[(aft > 1) & (bef > 1)]
at = M[aft <= 1.5]
def agg(D, nm):
    return D.groupby(['fire', 'slot']).agg(**{f'{nm}_n': ('t', 'size'), f'{nm}_frp': ('frp', 'max')}).reset_index()
for D, nm in [(btw[btw.sensor == 'Terra'], 'terra_btw'), (btw[btw.sensor == 'Aqua'], 'aqua_btw'), (at, 'modis_at')]:
    T = T.merge(agg(D, nm), on=['fire', 'slot'], how='left')
for c in [c for c in T.columns if c.startswith(('terra_btw', 'aqua_btw', 'modis_at'))]: T[c] = T[c].fillna(0)
# any MODIS since the last VIIRS detection (cumulative within the silent run, incl. between this slot and the next)
T['m_any'] = ((T.terra_btw_n + T.aqua_btw_n + T.modis_at_n) > 0).astype(int)
T['run'] = T.groupby('fire').det.cumsum()
T['m_since_lastV'] = T.groupby(['fire', 'run']).m_any.cummax()
T['season'] = T.fire.map(F.season); T['rbox'] = T.fire.map(F.ratapani_box)
VF = ['k', 'frp_now', 'frp_last', 'frp_max', 'seen_so_far', 'age', 'nv', 'h']
MF = VF + ['terra_btw_n', 'terra_btw_frp', 'aqua_btw_n', 'aqua_btw_frp', 'modis_at_n', 'modis_at_frp', 'm_since_lastV']
def loso(cols):
    p = np.zeros(len(T))
    for s in sorted(T.season.unique()):
        tr, te = T.season != s, T.season == s
        m = H(max_iter=200, learning_rate=.05, max_leaf_nodes=15).fit(T.loc[tr, cols], T.loc[tr, 'label']); p[te.values] = m.predict_proba(T.loc[te, cols])[:, 1]
    return p
TF = VF + ['terra_btw_n', 'terra_btw_frp']
T['pV'] = loso(VF); T['pM'] = loso(MF); T['pT'] = loso(TF)
rows = []
subsets = {'all states': T.index == T.index, 'at 13:30 look (next = 01:30)': T.day, 'at 01:30 look (next = 13:30)': ~T.day,
           'silent states (k>=1)': T.k >= 1, '13:30 look, fire seen then': T.day & T.det,
           'Terra look in the gap': T.terra_btw_n > 0, 'Ratapani box': T.rbox}
for nm, s in subsets.items():
    D = T[s]
    if D.label.nunique() < 2: continue
    r = dict(subset=nm, n=len(D), base_rate=round(D.label.mean(), 3), share_with_terra_btw=round((D.terra_btw_n > 0).mean(), 3),
             auc_viirs=round(roc_auc_score(D.label, D.pV), 4), auc_with_modis=round(roc_auc_score(D.label, D.pM), 4), auc_with_terra_only=round(roc_auc_score(D.label, D.pT), 4),
             brier_viirs=round(brier_score_loss(D.label, D.pV), 4), brier_with_modis=round(brier_score_loss(D.label, D.pM), 4), brier_with_terra_only=round(brier_score_loss(D.label, D.pT), 4))
    # fire-cluster bootstrap of the AUC gain
    rng = np.random.default_rng(0); fid = D.fire.values; uf = np.unique(fid); gains = []
    pos = pd.Series(np.arange(len(D))).groupby(fid).apply(np.array)
    for _ in range(100):
        pick = np.concatenate(pos.loc[rng.choice(uf, len(uf))].values)
        y = D.label.values[pick]
        if 0 < y.sum() < len(y): gains.append(roc_auc_score(y, D.pM.values[pick]) - roc_auc_score(y, D.pV.values[pick]))
    r['auc_gain_lo'], r['auc_gain_hi'] = np.round(np.percentile(gains, [2.5, 97.5]), 4)
    rows.append(r)
X = pd.DataFrame(rows); X.to_csv(f'{OUT}/alive.csv', index=False); pd.set_option('display.width', 250); print(X)
# simple table: 13:30 detection -> seen at 01:30, by Terra 22:30
D = T[T.day & T.det]
tab = D.groupby([(D.terra_btw_n > 0).rename('terra_22_30'), pd.cut(D.frp_now, [0, 5, 15, 50, 1e5]).rename('frp_1330')], observed=True).label.agg(['mean', 'size']).round(3)
print(tab); tab.to_csv(f'{OUT}/alive_table_1330.csv')
D = T[T.day & ~T.det & (T.k <= 2)]
tab2 = D.groupby([(D.terra_btw_n > 0).rename('terra_22_30'), D.k.rename('silent_slots')]).label.agg(['mean', 'size']).round(3)
print(tab2); tab2.to_csv(f'{OUT}/alive_table_silent.csv')
# declare-out rule: states flagged p<0.10
for c in ['pV', 'pM']:
    f = T[c] < .10; print(c, 'flag p<0.10:', int(f.sum()), 'seen next look %.3f' % T.label[f].mean())
