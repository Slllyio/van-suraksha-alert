"""Train the learned per-pixel burned classifier (LightGBM) on the training chips only.
Labels (no independent truth is used here):
  positive  = the rule's pass-1 core pixels in alert chips (strict drop + NIR + persistence, patch touching an alert disk)
  PU model  = positive vs everything else (unlabeled) in alert and control chips; Elkan-Noto correction:
              c = mean score of held-out positives, burned if score >= c/2 (i.e. P(burned) >= 0.5)
  PN model  = positive vs all pixels of control chips (3 km away, no alert within 1.5 km / 15 days), class-balanced
Out: model_pu.txt, model_pn.txt, train_meta.json (features, c, CV numbers), feature importance csv."""
import json, os, time, warnings, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.model_selection import GroupKFold
from lib import CODE, SCR, prepare, features, static_layers
warnings.filterwarnings('ignore')
C = pd.read_csv(CODE + 'chips.csv'); C = C[C.kind.isin(['train_alert', 'train_control'])]
rng = np.random.default_rng(0); rows = []; t0 = time.time(); FE = None
for r in C.to_dict('records'):
    if not os.path.exists(f"{SCR}stacks/{r['chip']}.npz"): continue
    p = prepare(r)
    if p is None: continue
    f = features(p['st'], p['pair'], p['parts'], static_layers(p['st']['tr'], p['st']['n']))
    FE = FE or sorted(f)
    ok = p['parts']['ok']; pos = p['core'] & ok
    if r['kind'] == 'train_control': pos[:] = False
    unl = ok & ~pos
    pi, ui = np.flatnonzero(pos), np.flatnonzero(unl)
    pi = rng.choice(pi, min(len(pi), 1500), replace=False) if len(pi) else pi
    ui = rng.choice(ui, min(len(ui), 1500), replace=False) if len(ui) else ui
    ii = np.r_[pi, ui]
    M = np.stack([f[k].ravel()[ii] for k in FE], 1).astype(np.float32)
    rows.append(pd.DataFrame(M, columns=FE).assign(y=np.r_[np.ones(len(pi)), np.zeros(len(ui))], chip=r['chip'], ctrl=r['kind'] == 'train_control',
                                                    rule=p['rule'].ravel()[ii]))
D = pd.concat(rows, ignore_index=True); print('pixels', len(D), 'pos', int(D.y.sum()), 'chips', D.chip.nunique(), f'{time.time()-t0:.0f}s')
D.to_parquet(SCR + 'train_pixels.parquet')
prm = dict(objective='binary', learning_rate=0.05, num_leaves=63, min_data_in_leaf=100, feature_fraction=0.7, bagging_fraction=0.8,
           bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=4)
meta = dict(features=FE, n_pixels=len(D), n_pos=int(D.y.sum()), n_chips=int(D.chip.nunique()))
# PU: cross-validated c
oof = np.zeros(len(D))
for tr_i, te_i in GroupKFold(5).split(D, D.y, D.chip):
    b = lgb.train(prm, lgb.Dataset(D.iloc[tr_i][FE], D.y.iloc[tr_i]), 300)
    oof[te_i] = b.predict(D.iloc[te_i][FE])
c = float(oof[D.y == 1].mean()); meta['pu_c'] = c
meta['pu_oof_unlabeled_called_burned'] = float((oof[D.y == 0] >= c / 2).mean())
meta['pu_oof_unlabeled_called_burned_control'] = float((oof[(D.y == 0) & D.ctrl] >= c / 2).mean())
meta['pu_oof_unlabeled_called_burned_alertchips'] = float((oof[(D.y == 0) & ~D.ctrl] >= c / 2).mean())
meta['pu_oof_pos_recall'] = float((oof[D.y == 1] >= c / 2).mean())
bpu = lgb.train(prm, lgb.Dataset(D[FE], D.y), 300); bpu.save_model(CODE + 'model_pu.txt')
# PN: positives vs control-chip pixels
E = D[(D.y == 1) | D.ctrl]; w = np.where(E.y == 1, 0.5 / E.y.mean(), 0.5 / (1 - E.y.mean()))
oof2 = np.zeros(len(E))
for tr_i, te_i in GroupKFold(5).split(E, E.y, E.chip):
    b = lgb.train(prm, lgb.Dataset(E.iloc[tr_i][FE], E.y.iloc[tr_i], weight=w[tr_i]), 300); oof2[te_i] = b.predict(E.iloc[te_i][FE])
meta['pn_oof_pos_recall'] = float((oof2[E.y == 1] >= 0.5).mean()); meta['pn_oof_ctrl_called_burned'] = float((oof2[E.y == 0] >= 0.5).mean())
bpn = lgb.train(prm, lgb.Dataset(E[FE], E.y, weight=w), 300); bpn.save_model(CODE + 'model_pn.txt')
imp = pd.DataFrame(dict(feature=FE, gain_pu=bpu.feature_importance('gain'), gain_pn=bpn.feature_importance('gain')))
imp.sort_values('gain_pu', ascending=False).to_csv(CODE + 'feature_importance.csv', index=False)
json.dump(meta, open(CODE + 'train_meta.json', 'w'), indent=1); print(json.dumps({k: v for k, v in meta.items() if k != 'features'}, indent=1))
print(imp.sort_values('gain_pu', ascending=False).head(15).to_string())
