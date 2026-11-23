"""Step 6: models, held out by season.
Splits: leave-one-season-out over 2017-2024 (train on the other 2017-24 seasons), and a forward test (train 2017-24 once,
predict 2025 and 2026). Every fitted thing (division history, medians, scaler, model, isotonic map) uses training seasons only.
Models: 'dots' = big-fire rate per first-look dot class (the existing flag, refitted all-MP); 'logit' = logistic regression;
'lgbm' = LightGBM with an isotonic calibration map fitted on inner season-group out-of-fold scores.
Targets: truth V (VIIRS footprint) and S (scar), 50/200/500 ha; feature versions v1 (first look) and v2 (first look + 15 h).
Out (scratch): preds.parquet (every population alert x config x model)."""
import sys, warnings
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
warnings.filterwarnings('ignore')
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
A = pd.read_parquet(f'{SC}/ds.parquet').reset_index(drop=True)
L = np.log
def base_feats(A):
    X = pd.DataFrame(index=A.index)
    X['l_n1'] = L(A.n1); X['l_ext1'] = L(A.ext1); X['l_frp_sum1'] = L(A.frp_sum1.clip(lower=0.1)); X['l_frp_max1'] = L(A.frp_max1.clip(lower=0.1))
    X['blk1'] = A.blk1; X['night'] = A.night; X['hour'] = A.hour; X['days_since_15feb'] = A.days_since_15feb; X['speed50'] = A.speed50
    for c in ['g_grass_dots', 'g_teak_dots', 'g_sal_dots', 'g_dry_dots', 'g_moist_dots', 'g_degr_dots', 'g_bamboo_dots', 'g_nonforest_dots',
              'grass_1km', 'teak_1km', 'sal_1km', 'forest_1km', 'agri_1km', 'slope1', 'slope_max1', 'elev1', 'rough1500', 'control_live',
              'terra_before', 'modis_before', 'bt4_max1']:
        X[c] = A[c]
    X['l_near10_3d'] = np.log1p(A.near10_3d); X['l_near3_3d'] = np.log1p(A.near3_3d); X['l_burned_before_2km'] = np.log1p(A.burned_before_2km)
    X['l_state_24h'] = np.log1p(A.state_24h); X['era'] = A.era
    for s in ('S-NPP', 'NOAA-20', 'NOAA-21'): X[f'sen_{s}'] = (A.sensor == s).astype(int)
    return X
def v2_feats(A):
    X = pd.DataFrame(index=A.index)
    X['l_n2'] = L(A.n2); X['l_ext2'] = L(A.ext2); X['l_cells2'] = L(A.cells2.fillna(1)); X['looks2'] = A.looks2; X['seen_again2'] = A.seen_again2
    X['l_n_later2'] = np.log1p(A.n_later2); X['night_later2'] = A.night_later2; X['l_frp_sum2'] = L(A.frp_sum2.clip(lower=0.1))
    X['l_frp_max2'] = L(A.frp_max2.clip(lower=0.1)); X['g_n'] = L(A.n2 / A.n1); X['g_ext'] = L(A.ext2 / A.ext1); X['terra_between2'] = A.terra_between2
    return X
XB, X2 = base_feats(A), v2_feats(A)
# division history: VIIRS-truth 200 ha share per division, from training seasons other than the row's own season
TAB = A.groupby(['Division', 'season']).yV200.agg(['sum', 'count']).reset_index()
def div_hist(train_seasons, m=50):
    T = TAB[TAB.season.isin(train_seasons)]
    tot = T.groupby('Division')[['sum', 'count']].sum()
    prior = T['sum'].sum() / T['count'].sum()
    own = TAB.set_index(['Division', 'season'])
    s_ = own.reindex(pd.MultiIndex.from_arrays([A.Division, A.season])).fillna(0).values
    t_ = tot.reindex(A.Division).fillna(0).values
    in_tr = A.season.isin(train_seasons).values[:, None]
    num = t_[:, 0] - np.where(in_tr[:, 0], s_[:, 0], 0); den = t_[:, 1] - np.where(in_tr[:, 0], s_[:, 1], 0)
    return (num + m * prior) / (den + m)
def dot_class(n): return np.digitize(n, [1.5, 2.5, 4.5, 8.5])   # 1, 2, 3-4, 5-8, 9+
LGBP = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=100, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=1)
def fit_predict(Xtr, ytr, gtr, Xte):
    out = {}
    # logistic
    med = Xtr.median(); sc = StandardScaler().fit(Xtr.fillna(med))
    lr = LogisticRegression(C=0.3, max_iter=3000).fit(sc.transform(Xtr.fillna(med)), ytr)
    out['logit'] = lr.predict_proba(sc.transform(Xte.fillna(med)))[:, 1]
    # lightgbm + isotonic from inner season-group folds
    us = np.unique(gtr); folds = np.array_split(np.random.default_rng(0).permutation(us), 4)
    oof = np.zeros(len(ytr))
    for fs in folds:
        te = np.isin(gtr, fs)
        m = lgb.LGBMClassifier(**LGBP).fit(Xtr[~te], ytr[~te]); oof[te] = m.predict_proba(Xtr[te])[:, 1]
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(oof, ytr)
    m = lgb.LGBMClassifier(**LGBP).fit(Xtr, ytr)
    out['lgbm'] = iso.predict(m.predict_proba(Xte)[:, 1])
    out['lgbm_raw'] = m.predict_proba(Xte)[:, 1]
    return out, m
SPLITS = [(f'loso{s}', [t for t in range(2017, 2025) if t != s], [s]) for s in range(2017, 2025)] + [('forward', list(range(2017, 2025)), [2025, 2026])]
want = sys.argv[1:] or ['V200', 'S200', 'V50', 'S50', 'V500', 'S500']
rows, imps = [], []
for tgt in want:
    y_all = A[f'y{tgt}']
    for ver in ('v1', 'v2'):
        for name, trs, tes in SPLITS:
            dh = div_hist(trs)
            X = XB.copy(); X['div_hist'] = dh
            if ver == 'v2': X = pd.concat([X, X2], axis=1)
            tr = A.season.isin(trs).values & y_all.notna().values; te = A.season.isin(tes).values
            ytr = y_all.values[tr].astype(int)
            res, m = fit_predict(X[tr], ytr, A.season.values[tr], X[te])
            dc = dot_class(A.n1.values); rate = pd.Series(ytr).groupby(dc[tr]).mean()
            res['dots'] = pd.Series(dc[te]).map(rate).fillna(rate.iloc[-1]).values
            for k, p in res.items():
                rows.append(pd.DataFrame(dict(alert=A.alert.values[te], target=tgt, ver=ver, split=name, model=k, p=p.astype(np.float32))))
            if name == 'forward':
                imps.append(pd.DataFrame(dict(target=tgt, ver=ver, feature=X.columns, gain=m.booster_.feature_importance('gain'))))
            print(tgt, ver, name, "train", tr.sum(), "pos", ytr.sum(), pd.Timestamp.now(), flush=True)
        pd.concat(rows).to_parquet(f'{SC}/preds_{"_".join(want)}.parquet'); pd.concat(imps).to_parquet(f'{SC}/imp_{"_".join(want)}.parquet')
