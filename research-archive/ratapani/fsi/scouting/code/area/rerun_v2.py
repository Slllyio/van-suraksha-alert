"""Area-from-VIIRS-points tests: v1 scars vs v2 scars (16 Oct 2026), same design.
Features from build_features.py (features_750.parquet; computed from VIIRS points and the event's
alert date / post_date, independent of the scar outline). Targets: v1 = scar_ha in features file;
v2 = scar_ha in reference/v2_2026-10-16/firms_event_scars.geojson.
Leave-one-season-out, Jan-Jun, grew_into_large_burn (v1 flag) dropped in both, so rows are identical.
Usage: python3 -I rerun_v2.py <features.parquet> <v2 firms_event_scars.geojson> <out_dir>
"""
import sys, json, numpy as np, pandas as pd, lightgbm as lgb, pyogrio
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

feat_p, v2_p, out = sys.argv[1], sys.argv[2], sys.argv[3]
F = pd.read_parquet(feat_p)
V2 = pyogrio.read_dataframe(v2_p, read_geometry=False)[
    ['event_id', 'scar_ha', 'post_date', 'still_at_edge', 'v2_action', 'chip_km']].rename(
    columns={'scar_ha': 'scar_ha_v2', 'post_date': 'post_v2'})
F = F.merge(V2, on='event_id', how='left')
F = F[(F.month <= 6) & ~F.grew_large & F.scar_ha_v2.notna()].reset_index(drop=True)
F['still_at_edge'] = F.still_at_edge.fillna(False).astype(bool)
print('rows', len(F), '| v2 redrawn among them', F.v2_action.isin(['redrawn_split']).sum(),
      '| v2 still at edge', F.still_at_edge.sum(), '| v1 at edge', F.edge.sum())
seasons = sorted(F.year.unique())
labs = ['<10', '10-30', '30-100', '100-300', '300-1000', '>=1000']
bins = [0, 10, 30, 100, 300, 1000, 1e9]
REG = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40,
           subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
q = lambda p: (lambda s: np.percentile(s, p))
R = {}


def run(tag, area, edge):
    r = {}
    y = np.log(area)
    cls = pd.cut(area, bins, labels=labs, right=False)
    r['n'] = len(area); r['n_edge'] = int(edge.sum()); r['median_ha'] = np.median(area); r['total_ha'] = area.sum()
    cols0 = [c for c in F.columns if c.startswith('d0_')] + ['month']
    colsA = [c for c in F.columns if c.startswith('all_')] + ['month']
    preds = {}
    for name, cols in [('lgb_d0', cols0), ('lgb_all', colsA)]:
        X = F[cols].values; p = np.full(len(F), np.nan); pb = p.copy(); ps = p.copy()
        lo = p.copy(); hi = p.copy()
        for s in seasons:
            te = (F.year == s).values; tr = ~te
            p[te] = lgb.LGBMRegressor(**REG).fit(X[tr], y[tr]).predict(X[te])
            C = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40, verbose=-1)
            pb[te] = lgb.LGBMClassifier(**C).fit(X[tr], area[tr] >= 100).predict_proba(X[te])[:, 1]
            ps[te] = lgb.LGBMClassifier(**C).fit(X[tr], area[tr] < 10).predict_proba(X[te])[:, 1]
            if name == 'lgb_d0':
                for a, arr in [(0.1, lo), (0.9, hi)]:
                    arr[te] = lgb.LGBMRegressor(objective='quantile', alpha=a, n_estimators=300, learning_rate=0.03,
                                                num_leaves=15, min_child_samples=40, verbose=-1).fit(X[tr], y[tr]).predict(X[te])
        preds[name] = p
        r[f'{name}:auc_ge100'] = roc_auc_score(area >= 100, pb)
        r[f'{name}:auc_lt10'] = roc_auc_score(area < 10, ps)
        k = int(0.1 * len(F)); r[f'{name}:top10_prec_ge100'] = np.mean(area[np.argsort(-pb)[:k]] >= 100)
        if name == 'lgb_d0':
            cov = (y >= lo) & (y <= hi); r['q80_cov_all'] = cov.mean()
            r['q80_width_factor'] = float(np.exp(np.median(hi - lo)))
            for c in labs:
                m = cls == c
                if m.sum(): r[f'q80_cov:{c}'] = cov[m].mean()
    r['base_ge100'] = np.mean(area >= 100); r['base_lt10'] = np.mean(area < 10)
    # null and power law
    pn = np.full(len(F), np.nan); pl = pn.copy()
    xl = np.log(F.d0_fp_union_ha.values)
    for s in seasons:
        te = (F.year == s).values; tr = ~te
        pn[te] = np.median(y[tr]); b = np.polyfit(xl[tr], y[tr], 1); pl[te] = np.polyval(b, xl[te])
    preds['null'] = pn; preds['pow_d0_union'] = pl; preds['raw_d0_union'] = np.log(F.d0_fp_union_ha.values)
    preds['raw_d0_hull'] = np.log(F.d0_hull_ha.values)
    for name, p in preds.items():
        lr = (p - y) / np.log(2)
        r[f'{name}:spearman'] = spearmanr(p, y)[0] if name != 'null' else np.nan
        r[f'{name}:within_x2'] = np.mean(np.abs(lr) <= 1)
        r[f'{name}:med_abs_log2'] = np.median(np.abs(lr))
        # also scored only on rows not at chip edge (v1: touches edge; v2: still_at_edge)
        ok = ~edge
        r[f'{name}:within_x2_noedge'] = np.mean(np.abs(lr[ok]) <= 1)
        for c in labs:
            m = cls == c
            if m.sum() == 0: continue
            r[f'{name}:n:{c}'] = int(m.sum())
            r[f'{name}:x2:{c}'] = np.mean(np.abs(lr[m]) <= 1)
            r[f'{name}:ratio:{c}'] = 2 ** np.median(lr[m])
            r[f'{name}:MAE:{c}'] = np.mean(np.abs(np.exp(p[m]) - area[m]))
    # power-law fits on full data
    for x in ['d0_n', 'd0_fp_union_ha', 'd0_frp_sum', 'all_n']:
        b = np.polyfit(np.log(F[x]), y, 1); res = y - np.polyval(b, np.log(F[x]))
        r[f'fit:{x}'] = f'{np.exp(b[1]):.1f} * x^{b[0]:.2f} (resid factor {np.exp(res.std()):.2f})'
        r[f'spearman_raw:{x}'] = spearmanr(F[x], area)[0]
    # lookup by day-0 detection count
    nb = pd.cut(F.d0_n, [0, 1, 2, 4, 8, 16, 1000], labels=['1', '2', '3-4', '5-8', '9-16', '>16'])
    T = pd.DataFrame({'nb': nb, 'a': area}).groupby('nb', observed=True).a.agg(
        n='size', p10=q(10), p50=q(50), p90=q(90), share_ge100=lambda s: (s >= 100).mean())
    r['lookup'] = T
    # ha per detection and per MW
    nbA = pd.cut(F.all_n, [0, 1, 2, 4, 8, 16, 1000], labels=['1', '2', '3-4', '5-8', '9-16', '>16'])
    r['ha_per_det'] = pd.Series(area / F.all_n.values).groupby(nbA.values, observed=True).median()
    hpm = area / F.all_frp_sum.values
    r['ha_per_MW'] = np.median(hpm)
    r['ha_per_MW_month'] = pd.Series(hpm).groupby(F.month.values).median()
    r['median_month'] = pd.Series(area).groupby(F.month.values).median()
    r['spearman_gap'] = spearmanr(F.gap_days, area)[0]
    return r


R['v1'] = run('v1', F.scar_ha.values, F.edge.values)
R['v2'] = run('v2', F.scar_ha_v2.values, F.still_at_edge.values)

# --- print side by side
scal = [k for k in R['v2'] if not isinstance(R['v2'][k], (pd.DataFrame, pd.Series))]  # v2 has the >=1000 class
rows = []
for k in scal:
    rows.append({'metric': k, 'v1': R['v1'].get(k), 'v2': R['v2'].get(k)})
S = pd.DataFrame(rows)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500); pd.set_option('display.max_colwidth', 80)


def fmt(v):
    return f'{v:.3f}' if isinstance(v, (float, np.floating)) else str(v)


S['v1'] = S.v1.map(fmt); S['v2'] = S.v2.map(fmt)
print(S.to_string(index=False))
for k in ['lookup', 'ha_per_det', 'ha_per_MW_month', 'median_month']:
    print('\n==', k)
    print(pd.concat({'v1': R['v1'][k], 'v2': R['v2'][k]}, axis=1).round(2).to_string())
print('\nha per MW summed FRP: v1 %.2f  v2 %.2f' % (R['v1']['ha_per_MW'], R['v2']['ha_per_MW']))
S.to_csv(out + '/rerun_v2_scalars.csv', index=False)
pd.concat({'v1': R['v1']['lookup'], 'v2': R['v2']['lookup']}, axis=1).to_csv(out + '/rerun_v2_lookup.csv')
