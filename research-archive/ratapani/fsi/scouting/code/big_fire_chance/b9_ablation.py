"""Step 9: which groups of alert-time items carry the skill (logistic regression, same held-out splits as b6), and the
existing dot-count flag re-read all-MP and in Ratapani. Out: out/ablation.csv, out/dots_table.csv"""
import numpy as np, pandas as pd, warnings
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
warnings.filterwarnings('ignore')
exec(open('/mnt/project-files/ratapani/fsi/scouting/code/big_fire_chance/b6_models.py').read().split('LGBP = dict')[0])
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/big_fire_chance/out'
GR = {'dots': ['l_n1'],
      'size of first look (extent, FRP, block size, brightness)': ['l_ext1', 'l_frp_sum1', 'l_frp_max1', 'blk1', 'bt4_max1'],
      'timing (date, hour, night, satellite, era)': ['days_since_15feb', 'hour', 'night', 'era', 'sen_S-NPP', 'sen_NOAA-20', 'sen_NOAA-21'],
      'place (division history, speed map, forest type, terrain)': ['div_hist', 'speed50', 'g_grass_dots', 'g_teak_dots', 'g_sal_dots', 'g_dry_dots',
            'g_moist_dots', 'g_degr_dots', 'g_bamboo_dots', 'grass_1km', 'teak_1km', 'sal_1km', 'forest_1km', 'agri_1km', 'slope1', 'slope_max1', 'elev1', 'rough1500'],
      'context (fires nearby 3 days, burned before, statewide activity)': ['l_near10_3d', 'l_near3_3d', 'l_burned_before_2km', 'l_state_24h'],
      'flags (control burn, MODIS before)': ['control_live', 'terra_before', 'modis_before']}
ALL = sum(GR.values(), [])
CONF = {'dots only': ['l_n1']}
acc = ['l_n1']
for k in list(GR)[1:]:
    acc = acc + GR[k]; CONF['+ ' + k.split(' (')[0]] = list(acc)
for k in list(GR)[1:]:
    CONF['all minus ' + k.split(' (')[0]] = [f for f in ALL if f not in GR[k]]
CONF['all minus division history'] = [f for f in ALL if f != 'div_hist']
CONF['all minus speed map'] = [f for f in ALL if f != 'speed50']
SPL = [(f'loso{s}', [t for t in range(2017, 2025) if t != s], [s]) for s in range(2017, 2025)] + [('forward', list(range(2017, 2025)), [2025, 2026])]
rows = []
for tgt in ('S200', 'V200'):
    y = A[f'y{tgt}']
    for cname, feats in CONF.items():
        pr = pd.Series(np.nan, index=A.index); st = pd.Series('', index=A.index)
        for name, trs, tes in SPL:
            X = XB.copy(); X['div_hist'] = div_hist(trs); X = X[feats]
            tr = A.season.isin(trs).values & y.notna().values; te = A.season.isin(tes).values
            med = X[tr].median(); sc = StandardScaler().fit(X[tr].fillna(med))
            m = LogisticRegression(C=0.3, max_iter=3000).fit(sc.transform(X[tr].fillna(med)), y[tr].astype(int))
            pr[te] = m.predict_proba(sc.transform(X[te].fillna(med)))[:, 1]; st[te] = 'loso' if name != 'forward' else 'fwd'
        for s_ in ('loso', 'fwd'):
            ok = (st == s_) & y.notna()
            rows.append(dict(target=tgt, config=cname, set=s_ + ('2025-26' if s_ == 'fwd' else ' 2017-24'), auc=roc_auc_score(y[ok], pr[ok])))
        print(rows[-2], rows[-1], flush=True)
pd.DataFrame(rows).to_csv(f'{OUT}/ablation.csv', index=False, float_format='%.3f')
# the dot-count flag, read again
A['dots'] = pd.cut(A.n1, [0, 1, 2, 4, 1000], labels=['1 dot', '2 dots', '3-4 dots', '5+ dots'])
A['ratapani'] = A.Division.isin(['Obedullahganj', 'Raisen'])
T = []
for reg, g in (('all MP', A), ('Obedullahganj + Raisen (Ratapani)', A[A.ratapani])):
    for tgt in ('S200', 'V200'):
        h = g[g[f'y{tgt}'].notna()]
        t = h.groupby('dots', observed=True)[f'y{tgt}'].agg(['size', 'mean']).reset_index(); t['region'] = reg; t['truth'] = tgt
        t['share_of_big'] = h.groupby('dots', observed=True)[f'y{tgt}'].sum().values / h[f'y{tgt}'].sum()
        T.append(t)
T = pd.concat(T); T.to_csv(f'{OUT}/dots_table.csv', index=False, float_format='%.3f'); print(T.round(3).to_string())
