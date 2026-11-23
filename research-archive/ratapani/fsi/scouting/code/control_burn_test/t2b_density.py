"""t2b: is the excess-over-background estimate biased by fire density? The flag needs 'nothing within 1 km on days -2..+3', which is
easier to pass when few fires burn nearby (late Feb, June) than in the crowded Mar-May background. Here the background flag rate is
matched on local fire density: other VIIRS points within 10 km on fire-days -7..+7 (own cluster excluded), in 7 bins, per season
(bins with <30 background points pooled over seasons). Placebo: June and 1-15 Mar, where planned burning is not expected.
Also: season-level bootstrap (resample seasons) for the pooled late-Feb precision, and the same for the learned alternative.
Output: out/density_matched.csv, out/season_bootstrap.csv; scratch r21_cb/density.parquet"""
import numpy as np, pandas as pd, json
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
d = pd.read_parquet(S + 'r15_firms_nd/pts_feat2.parquet', columns=['x', 'y', 'season', 'fday', 'cid'])
c = pd.read_parquet(S + 'r21_cb/clusters_t1.parquet')
f = pd.read_parquet(S + 'r21_cb/cluster_flags.parquet')
c = c.merge(f[['cid', 'grp', 'flag_cur', 'flag_live', 'flag_refit_ho', 'p_learned']], on='cid')
c = c[c.fn != 'x'].reset_index(drop=True)
try:
    c = c.merge(pd.read_parquet(S + 'r21_cb/density.parquet'), on='cid')
except Exception:
    key = d.season.astype(np.int64) * 1000 + d.fday
    ix = d.groupby(key).indices; X = d[['x', 'y']].values
    tr = {k: cKDTree(X[i]) for k, i in ix.items()}
    ck = (c.season.astype(np.int64) * 1000 + c.fday).values; C = c[['x', 'y']].values
    dens = np.zeros(len(c))
    for k in np.unique(ck):
        rows = np.where(ck == k)[0]
        for o in range(-7, 8):
            t = tr.get(k + o)
            if t is None: continue
            dens[rows] += t.query_ball_point(C[rows], 10000, return_length=True)
    dens -= c.n.values   # own cluster (centre within 10 km of all its points, to within 750 m)
    pd.DataFrame({'cid': c.cid, 'dens10k': np.clip(dens, 0, None)}).to_parquet(S + 'r21_cb/density.parquet')
    c['dens10k'] = np.clip(dens, 0, None)
edges = [-1, 0, 2, 5, 10, 25, 60, 1e9]
c['db'] = np.digitize(c.dens10k, edges[1:-1], right=True)
BG = '5 16 Mar-May'; w = c.n.values.astype(float)
print(c.groupby('fn').dens10k.median(), pd.crosstab(c.fn, c.db, values=c.n, aggfunc='sum', normalize='index').round(3))


def excess(mask, win, ww=w, seasons=None, matched=True):
    sel = np.ones(len(c), bool) if seasons is None else np.isin(c.season.values, seasons)
    t = pd.DataFrame({'s': c.season.values, 'b': c.db.values, 'fn': c.fn.values, 'w': ww, 'f': ww * mask})[sel]
    a = t[t.fn == win].groupby(['s', 'b'])[['w', 'f']].sum(); g = t[t.fn == BG].groupby(['s', 'b'])[['w', 'f']].sum()
    gp = t[t.fn == BG].groupby('b')[['w', 'f']].sum()
    if matched:
        rate = (g.f / g.w).where(g.w >= 30)
        pooled = (gp.f / gp.w)
        r = rate.reindex(a.index); r = r.fillna(pd.Series(a.index.get_level_values('b').map(pooled), index=a.index))
    else:
        gs = t[t.fn == BG].groupby('s')[['w', 'f']].sum(); r = pd.Series(a.index.get_level_values('s').map(gs.f / gs.w), index=a.index)
    ok = r.notna()
    F, N, E = a.f[ok].sum(), a.w[ok].sum(), (r * a.w)[ok].sum()
    return dict(pts=N, flagged=F, expected_wildfire_flagged=E, precision=(F - E) / F if F else np.nan, est_control_caught=F - E)


# learned (held-out) mask: per fold threshold, chosen on training seasons by the plain estimator (as in t2)
seasons = np.arange(2014, 2027); p = c.p_learned.values
m_learn = np.zeros(len(c), bool)
for h in seasons:
    trn = [s for s in seasons if s != h]; best, bt = -1, None
    for thr in np.arange(0.5, 0.99, 0.01):
        e = excess(p >= thr, '3 15-28 Feb', seasons=trn, matched=False)
        if e['precision'] >= 0.65 and e['est_control_caught'] > best: best, bt = e['est_control_caught'], thr
    m_learn |= (p >= bt) & (c.season.values == h)
masks = {'current rule': c.flag_cur.values, 'current live tag': c.flag_live.values, 'refit rule (held-out)': c.flag_refit_ho.values,
         'learned (held-out)': m_learn}
rng = np.random.default_rng(7); uf, fi = np.unique(c.fire_id.values, return_inverse=True)
rows = []
for nm, m in masks.items():
    for win in ['1 Jan', '2 1-14 Feb', '3 15-28 Feb', '4 1-15 Mar', '6 Jun']:
        for matched in [False, True]:
            r = excess(m, win, matched=matched)
            bs = []
            for _ in range(150):
                ww = w * rng.poisson(1, len(uf))[fi]; bs.append(excess(m, win, ww=ww, matched=matched)['precision'])
            # season bootstrap
            ss = []
            for _ in range(300):
                sd = rng.choice(seasons, len(seasons)); ww = w * pd.Series(sd).value_counts().reindex(c.season.values).fillna(0).values
                ss.append(excess(m, win, ww=ww, matched=matched)['precision'])
            rows.append(dict(rule=nm, window=win, background='density-matched' if matched else 'plain (as r15)', **r,
                             fire_lo=np.nanpercentile(bs, 2.5), fire_hi=np.nanpercentile(bs, 97.5),
                             season_lo=np.nanpercentile(ss, 2.5), season_hi=np.nanpercentile(ss, 97.5)))
R = pd.DataFrame(rows); R.to_csv(O + 'density_matched.csv', index=False)
pd.set_option('display.width', 250); print(R.round(3).to_string())
# per group, density matched, current rule, late Feb
g = []
for gv in sorted(c.grp.unique()):
    sub = c.grp.values == gv
    for nm in ['current rule', 'learned (held-out)']:
        for win in ['3 15-28 Feb', '4 1-15 Mar']:
            r = excess(masks[nm] & sub, win, ww=w * sub, matched=True)
            bs = [excess(masks[nm] & sub, win, ww=w * sub * rng.poisson(1, len(uf))[fi], matched=True)['precision'] for _ in range(150)]
            g.append(dict(group=gv, rule=nm, window=win, **r, lo=np.nanpercentile(bs, 2.5), hi=np.nanpercentile(bs, 97.5)))
Gd = pd.DataFrame(g); Gd.to_csv(O + 'density_matched_groups.csv', index=False); print(Gd.round(3).to_string())
c[['cid']].assign(flag_learn_ho=m_learn).to_parquet(S + 'r21_cb/learn_mask.parquet')
