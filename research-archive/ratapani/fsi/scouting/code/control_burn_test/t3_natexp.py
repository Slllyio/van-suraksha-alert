"""t3: natural experiment. Kuno, Satpura and Kanha have seasons with a big pre-15 Feb burning programme ('burn years': early share of the
season's Oct-Jun points >= 20%) and seasons without. If the flag tracks planned burning, burn years should show (a) a higher core-flag
share in Jan-14 Feb and (b) more flagged excess in 15-28 Feb, relative to the same reserve's other years and to the rest of MP in the
same seasons (difference in differences). Bootstrap by fire (Poisson weights, 400 reps).
Output: out/natexp.csv"""
import numpy as np, pandas as pd
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
c = pd.read_parquet(S + 'r21_cb/cluster_flags.parquet')
c = c[c.season >= 2014]
early = c.fn.isin(['0 Oct-Dec', '1 Jan', '2 1-14 Feb'])
sh = c.assign(e=c.n * early).groupby(['Division', 'season'])[['e', 'n']].sum()
sh['early_share'] = sh.e / sh.n
RES = ['Kuno_Palpur', 'Satpura_TR', 'Kanha Tiger Reserve']
print(sh.loc[RES].early_share.unstack().round(2))
burn = (sh.early_share >= 0.20) & (sh.n >= 50)
c = c.join(burn.rename('burn_year'), on=['Division', 'season'])
rng = np.random.default_rng(3)
uf, fi = np.unique(c.fire_id.values, return_inverse=True)
W = rng.poisson(1, (400, len(uf))).astype(np.float32)


def stats(df, ww):
    """per (season): Jan-14Feb flag share, late-Feb excess share (f - b), late-Feb flagged pts, precision."""
    d = df.assign(w=ww, fw=ww * df.flag_cur)
    t = d.groupby(['season', 'fn'])[['w', 'fw']].sum().unstack('fn').fillna(0)
    jan = (t[('fw', '1 Jan')] + t[('fw', '2 1-14 Feb')]).sum() / max((t[('w', '1 Jan')] + t[('w', '2 1-14 Feb')]).sum(), 1e-9)
    N, F = t[('w', '3 15-28 Feb')], t[('fw', '3 15-28 Feb')]
    b = t[('fw', '5 16 Mar-May')] / t[('w', '5 16 Mar-May')].replace(0, np.nan)
    ok = (N > 0) & b.notna()
    TP = (F - b * N)[ok].sum()
    return dict(jan_flag_share=jan, lf_pts=N[ok].sum(), lf_flag_share=F[ok].sum() / max(N[ok].sum(), 1e-9),
                lf_excess_share=TP / max(N[ok].sum(), 1e-9), lf_precision=TP / F[ok].sum() if F[ok].sum() else np.nan,
                lf_excess_pts_per_season=TP / max(ok.sum(), 1), seasons=int(ok.sum()))


rows = []
for dv in RES:
    for by in [True, False]:
        m = ((c.Division == dv) & (c.burn_year == by)).values
        if not m.any(): continue
        base = stats(c[m], c.n.values[m].astype(float))
        bs = [stats(c[m], (c.n.values * W[r][fi])[m]) for r in range(200)]
        r = dict(reserve=dv, burn_year=by, seasons_list=sorted(c[m].season.unique().tolist()), **base)
        for k in ['jan_flag_share', 'lf_excess_share', 'lf_precision']:
            v = np.array([b[k] for b in bs]); r[k + '_lo'], r[k + '_hi'] = np.nanpercentile(v, [2.5, 97.5])
        rows.append(r)
R = pd.DataFrame(rows)
# DiD: (reserve burn years - reserve other years) - (rest of MP in those seasons - rest of MP in the other seasons), late-Feb excess share
did = []
for dv in RES:
    by = set(c[(c.Division == dv) & (c.burn_year == True)].season.unique()); ny = set(c[(c.Division == dv) & (c.burn_year == False)].season.unique())
    def dd(ww):
        v = {}
        for nm, mm in [('rb', (c.Division == dv) & c.season.isin(by)), ('rn', (c.Division == dv) & c.season.isin(ny)),
                       ('ob', (~c.Division.isin(RES)) & c.season.isin(by)), ('on', (~c.Division.isin(RES)) & c.season.isin(ny))]:
            mm = mm.values; v[nm] = stats(c[mm], ww[mm])['lf_excess_share']
        return (v['rb'] - v['rn']) - (v['ob'] - v['on']), v
    est, parts = dd(c.n.values.astype(float))
    bs = [dd(c.n.values * W[r][fi])[0] for r in range(100)]
    did.append(dict(reserve=dv, burn_seasons=sorted(by), did_lf_excess_share=est, lo=np.nanpercentile(bs, 2.5), hi=np.nanpercentile(bs, 97.5), **{k: v for k, v in parts.items()}))
D = pd.DataFrame(did)
pd.concat([R, D], ignore_index=True).to_csv(O + 'natexp.csv', index=False)
print(R.round(3).to_string()); print(D.round(3).to_string())
