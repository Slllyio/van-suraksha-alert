"""t2c: per held-out season, density-matched precision of the current rule, the live tag and the learned alternative (15-28 Feb),
fire bootstrap CIs. Season 2026 (Oct 2025-Jun 2026) is the forward test: the learned model and refit for it saw only 2014-25.
Also the live tag's cost: share of wildfire points tagged (density-matched background), flips after 3 days. Output: out/season_density.csv"""
import numpy as np, pandas as pd, importlib.util, sys
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
c = pd.read_parquet(S + 'r21_cb/clusters_t1.parquet')
f = pd.read_parquet(S + 'r21_cb/cluster_flags.parquet')
c = c.merge(f[['cid', 'flag_cur', 'flag_live', 'flag_refit_ho']], on='cid').merge(pd.read_parquet(S + 'r21_cb/density.parquet'), on='cid')
c = c.merge(pd.read_parquet(S + 'r21_cb/learn_mask.parquet'), on='cid')
c = c[c.fn != 'x'].reset_index(drop=True)
edges = [-1, 0, 2, 5, 10, 25, 60, 1e9]; c['db'] = np.digitize(c.dens10k, edges[1:-1], right=True)
BG = '5 16 Mar-May'; w = c.n.values.astype(float)
gp_all = None


def excess(mask, win, ww, sel):
    t = pd.DataFrame({'s': c.season.values, 'b': c.db.values, 'fn': c.fn.values, 'w': ww, 'f': ww * mask})
    gpool = t[t.fn == BG].groupby('b')[['w', 'f']].sum()
    t = t[sel]
    a = t[t.fn == win].groupby(['s', 'b'])[['w', 'f']].sum(); g = t[t.fn == BG].groupby(['s', 'b'])[['w', 'f']].sum()
    r = (g.f / g.w).where(g.w >= 30).reindex(a.index)
    r = r.fillna(pd.Series(a.index.get_level_values('b').map(gpool.f / gpool.w), index=a.index))
    F, N, E = a.f.sum(), a.w.sum(), (r * a.w).sum()
    return F, N, E


rng = np.random.default_rng(11); uf, fi = np.unique(c.fire_id.values, return_inverse=True)
rows = []
for s in range(2014, 2027):
    sel = c.season.values == s
    for nm, col in [('current rule', 'flag_cur'), ('current live tag', 'flag_live'), ('learned (held-out)', 'flag_learn_ho')]:
        m = c[col].values
        F, N, E = excess(m, '3 15-28 Feb', w, sel)
        bs = []
        for _ in range(150):
            Fb, Nb, Eb = excess(m, '3 15-28 Feb', w * rng.poisson(1, len(uf))[fi], sel); bs.append((Fb - Eb) / Fb if Fb else np.nan)
        rows.append(dict(season=s, rule=nm, pts=N, flagged=F, precision=(F - E) / F if F else np.nan, lo=np.nanpercentile(bs, 2.5),
                         hi=np.nanpercentile(bs, 97.5), est_control_caught=F - E))
R = pd.DataFrame(rows); R.to_csv(O + 'season_density.csv', index=False)
print(R.pivot(index='season', columns='rule', values=['precision', 'lo', 'hi', 'flagged']).round(2).to_string())
# live tag cost, density matched
sel = np.ones(len(c), bool)
for nm, col in [('final (after 3 days)', 'flag_cur'), ('live (day 0)', 'flag_live')]:
    F, N, E = excess(c[col].values, '3 15-28 Feb', w, sel)
    print(nm, 'late-Feb pts', N, 'tagged', F, 'expected wildfire tagged', round(E), 'share of late-Feb pts that are tagged wildfires', round(E / N, 3))
lf = c.fn.values == '3 15-28 Feb'
print('live tags later cleared', 1 - (w * (c.flag_cur & c.flag_live))[lf].sum() / (w * c.flag_live)[lf].sum())
