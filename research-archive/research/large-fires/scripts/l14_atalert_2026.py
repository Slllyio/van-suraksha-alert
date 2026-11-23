"""Step 14. At alert on scar truth with the app's REAL points (big_fire_replay season_<S>.csv), 2025 and 2026.
Each scar fire starting 15 Feb-31 May is matched to the replay's new-fire first look nearest its start (within 1.5 km,
same IST day or the day before/after). Size score = max SIZE of the start squares on the day before (models trained
2018-24). Combination = logistic on points + logit(size) fitted on 2025, tested on 2026.
Out: results/at_alert_scar_truth.csv."""
import pickle, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from pyproj import Transformer
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression
import lf_common as L, lf_sr
U = lf_sr.Fe.base()['U']; tr = Transformer.from_crs(4326, 32643, always_xy=True)
lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))


def table(y, fires):
    R = pd.read_csv(L.P + f'field-system/docs/big_fire_replay/season_{y}.csv')
    R['x'], R['y'] = tr.transform(R.lon.values, R.lat.values)
    R['day'] = pd.to_datetime(R.first_look_utc).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None).dt.normalize()
    t = cKDTree(R[['x', 'y']].values); c = np.load(L.SC + f'cube_SIZE_{y}.npy').astype(np.float32); d0 = pd.Timestamp(f'{y}-02-13')
    rows = []
    for f in fires:
        if not (pd.Timestamp(f'{y}-02-15') <= f['start_day'] <= pd.Timestamp(f'{y}-05-31')): continue
        sc = f['start_cells']; x = (L.X0 + (sc % L.W + .5) * L.S).mean(); yy = (L.Y1 - (sc // L.W + .5) * L.S).mean()
        ii = [i for i in t.query_ball_point([x, yy], 1500) if abs((R.day.iloc[i] - f['start_day']).days) <= 1]
        if not ii: continue
        j = min(ii, key=lambda i: (abs((R.day.iloc[i] - f['start_day']).days), np.hypot(R.x.iloc[i] - x, R.y.iloc[i] - yy)))
        k = np.searchsorted(U, sc); ok = (k < len(U)) & (U[np.minimum(k, len(U) - 1)] == sc); tt = (f['start_day'] - pd.Timedelta(days=1) - d0).days
        if not ok.any() or tt < 0: continue
        rows.append(dict(season=y, fire=f['fire'], day=f['start_day'], ha=f['forest_ha'], points=R.points.iloc[j], size=float(np.nanmax(c[tt, k[ok]]))))
    return pd.DataFrame(rows).dropna()


F25 = [f for f in pickle.load(open(L.SC + 'fires.pkl', 'rb')) if f['year'] == 2025]
F26 = pickle.load(open(L.SC + 'fires_2026.pkl', 'rb'))
A, B = table(2025, F25), table(2026, F26); out = []
for th in (200, 500):
    m = LogisticRegression().fit(np.c_[A.points, lg(A['size'])], A.ha >= th)
    for D, nm in ((A, '2025 (fit)'), (B, '2026')):
        y = (D.ha >= th).values; comb = m.predict_proba(np.c_[D.points, lg(D['size'])])[:, 1]
        for k, s in (('points', D.points + 1e-6 * D['size']), ('size_score', D['size']), ('points_plus_size', comb)):
            bs = [roc_auc_score(y[i], np.asarray(s)[i]) for i in [np.random.default_rng(b).integers(0, len(y), len(y)) for b in range(300)]]
            rk = pd.Series(np.asarray(s)).groupby(D.day.values).rank(ascending=False, pct=True).values
            out.append(dict(season=nm, size=f'{th}+', n_fires=len(y), n_big=int(y.sum()), score=k, auc=roc_auc_score(y, s),
                            lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5), top10_share=100 * (y & (rk <= .1)).sum() / y.sum()))
O = pd.DataFrame(out).round(3); O.to_csv(L.OUT + 'at_alert_scar_truth.csv', index=False); print(O.to_string())
