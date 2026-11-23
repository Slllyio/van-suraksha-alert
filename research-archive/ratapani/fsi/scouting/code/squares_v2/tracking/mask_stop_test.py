"""What the VIIRS fire masks add to "has this front stopped?" beyond the alert dots.

Unit: one fire x one VIIRS pass after the fire's first alert and within 36 h of its latest alert, that shows NO fire pixel
in the front zone (mask pixels within 750 m of the fire's earlier alerts). Dots alone see all of these as "no dot".
The mask splits them: CLEAR (>=80% of front-zone pixels class 3/5: looked, saw no fire), BLIND (>=50% cloud, glint,
unclassified, bow-tie or not processed), PARTIAL (rest).
Outcome: the fire is seen again later (any alert of the fire after the pass, any sensor; fire_alerts.csv).
Also: a fire-level held-out test (5-fold by fire) of a logistic stop model on hours since last alert + view angle
(dots only) against the same + clear/blind shares (masks), scored by AUC and log loss.
Inputs : results/mask_fire_pass_summary.csv (build_mask_tables.py). Output: results/mask_stop_test.json
"""
import os, json, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.model_selection import GroupKFold
HERE = os.path.dirname(os.path.abspath(__file__)); RES = f'{HERE}/results'
S = pd.read_csv(f'{RES}/mask_fire_pass_summary.csv', parse_dates=['t_pass'])
S = S[(S.n_front >= 3) & S.hours_since_last_alert.between(0, 36)].copy()
blind = S.n_cloud + S.n_noinfo + S.n_missing
S['state'] = np.where(S.n_fire > 0, 'fire seen', np.where(S.n_clear >= 0.8 * S.n_front, 'clear, no fire',
                      np.where(blind >= 0.5 * S.n_front, 'blind (cloud/bow-tie/etc)', 'partial')))
out = dict(rows=int(len(S)), fires=int(S.fire.nunique()), table={})
for k, g in S.groupby('state'):
    out['table'][k] = dict(passes=int(len(g)), fires=int(g.fire.nunique()), seen_again_later=round(float(g.seen_later.mean()), 3))
nd = S[S.state != 'fire seen']
out['no_dot_total'] = dict(passes=int(len(nd)), seen_again_later=round(float(nd.seen_later.mean()), 3),
                           share_blind=round(float((nd.state == 'blind (cloud/bow-tie/etc)').mean()), 3),
                           share_clear=round(float((nd.state == 'clear, no fire').mean()), 3))
# by hours since the last alert
nd = nd.assign(hb=pd.cut(nd.hours_since_last_alert, [0, 14, 26, 36], labels=['<14 h', '14-26 h', '26-36 h']))
out['by_hours'] = {f'{h} | {s}': dict(passes=int(len(g)), seen_again=round(float(g.seen_later.mean()), 3))
                   for (h, s), g in nd.groupby(['hb', 'state'], observed=True) if len(g) >= 20}
# held-out stop model on no-dot passes
D = nd.copy(); D['clear_sh'] = D.n_clear / D.n_front; D['blind_sh'] = (D.n_cloud + D.n_noinfo + D.n_missing) / D.n_front
D['h'] = D.hours_since_last_alert; D['vza'] = D.vza_med.fillna(D.vza_med.median()); y = D.seen_later.astype(int).values
res = {}
for name, cols in [('dots only (hours since last dot, view angle, satellite)', ['h', 'vza']), ('+ mask (clear and blind shares)', ['h', 'vza', 'clear_sh', 'blind_sh'])]:
    X = pd.get_dummies(D[cols + ['sensor']], columns=['sensor'], dtype=float).values; p = np.zeros(len(D))
    for tr, te in GroupKFold(5).split(X, y, D.fire):
        p[te] = LogisticRegression(max_iter=1000).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    res[name] = dict(auc=round(float(roc_auc_score(y, p)), 3), log_loss=round(float(log_loss(y, p)), 4))
    if 'mask' in name:
        D['p'] = p; D['bin'] = pd.cut(p, [0, .2, .4, .6, .8, 1])
        res[name]['calibration'] = {str(b): dict(n=int(len(g)), said=round(float(g.p.mean()), 2), real=round(float(g.seen_later.mean()), 2))
                                    for b, g in D.groupby('bin', observed=True)}
out['heldout_stop_model'] = res
# fire level: first no-dot pass after the last-ever alert vs before it
json.dump(out, open(f'{RES}/mask_stop_test.json', 'w'), indent=1); print(json.dumps(out, indent=1))
