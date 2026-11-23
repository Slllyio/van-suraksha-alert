"""Numbers for the unseen-fire validation report (see uv_apply.py).  python3 uv_report.py prefix [train_prefix]"""
import sys, json, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
PRE = sys.argv[1]; TP = sys.argv[2] if len(sys.argv) > 2 else None
Fz = pd.read_csv('/mnt/project-files/research/big-fires/results/fires.csv').set_index('fire')
TRAIN = pd.read_parquet('/tmp/claude-0/fronts/mf_fronts.parquet'); MED = float(np.median(TRAIN[TRAIN.active].new24_ha))
rng = np.random.default_rng(0)


def boot(df, fn, n=1000):
    fires = df.fire.unique(); grp = {f: x for f, x in df.groupby('fire')}; v = []
    for _ in range(n):
        s = rng.choice(fires, len(fires)); v.append(fn(pd.concat([grp[f] for f in s])))
    return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]


def w2(p, t):
    return float((np.abs(np.log(np.clip(p, .5, None) / np.clip(t, .5, None))) <= np.log(2)).mean())


def front_stats(f):
    y = (f.true_ha < 2).astype(int)
    o = dict(rows=len(f), fires=int(f.fire.nunique()), median_true_ha=float(f.true_ha.median()), share_stopped=float(y.mean()),
             within2x_model=w2(f.pred_ha, f.true_ha), within2x_median=w2(np.full(len(f), MED), f.true_ha),
             err_log_model=float(np.median(np.abs(np.log1p(f.pred_ha) - np.log1p(f.true_ha)))),
             err_log_median=float(np.median(np.abs(np.log1p(MED) - np.log1p(f.true_ha)))),
             bias_pred_over_true=float(np.exp(np.median(np.log1p(f.pred_ha) - np.log1p(f.true_ha)))),
             spearman=float(spearmanr(f.pred_ha, f.true_ha)[0]) if len(f) > 5 else np.nan)
    if 0 < y.sum() < len(y):
        o['stop_auc_model'] = float(roc_auc_score(y, f.p_stop)); o['stop_auc_no_dots_last'] = float(roc_auc_score(y, -f.n_dots_last))
        o['brier_model'] = float(((f.p_stop - y) ** 2).mean()); o['brier_base_rate'] = float(((y.mean() - y) ** 2).mean())
    return o


F = pd.read_csv(f'{PRE}_apply_fronts.csv'); I = pd.read_csv(f'{PRE}_apply_issues.csv')
F['size'] = pd.cut(Fz.area_ha.reindex(F.fire).values, [0, 50, 100, 200, 1e9], labels=['<50 ha', '50-100', '100-200', '>200'])
I['size'] = pd.cut(Fz.area_ha.reindex(I.fire).values, [0, 50, 100, 200, 1e9], labels=['<50 ha', '50-100', '100-200', '>200'])
res = dict(train_median_ha=MED, fronts=front_stats(F))
res['fronts_ci'] = dict(within2x_model=boot(F, lambda x: w2(x.pred_ha, x.true_ha)), within2x_median=boot(F, lambda x: w2(np.full(len(x), MED), x.true_ha)),
                        stop_auc=boot(F, lambda x: roc_auc_score((x.true_ha < 2).astype(int), x.p_stop)))
res['by_size'] = {str(k): front_stats(x) for k, x in F.groupby('size', observed=True)}
res['by_kind'] = {k: front_stats(x) for k, x in F.groupby('kind')}
res['by_season'] = {int(k): front_stats(x) for k, x in F.groupby('season')}
# calibration of the stop chance
F['bin'] = pd.cut(F.p_stop, [0, .2, .4, .6, .8, 1.0], include_lowest=True)
res['stop_calibration'] = [dict(bin=str(b), n=len(x), said=round(float(x.p_stop.mean()), 2), happened=round(float((x.true_ha < 2).mean()), 2))
                           for b, x in F.groupby('bin', observed=True)]
# growth band coverage by predicted size
F['gbin'] = pd.cut(F.pred_ha, [-1, 2, 5, 10, 20, 50, 1e9])
res['growth_by_pred'] = [dict(bin=str(b), n=len(x), pred_median=round(float(x.pred_ha.median()), 1), true_median=round(float(x.true_ha.median()), 1),
                              in_band=round(w2(x.pred_ha, x.true_ha), 2)) for b, x in F.groupby('gbin', observed=True)]
# maps
mcols = ['sor_tool', 'sor_foot', 'sor_blob_same_area', 'sor_blob_median']
res['maps'] = {c: float(I[c].median()) for c in mcols}
res['maps_mean_by_fire'] = {c: float(I.groupby('fire')[c].mean().mean()) for c in mcols}
res['maps_ci_tool_minus_foot'] = boot(I, lambda x: (x.sor_tool - x.sor_foot).mean())
res['maps_ci_tool_minus_blob_median'] = boot(I, lambda x: (x.sor_tool - x.sor_blob_median).mean())
res['maps_ci_tool_minus_blob_same_area'] = boot(I, lambda x: (x.sor_tool - x.sor_blob_same_area).mean())
res['maps_size_ratio_median'] = float(np.median((I.fc_ha) / I.truth_ha.clip(1)))
res['maps_by_size'] = {str(k): {c: round(float(x[c].median()), 3) for c in mcols} | dict(issues=len(x)) for k, x in I.groupby('size', observed=True)}
res['issues'] = len(I); res['fires'] = int(I.fire.nunique())
# new-front band
res['far1k_share_pooled'] = float(I.far1k_ha.sum() / max(I.new24_ha.sum(), 1e-9))
res['far_in_band_share'] = float(I.far_in_band_ha.sum() / max(I.far1k_ha.sum(), 1e-9))
res['band_hit_rate_pooled'] = float(I.far_in_band_ha.sum() / I.band_ha.sum())
if TP:
    F2 = pd.read_csv(f'{TP}_apply_fronts.csv'); I2 = pd.read_csv(f'{TP}_apply_issues.csv')
    res['train_fires_same_tool'] = dict(fronts=front_stats(F2), maps={c: float(I2[c].median()) for c in mcols},
                                        far1k_share_pooled=float(I2.far1k_ha.sum() / I2.new24_ha.sum()))
json.dump(res, open(f'{PRE}_report.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
