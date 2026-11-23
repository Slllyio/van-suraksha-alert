"""Pick a method with seasons held out, and report all methods on the photos.
Choice rule: highest mean pixel accuracy on the other seasons' photos (leave one season out); the held-out season is
scored with the method chosen without it. Differences vs the spread review's map ('base') and 'nn': 95% range by
resampling fires. Out: results/photo_summary.csv, results/photo_choice.json"""
import json, numpy as np, pandas as pd
R = '/mnt/project-files/research/fire-continuity/results'
X = pd.read_parquet(f'{R}/photo_scores.parquet')
meth = [c[4:] for c in X.columns if c.startswith('acc_')]
X['both'] = (X.looks_before > 0) & (X.looks_after > 0)
cand = [m for m in meth if m not in ('base',)]
lo = []
for s in sorted(X.season.unique()):
    tr = X[X.season != s]; best = max(cand, key=lambda m: tr['acc_' + m].mean())
    lo.append(X[X.season == s].assign(acc_chosen=lambda g: g['acc_' + best], auc_chosen=lambda g: g['auc_' + best],
                                      frac_chosen=lambda g: g['frac_' + best], accU_chosen=lambda g: g['accU_' + best], chosen=best))
X = pd.concat(lo); meth = meth + ['chosen']
rows = []
for m in meth:
    r = dict(method=m)
    for nm, g in [('all', X), ('both_sides', X[X.both]), ('big', X[X.big])]:
        r[f'acc_{nm}'] = g['acc_' + m].mean(); r[f'auc_{nm}'] = g['auc_' + m].mean()
        r[f'share_err_{nm}'] = (g['frac_' + m] - g.obs_frac).abs().median()
    r['acc_undecided'] = X['accU_' + m].mean()
    rows.append(r)
S = pd.DataFrame(rows).set_index('method').round(3).sort_values('acc_all', ascending=False); S.to_csv(f'{R}/photo_summary.csv'); print(S.to_string())
rng = np.random.default_rng(0); fires = X.fire.unique(); out = dict(chosen_by_season=X.groupby('season').chosen.first().to_dict(), n_photos=len(X), n_fires=len(fires),
      n_both_sides=int(X.both.sum()), n_big=int(X.big.sum()))
for ref in ['base', 'nn']:
    for nm, msk in [('all', np.ones(len(X), bool)), ('both_sides', X.both.values)]:
        g = X[msk].assign(dif=lambda q: q.acc_chosen - q['acc_' + ref]).groupby('fire').dif.agg(['sum', 'size'])
        dd = []
        for _ in range(1000):
            i = rng.integers(0, len(g), len(g)); dd.append(g['sum'].values[i].sum() / g['size'].values[i].sum())
        out[f'chosen_minus_{ref}_{nm}'] = [round(float(np.quantile(dd, q)), 3) for q in (.025, .5, .975)]
print(json.dumps(out, indent=1, default=str)); json.dump(out, open(f'{R}/photo_choice.json', 'w'), indent=1, default=str)
