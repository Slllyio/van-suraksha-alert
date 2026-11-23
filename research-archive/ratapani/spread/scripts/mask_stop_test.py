"""Do the VIIRS raw fire masks ("looked, saw no fire") improve the 24 h forecast on the unseen fires? (Oct 17; Akkshay saved the
EARTHDATA_TOKEN secret, "now do"; masks pulled in thread "VIIRS fire masks and statewide 70 m run" with pull_fire_masks.py.)
Per forecast issue (fire, VIIRS look k, time tk) and per active front (dots in the last 2 looks, fronts as in mf_tracker: 750 m link):
  evidence = every VIIRS pass over the front AFTER the front's last dot and up to tk + 10 min (so only what is known at issue time);
             mask pixels within 400 m of the front's last-look dots: fire (7-9), clear (3, 5), no info (2, 4, 6), missing (0, 1).
  seen_clear = some such pass has >= 80% of those pixels clear and no fire pixel.
Map rules (blocks counted as burned; same truth as uv_apply.py):
  rule      : 24.1 ha per active front, nearest to dots                           (0.477 on unseen)
  drop      : 0 ha for active fronts seen clear
  half      : 12 ha for them
Stop (new24 < 2 ha near the front): stop rate seen-clear vs not; all-fire LOSO stop chance with and without seen_clear
(logistic on logit p_stop + seen_clear + n clear passes, fitted with each season held out).
  python3 mask_stop_test.py RESULTS_DIR   (holds mask_pixels_near_fires.parquet from the fire-mask thread)
"""
import sys, os, pickle, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from pyproj import Transformer
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
MD = sys.argv[1]; X0, Y0 = 737300.0, 2560500.0; MED = 24.1; LINK = 750.0; NEAR = 400.0; CLEAR_SHARE = .8
MP_ = pd.read_parquet(f'{MD}/mask_pixels_near_fires.parquet', columns=['fire', 'pass_key', 't_pass', 'lat', 'lon', 'cls'])
MP_['t_pass'] = pd.to_datetime(MP_.t_pass); PLAN = MP_.groupby(['fire', 'pass_key'], as_index=False).t_pass.first().rename(columns={'t_pass': 't_utc'})
PIX = {k: g for k, g in MP_.groupby('pass_key')}
I = pd.read_parquet('/tmp/claude-0/unseen/u_issues.parquet'); M = pickle.load(open('/tmp/claude-0/unseen/u_maps.pkl', 'rb'))
FR = pd.read_csv('/tmp/claude-0/unseen/u_apply_loso_fronts.csv')
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
TR = Transformer.from_crs(4326, 32643, always_xy=True)
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
_cache = {}


def crop(pk):
    if pk in _cache: return _cache[pk]
    g = PIX.get(pk); out = None
    if g is not None and len(g):
        x, y = TR.transform(g.lon.values.astype(float), g.lat.values.astype(float)); out = (np.c_[x, y], g.cls.values)
    if len(_cache) > 400: _cache.clear()
    _cache[pk] = out; return out


def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]


rows, fr_rows = [], []
fires = sorted(set(I.fire) & set(PLAN.fire))
for fire in fires:
    pl = PLAN[PLAN.fire == fire].sort_values('t_utc')
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    for it in I[I.fire == fire].itertuples():
        k = it.k; kn = d[d.lk <= k].reset_index(drop=True); tk = kn[kn.lk == k].t.max(); xy = kn[['x', 'y']].values
        lab = clusters(xy); kn['front'] = lab; act = sorted(kn[kn.lk >= k - 1].front.unique())
        dd, near = cKDTree(xy).query(P); own = lab[near]; foot = dd <= 265
        truth = dom & (Tg <= it.th + 24); new = dom & (Tg > it.th) & (Tg <= it.th + 24)
        ha = {}
        for f in act:
            g = kn[kn.front == f]; tl = g.t.max(); last = g[g.lk == g.lk.max()][['x', 'y']].values
            ps = pl[(pl.t_utc > tl + pd.Timedelta(minutes=10)) & (pl.t_utc <= tk + pd.Timedelta(minutes=10))]
            n_pass = n_clear_pass = n_fire_pass = n_noinfo_pass = 0
            for pk in ps.pass_key:
                c = crop(pk)
                if c is None: continue
                n_pass += 1; dn = cKDTree(last).query(c[0])[0]; m = c[1][dn <= NEAR]
                if not len(m): continue
                fire_px = np.isin(m, (7, 8, 9)).sum(); clr = np.isin(m, (3, 5)).mean()
                if fire_px: n_fire_pass += 1
                elif clr >= CLEAR_SHARE: n_clear_pass += 1
                else: n_noinfo_pass += 1
            true_ha = float((new & (own == f) & (dd <= 1000)).sum() * .04)
            r = FR[(FR.fire == fire) & (FR.k == k) & (FR.n_dots == len(g)) & (FR.n_dots_last == int((g.lk == k).sum()))]
            fr_rows.append(dict(fire=fire, season=it.season, k=k, front=int(f), n_dots=len(g), dots_at_k=int((g.lk == k).sum()),
                                hours_since_dot=(tk - tl).total_seconds() / 3600, passes_after=len(ps), passes_loaded=n_pass,
                                clear_passes=n_clear_pass, fire_passes=n_fire_pass, noinfo_passes=n_noinfo_pass,
                                seen_clear=bool(n_clear_pass and not n_fire_pass), true_ha=true_ha,
                                p_stop=float(r.p_stop.iloc[0]) if len(r) == 1 else np.nan))
            ha[f] = fr_rows[-1]['seen_clear']
        def place(n):
            s = np.where(foot, -1, dd); mk = np.zeros(len(s), bool); mk[np.argsort(s, kind='stable')[:n]] = True; return mk
        nclr = sum(ha.values()); nact = len(act)
        rows.append(dict(fire=fire, season=it.season, k=k, n_active=nact, n_seen_clear=nclr,
                         rule=so(place(int(foot.sum() + MED * nact / .04)), truth),
                         drop=so(place(int(foot.sum() + MED * (nact - nclr) / .04)), truth),
                         half=so(place(int(foot.sum() + MED * (nact - nclr / 2) / .04)), truth)))
R = pd.DataFrame(rows); F = pd.DataFrame(fr_rows)
R.to_csv('/tmp/claude-0/unseen/mask_issues.csv', index=False); F.to_csv('/tmp/claude-0/unseen/mask_fronts.csv', index=False)
res = dict(fires=int(R.fire.nunique()), issues=len(R), active_fronts=len(F), fronts_with_a_pass_after_last_dot=int((F.passes_loaded > 0).sum()),
           fronts_seen_clear=int(F.seen_clear.sum()), issues_with_a_clear_front=int((R.n_seen_clear > 0).sum()))
F['stopped'] = F.true_ha < 2
for name, x in [('seen_clear', F[F.seen_clear]), ('pass_saw_fire', F[F.fire_passes > 0]), ('no_info_or_no_pass', F[~F.seen_clear & (F.fire_passes == 0)])]:
    res[f'stop_rate_{name}'] = dict(n=len(x), stopped=round(float(x.stopped.mean()), 3) if len(x) else None, median_true_ha=round(float(x.true_ha.median()), 1) if len(x) else None)
rng = np.random.default_rng(0)
for c in ['rule', 'drop', 'half']:
    res[c] = round(float(R[c].median()), 4)
f = R.groupby('fire')[['rule', 'drop', 'half']].mean()
for c in ['drop', 'half']:
    dl = (f[c] - f.rule).values
    res[f'{c}_minus_rule_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
    res[f'{c}_better/worse_fires'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
S = R[R.n_seen_clear > 0]
if len(S): res['only_issues_with_a_clear_front'] = {c: round(float(S[c].median()), 4) for c in ['rule', 'drop', 'half']} | dict(n=len(S))
# stop chance with the mask evidence, each season held out
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
G = F.dropna(subset=['p_stop']).copy(); G['lp'] = np.log(G.p_stop.clip(.01, .99) / (1 - G.p_stop.clip(.01, .99)))
X = np.c_[G.lp, G.seen_clear.astype(float), G.clear_passes, G.fire_passes]; y = G.stopped.astype(int).values; G['p_new'] = np.nan
for s in G.season.unique():
    tr = (G.season != s).values
    if y[tr].min() == y[tr].max(): continue
    G.loc[~tr, 'p_new'] = LogisticRegression(max_iter=500).fit(X[tr], y[tr]).predict_proba(X[~tr])[:, 1]
G = G.dropna(subset=['p_new'])
if len(G) > 20 and G.stopped.nunique() == 2:
    res['stop_auc_model'] = round(float(roc_auc_score(G.stopped, G.p_stop)), 3); res['stop_auc_model_plus_masks'] = round(float(roc_auc_score(G.stopped, G.p_new)), 3)
    res['stop_brier_model'] = round(float(((G.p_stop - G.stopped) ** 2).mean()), 4); res['stop_brier_plus_masks'] = round(float(((G.p_new - G.stopped) ** 2).mean()), 4)
    G['bin'] = pd.cut(G.p_new, [0, .2, .4, .6, .8, 1], include_lowest=True)
    res['calibration_plus_masks'] = [dict(bin=str(b), n=len(z), said=round(float(z.p_new.mean()), 2), happened=round(float(z.stopped.mean()), 2)) for b, z in G.groupby('bin', observed=True)]
json.dump(res, open('/tmp/claude-0/unseen/mask_stop_test.json', 'w'), indent=1); print(json.dumps(res, indent=1))
