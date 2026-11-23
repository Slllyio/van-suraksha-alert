"""Second learned model whose labels do NOT come from the NBR rule: positives are Sentinel-2/Landsat fire pixels
(hot at the ~10:30 overpass, so certainly burning) in the train_af chips, with that scene removed from the stack;
negatives are the control-chip pixels (3 km from alerts, no alert within 1.5 km / 15 days). Class-balanced, P >= 0.5.
Out: model_af.txt, train_af_meta.json."""
import json, os, warnings, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.model_selection import GroupKFold
from pyproj import Transformer
from lib import CODE, SCR, prepare, features, static_layers, RES
warnings.filterwarnings('ignore')
META = json.load(open(CODE + 'train_meta.json')); FALL = META['features']
# chip-level constants are dropped: positives and negatives come from different chip sets, so gap length etc. would leak
FE = [f for f in FALL if f not in ('gap_days', 'chk_days', 'doy', 'pre_is_s2', 'post_is_s2')]
TO = Transformer.from_crs(4326, 32643, always_xy=True)
af = pd.read_csv('/mnt/project-files/fire-alert-scars/out/af/af_pixels_clean.csv')
af['key'] = af.season.astype(str) + '_' + af.cluster.astype(str) + '_' + af.date; af['x'], af['y'] = TO.transform(af.lon.values, af.lat.values)
C = pd.read_csv(CODE + 'chips.csv'); rows = []
for r in C[C.kind == 'train_af'].to_dict('records'):
    if not os.path.exists(f"{SCR}stacks/{r['chip']}.npz"): continue
    p = prepare(r, [r['scene_date']])
    if p is None: continue
    st = p['st']; n = st['n']; tr = st['tr']
    q = af[af.key == r['key']]; cc = ((q.x - tr[2]) / RES).astype(int).values; rr = ((tr[5] - q.y) / RES).astype(int).values
    k = (cc >= 0) & (cc < n) & (rr >= 0) & (rr < n); ii = np.unique(rr[k] * n + cc[k])
    ii = ii[p['parts']['ok'].ravel()[ii]]
    if not len(ii): continue
    f = features(st, p['pair'], p['parts'], static_layers(tr, n))
    rows.append(pd.DataFrame(np.stack([f[k_].ravel()[ii] for k_ in FE], 1), columns=FE).assign(y=1, chip=r['chip']))
P = pd.concat(rows, ignore_index=True)
T = pd.read_parquet(SCR + 'train_pixels.parquet'); N = T[T.ctrl][FE + ['chip']].assign(y=0)
D = pd.concat([P, N], ignore_index=True); w = np.where(D.y == 1, 0.5 / D.y.mean(), 0.5 / (1 - D.y.mean()))
prm = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=50, feature_fraction=0.7, bagging_fraction=0.8,
           bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=4)
oof = np.zeros(len(D))
for a, b in GroupKFold(5).split(D, D.y, D.chip):
    m = lgb.train(prm, lgb.Dataset(D.iloc[a][FE], D.y.iloc[a], weight=w[a]), 300); oof[b] = m.predict(D.iloc[b][FE])
m = lgb.train(prm, lgb.Dataset(D[FE], D.y, weight=w), 300); m.save_model(CODE + 'model_af.txt')
meta = dict(features=FE, n_pos=int(D.y.sum()), pos_chips=int(P.chip.nunique()), n_neg=int((D.y == 0).sum()),
            oof_pos_recall=float((oof[D.y == 1] >= 0.5).mean()), oof_ctrl_called_burned=float((oof[D.y == 0] >= 0.5).mean()),
            top_features=pd.Series(m.feature_importance('gain'), FE).sort_values(ascending=False).head(10).round(0).to_dict())
json.dump(meta, open(CODE + 'train_af_meta.json', 'w'), indent=1); print(json.dumps({k: v for k, v in meta.items() if k != 'features'}, indent=1))
