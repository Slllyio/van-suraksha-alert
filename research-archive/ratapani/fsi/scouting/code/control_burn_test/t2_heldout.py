"""t2: held-out-by-season test of the control-burn flag, threshold refits, a learned alternative, live (provisional) tag costs.
Truth is NOT available here: 'precision' = excess-over-background estimate, (f - b) / f, where f = flagged share of points in the
window and b = flagged share in 16 Mar-31 May of the SAME season(s) (the wildfire background). Bootstrap = Poisson weights by fire
(fire = clusters chained within 1 km on consecutive days), 400 replicates, stratified by season.
Outputs (code/control_burn_test/out/): rule_grid_by_season.parquet (small), loso_folds.csv, heldout_fortnight.csv, heldout_groups.csv,
live_tag.csv, learned_vs_rule.csv, bias_checks.csv."""
import numpy as np, pandas as pd, itertools, json
from sklearn.ensemble import HistGradientBoostingClassifier
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
import os; os.makedirs(O, exist_ok=True)
c = pd.read_parquet(S + 'r21_cb/clusters_t1.parquet')
c = c[c.fn != 'x'].reset_index(drop=True)
T = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/division_types_final.csv')[['Division', 'dominant']]
TR = {'Kanha Tiger Reserve', 'Satpura_TR', 'PTR MP', 'BTR', 'Panna_TR', 'SANJAY_DUBRI', 'Noradehi', 'Madhav_National_Park',
      'Kuno_Palpur', 'Obedullahganj'}
dom = dict(zip(T.Division, T.dominant))
c['grp'] = [('1 reserves+Ratapani+Kuno' if d in TR else '2 sal territorial' if dom.get(d) == 'sal' else
             '3 teak territorial' if dom.get(d) == 'teak' else '4 other (dry/degraded/north)') for d in c.Division]
FN = sorted(c.fn.unique()); BG = '5 16 Mar-May'; LF = '3 15-28 Feb'
seasons = np.arange(2014, 2027)
w = c.n.values.astype(float)
dm = {k: c[f'dmin_{k:+d}'].values for k in (-3, -2, -1, 1, 2, 3)}


def rule_mask(nmax, frpmax, fut, past, rad, night, tod):
    m = (c.n.values <= nmax) & (c.frp_max.values <= frpmax)
    if night: m &= c.day_only.values
    for k in range(1, fut + 1): m &= dm[k] >= rad
    for k in range(1, past + 1): m &= dm[-k] >= rad
    if tod: m &= np.nan_to_num(c.first_dayhour.values, nan=99) < 13.5
    return m


CUR = dict(nmax=2, frpmax=5, fut=3, past=2, rad=1000, night=True, tod=False)
LIVE = dict(nmax=2, frpmax=5, fut=0, past=2, rad=1000, night=True, tod=False)   # what the field system can know on day 0
grid = [dict(nmax=a, frpmax=b, fut=f, past=p, rad=r, night=nt, tod=td) for a, b, f, p, r, nt, td in
        itertools.product([1, 2, 3, 4], [2, 3, 4, 5, 6, 8, 12], [0, 1, 2, 3], [0, 2], [1000, 2000], [True, False], [False, True])]
# per rule x season x fn: flagged pts (and totals)
key = c.season.values * 10 + np.array([FN.index(x) for x in c.fn])
uk, inv = np.unique(key, return_inverse=True)
tot = np.bincount(inv, weights=w)
G = np.zeros((len(grid), len(uk)))
for i, r in enumerate(grid): G[i] = np.bincount(inv, weights=w * rule_mask(**r), minlength=len(uk))
ks = pd.DataFrame({'season': uk // 10, 'fn': [FN[k % 10] for k in uk], 'tot': tot})


def est(Gi, sel_seasons, win=LF):
    """pooled over seasons: F flagged pts in win, N pts, TP = sum_s (F_s - b_s N_s), precision TP/F, j = Jan-14Feb flag share."""
    F = N = TP = 0.0
    for s in sel_seasons:
        a = (ks.season == s) & (ks.fn == win); bb = (ks.season == s) & (ks.fn == BG)
        if not a.any() or not bb.any(): continue
        Fs, Ns = Gi[a.values].sum(), ks.tot[a].sum(); b = Gi[bb.values].sum() / ks.tot[bb].sum()
        F += Fs; N += Ns; TP += Fs - b * Ns
    return F, N, TP, (TP / F if F else np.nan)


def choose(train, minprec=0.65, live=False):
    best, bi = -1, None
    for i, r in enumerate(grid):
        if live and r['fut'] > 0: continue
        F, N, TP, P = est(G[i], train)
        if P >= minprec and TP > best: best, bi = TP, i
    return bi


ci = grid.index(CUR); li = grid.index(LIVE)
folds = []
for h in seasons:
    tr = [s for s in seasons if s != h]
    bi = choose(tr); bl = choose(tr, live=True)
    for name, i in [('current rule (fixed)', ci), ('refit rule', bi), ('refit live-only rule', bl), ('current live tag', li)]:
        Ft, Nt, TPt, Pt = est(G[i], tr); Fh, Nh, TPh, Ph = est(G[i], [h])
        folds.append(dict(heldout=h, rule=name, params=json.dumps(grid[i]), train_prec=Pt, train_TP=TPt, heldout_prec=Ph,
                          heldout_flag_pts=Fh, heldout_TP=TPh, heldout_pts=Nh))
FO = pd.DataFrame(folds); FO.to_csv(O + 'loso_folds.csv', index=False)
print(FO.groupby('rule')[['train_prec', 'heldout_prec']].describe().round(2).T)
print(FO[FO.rule == 'refit rule'].params.value_counts())
# forward test: fit on 2014-2025, test 2026
fwd = choose(list(range(2014, 2026))); fwdl = choose(list(range(2014, 2026)), live=True)
print('forward refit rule', grid[fwd], est(G[fwd], [2026]), 'current', est(G[ci], [2026]), 'live refit', grid[fwdl], est(G[fwdl], [2026]))

# ---------- bootstrap by fire, per fortnight and group, for a given per-cluster mask --------------------------------------------
rng = np.random.default_rng(21)
fires = c.fire_id.values; ufi, finv = np.unique(fires, return_inverse=True)
B = 400


def boot_table(mask, by, seasons_sel=None, wins=('1 Jan', '2 1-14 Feb', LF, '4 1-15 Mar'), reps=B):
    """precision (excess), flag share f, background b, recall proxy j (=flag share in 1 Jan-14 Feb), with 95% CIs.
    Season-stratified pooling: TP = sum_s (F_s - b_s N_s)."""
    sel = np.ones(len(c), bool) if seasons_sel is None else c.season.isin(seasons_sel).values
    grp = c[by].values if by else np.array(['all'] * len(c))
    ug, gi = np.unique(grp, return_inverse=True)
    fi = np.array([FN.index(x) for x in c.fn]); si = c.season.values - 2014
    k = (gi * 13 + si) * len(FN) + fi
    k = np.where(sel, k, len(ug) * 13 * len(FN))
    K = len(ug) * 13 * len(FN) + 1
    Wt = rng.poisson(1.0, size=(reps, len(ufi))).astype(np.float32)
    def tabs(ww):
        Nt = np.bincount(k, weights=ww, minlength=K)[:-1].reshape(len(ug), 13, len(FN))
        Ft = np.bincount(k, weights=ww * mask, minlength=K)[:-1].reshape(len(ug), 13, len(FN))
        return Nt, Ft
    allr = [tabs(w)] + [tabs(w * Wt[r][finv]) for r in range(reps)]
    out = []
    jb = [FN.index('1 Jan'), FN.index('2 1-14 Feb')]
    for g_, gv in enumerate(ug):
        for win in wins:
            wi = FN.index(win); bi_ = FN.index(BG); res = []
            for Nt, Ft in allr:
                Ns, Fs, Nb, Fb = Nt[g_, :, wi], Ft[g_, :, wi], Nt[g_, :, bi_], Ft[g_, :, bi_]
                ok = (Ns > 0) & (Nb > 0)
                b = np.where(ok, Fb / np.where(Nb > 0, Nb, 1), 0)
                F, N = Fs[ok].sum(), Ns[ok].sum(); TP = (Fs - b * Ns)[ok].sum()
                jf, jn = Ft[g_, ok][:, jb].sum(), Nt[g_, ok][:, jb].sum()
                res.append((TP / F if F else np.nan, F / N if N else np.nan, (F - TP) / N if N else np.nan, jf / jn if jn else np.nan, N, F))
            R = np.array(res)
            q = lambda kk: np.nanpercentile(R[1:, kk], [2.5, 97.5]) if np.isfinite(R[1:, kk]).any() else [np.nan, np.nan]
            out.append(dict(group=gv, window=win, pts=R[0, 4], flagged_pts=R[0, 5], flag_share=R[0, 1], background_share=R[0, 2],
                            precision=R[0, 0], prec_lo=q(0)[0], prec_hi=q(0)[1], recall_proxy=R[0, 3], rec_lo=q(3)[0], rec_hi=q(3)[1]))
    return pd.DataFrame(out)


m_cur = rule_mask(**CUR); m_live = rule_mask(**LIVE)
# held-out version of the refit rule: each season scored with the rule chosen without it
m_ho = np.zeros(len(c), bool)
for h in seasons:
    i = grid.index(json.loads(FO[(FO.heldout == h) & (FO.rule == 'refit rule')].params.iloc[0])); m_ho |= rule_mask(**grid[i]) & (c.season.values == h)
T1 = pd.concat([boot_table(m_cur, None).assign(rule='current'), boot_table(m_ho, None).assign(rule='refit, held-out'),
                boot_table(m_cur, None, seasons_sel=[2026]).assign(rule='current, 2026 only'),
                boot_table(m_cur, 'era').assign(rule='current by era').rename(columns={'group': 'era'})])
T1.to_csv(O + 'heldout_fortnight.csv', index=False); print(T1.round(3).to_string())
T2 = boot_table(m_cur, 'grp', wins=(LF, '4 1-15 Mar')); T2.to_csv(O + 'heldout_groups.csv', index=False); print(T2.round(3).to_string())
# per-season held-out precision of current rule with CI (season = the held-out unit)
ps = []
for h in seasons:
    t = boot_table(m_cur, None, seasons_sel=[h], wins=(LF,), reps=200).assign(season=h); ps.append(t)
PS = pd.concat(ps); PS.to_csv(O + 'heldout_by_season.csv', index=False); print(PS[['season', 'pts', 'flag_share', 'background_share', 'precision', 'prec_lo', 'prec_hi']].round(3).to_string())

# ---------- live tag: what share of real wildfires does it mark, and how often does it flip ----------------------------------
L = []
lf = c.fn.values == LF
for nm, msk in [('16 Mar-May (wildfire background)', c.fn.values == BG), ('15-28 Feb', lf)]:
    L.append(dict(set=nm, pts=w[msk].sum(), live_tag_share=(w * m_live)[msk].sum() / w[msk].sum(),
                  final_tag_share=(w * m_cur)[msk].sum() / w[msk].sum(),
                  live_tags_dropped_after_3d=1 - (w * m_cur)[msk & m_live].sum() / (w * m_live)[msk].sum()))
# fires that became big (>=3 fire-days or >=10 points) and started 15-28 Feb: share whose first cluster had the live tag
first = c.sort_values('fday').groupby('fire_id').head(1)
big = (first.fire_ndays >= 3) | (first.fire_pts >= 10)
fl = first.fn == LF
L.append(dict(set='15-28 Feb fires that grew (>=3 days or >=10 pts): first-day live-tag share', pts=int((fl & big).sum()),
              live_tag_share=m_live[first.index][(fl & big).values].mean()))
fb = first.fn == BG
L.append(dict(set='16 Mar-May fires that grew: first-day live-tag share', pts=int((fb & big).sum()), live_tag_share=m_live[first.index][(fb & big).values].mean()))
LT = pd.DataFrame(L); LT.to_csv(O + 'live_tag.csv', index=False); print(LT.round(3).to_string())

# ---------- learned alternative (PU: 1 Jan-14 Feb = 1, 16 Mar-May = 0), leave-one-season-out --------------------------------
feat_all = ['n', 'nsat', 'frp_max', 'frp_sum', 'day_only', 'night_near', 'dmin_-3', 'dmin_-2', 'dmin_-1', 'dmin_+1', 'dmin_+2', 'dmin_+3',
            'first_dayhour', 'last_dayhour', 'd_road', 'd_track', 'd_edge', 'has_snpp']
feat_live = [f for f in feat_all if not f.startswith('dmin_+')]
Xall = c[feat_all].astype(float).fillna(-1)
c['era_n'] = c.era.str[0].astype(int)
y = np.isin(c.fn.values, ['1 Jan', '2 1-14 Feb']).astype(int)
trm = np.isin(c.fn.values, ['1 Jan', '2 1-14 Feb', BG])
res = []
for feats, nm in [(feat_all + ['era_n'], 'learned (all features)'), (feat_live + ['era_n'], 'learned (live features)')]:
    X = c[feats].astype(float).fillna(-1).values
    p = np.full(len(c), np.nan)
    for h in seasons:
        m = trm & (c.season.values != h)
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, class_weight='balanced', random_state=0).fit(X[m], y[m])
        o = c.season.values == h; p[o] = clf.predict_proba(X[o])[:, 1]
    c['p_' + nm] = p
    # threshold per fold chosen on training seasons' OOF scores (late Feb precision >= .65, max TP)
    mh = np.zeros(len(c), bool)
    for h in seasons:
        tr = [s for s in seasons if s != h]; best, bt = -1, None
        for thr in np.arange(0.5, 0.99, 0.01):
            Gi = np.bincount(inv, weights=w * (p >= thr), minlength=len(uk))
            F, N, TP, P = est(Gi, tr)
            if P >= 0.65 and TP > best: best, bt = TP, thr
        if bt is not None: mh |= (p >= bt) & (c.season.values == h)
    t = boot_table(mh, None, wins=(LF, '4 1-15 Mar'), reps=200).assign(rule=nm); res.append(t)
for msk, nm in [(m_cur, 'current rule'), (m_ho, 'refit rule, held-out'), (m_live, 'current live tag (no future test)')]:
    res.append(boot_table(msk, None, wins=(LF, '4 1-15 Mar'), reps=200).assign(rule=nm))
LV = pd.concat(res); LV['est_control_pts_caught'] = LV.flagged_pts * LV.precision
LV.to_csv(O + 'learned_vs_rule.csv', index=False); print(LV.round(3).to_string())

# ---------- bias check of the background assumption -------------------------------------------------------------------------
# (1) placebo windows: same estimator on Jun and 1-15 Mar; (2) division-season regression: late-Feb flag share vs early burning
bc = []
for win in ['6 Jun', '4 1-15 Mar']:
    F, N, TP, P = est(G[ci], seasons, win=win); bc.append(dict(check=f'excess "precision" in {win} (no planned burns expected in Jun)', value=P))
ds = c.assign(fl=m_cur * w, ww=w).groupby(['Division', 'season', 'fn'])[['fl', 'ww']].sum().unstack('fn')
lfF, lfN = ds[('fl', LF)].fillna(0), ds[('ww', LF)].fillna(0)
bgF, bgN = ds[('fl', BG)].fillna(0), ds[('ww', BG)].fillna(0)
jN = ds[('ww', '1 Jan')].fillna(0) + ds[('ww', '2 1-14 Feb')].fillna(0)
allN = ds['ww'].fillna(0).sum(1)
D = pd.DataFrame({'lf_share': lfF / lfN, 'lfN': lfN, 'bg': bgF / bgN, 'early': jN / allN}).dropna()
D = D[(D.lfN >= 10)]
D['ex'] = D.lf_share - D.bg
for lo, hi in [(0, 0.005), (0.005, 0.02), (0.02, 0.05), (0.05, 0.15), (0.15, 1.01)]:
    q = D[(D.early >= lo) & (D.early < hi)]
    bc.append(dict(check=f'division-seasons with early share {lo:.3f}-{hi:.3f}: n={len(q)}, late-Feb flag share (pt-weighted)',
                   value=(q.lf_share * q.lfN).sum() / q.lfN.sum(), background=(q.bg * q.lfN).sum() / q.lfN.sum()))
BC = pd.DataFrame(bc); BC.to_csv(O + 'bias_checks.csv', index=False); print(BC.round(3).to_string())
c[['cid', 'fire_id', 'season', 'Division', 'grp', 'fn', 'n']].assign(flag_cur=m_cur, flag_live=m_live, flag_refit_ho=m_ho,
    p_learned=c['p_learned (all features)']).to_parquet(S + 'r21_cb/cluster_flags.parquet')
