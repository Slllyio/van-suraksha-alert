"""Summarise the learned footprint scoring (footprint.py score). Usage: foot_stats.py foot_score_0.parquet,..."""
import numpy as np, pandas as pd, sys, json
d = pd.concat([pd.read_parquet(f) for f in sys.argv[1].split(',')], ignore_index=True)
print('fires', len(d), 'seasons', sorted(d.season.unique()))
def block(g, label):
    r = dict(n=len(g))
    for k in ['sor_learn', 'sor_circle', 'sor_phys', 'sor_learn_free', 'sor_circle_free', 'sor_phys_free', 'sor_phys48', 'auc_learn', 'auc_circle', 'auc_phys']:
        r[k] = round(float(g[k].mean()), 3)
    r['learn>circle'] = round(float((g.sor_learn > g.sor_circle).mean()), 3); r['learn>phys'] = round(float((g.sor_learn > g.sor_phys).mean()), 3)
    r['area_ratio_med'] = round(float((g.n_pred / g.scar_px).median()), 2); r['area_ratio_q'] = [round(float(x), 2) for x in (g.n_pred / g.scar_px).quantile([.25, .75])]
    r['area_corr_log'] = round(float(np.corrcoef(np.log(g.n_pred.clip(lower=1)), np.log(g.scar_px))[0, 1]), 3)
    r['phys48_ratio_med'] = round(float((g.area48 / g.scar_px).median()), 2)
    h = g[g.n_later.notna() & (g.n_later > 0)]
    if len(h):
        r['later_pass_hits'] = dict(n_det=int(h.n_later.sum()), learn=round(float(h.hit_learn.sum() / h.n_later.sum()), 3), circle=round(float(h.hit_circle.sum() / h.n_later.sum()), 3), phys=round(float(h.hit_phys.sum() / h.n_later.sum()), 3))
    print(f'\n== {label} ==\n' + json.dumps(r))
    return r
res = {'all': block(d, 'all fires')}
for lo, hi, lab in [(125, 500, '5-20 ha'), (500, 1250, '20-50 ha'), (1250, 10 ** 9, '>=50 ha')]:
    res[lab] = block(d[(d.scar_px >= lo) & (d.scar_px < hi)], f'scar {lab}')
res['multi_pass'] = block(d[d.n_pass >= 2], 'fires with >=2 passes')
res['single_pass'] = block(d[d.n_pass == 1], 'single-pass fires')
print('\nby season (sor_learn / circle / phys):')
print(d.groupby('season')[['sor_learn', 'sor_circle', 'sor_phys', 'sor_learn_free', 'sor_phys48']].mean().round(3).to_string())
json.dump(res, open('/tmp/claude-0/spread/data/foot_stats.json', 'w'), indent=1)
