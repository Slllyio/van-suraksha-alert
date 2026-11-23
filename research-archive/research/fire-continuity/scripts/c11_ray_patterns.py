"""Pattern recognition on the rays (c10): what makes a front stop, and which way it runs.
1. Matched stop rates: chance the front stops in the next 100 m when the ground is X vs not X, compared only within the same
   front (origin) and the same distance band (Mantel-Haenszel odds ratio, fire bootstrap 95% range). Removes fire size, weather,
   season, crews working the whole fire: what is left is the ground itself.
2. Held-out-season model (LightGBM step hazard) with pixel features vs a model that knows only distance and the front's own state.
   Scored on (a) where the stop happens (AUC) and (b) which of the 36 directions runs farthest, vs shuffled directions and vs
   one-factor rules (uphill, tree cover, avoid old burns, avoid crops, downwind).
3. Rules: shallow decision tree on the stop event (fit on other seasons, lift checked on the held-out season).
4. Shapes: each front's 36 reaches. Elongation axis vs terrain grain (ridge/valley direction), vs wind; longest lobe vs uphill;
   KMeans clustering of shape profiles into front types.
Out: results/ray_patterns.json, figures/ray_patterns.png"""
import os, sys, json, numpy as np, pandas as pd, lightgbm as lgb, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score
from sklearn.tree import DecisionTreeClassifier, _tree
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scipy.stats import spearmanr, kruskal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C
HERE = '/mnt/project-files/research/fire-continuity'
ST = pd.read_parquet(f'{C.SCRATCH}/rays.parquet'); O = pd.read_csv(f'{HERE}/results/ray_origins.csv')
O['reach'] = O.reach.apply(lambda s: np.array(json.loads(s.replace('nan', 'NaN'))))
O['censored'] = O.censored.apply(lambda s: np.array(json.loads(s.lower())))
ST = ST.merge(O[['origin', 'kind', 'n_dots', 'frp', 'doy', 'wind_ms', 'th']], on='origin')
ST['band'] = pd.cut(ST.s, [0, 200, 500, 1000, 2000, 1e9], labels=False, include_lowest=True)
ST['fuel'] = ST.fuel.fillna(ST.fuel.median()); ST['village_km'] = ST.village_km.fillna(ST.village_km.median())
T = ST[~ST.after_stop].copy(); T['y'] = T.stop.astype(int)
rng = np.random.default_rng(0); out = dict(n_steps=len(T), n_stops=int(T.y.sum()), n_origins=int(T.origin.nunique()), n_fires=int(T.fire.nunique()))
per100 = lambda h: 1 - (1 - h) ** 5
out['stop_chance_per_100m_overall'] = round(float(per100(T.y.mean())), 3)

# ---------- 1. matched stop rates
fq = T.fuel.quantile(.75)
EXPO = {'tree cover': T.tree == 1, 'grass / shrub': T.grass == 1, 'crop / built': T.crop == 1, 'water': T.water == 1,
        'road within 40 m': T.road == 1, 'burned earlier this season': T.burned_earlier == 1,
        'burned in most past seasons (>50%)': T.prior_burns > .5, 'leaving forest (trees behind, none here)': (T.tree_prev100 > .6) & (T.tree == 0),
        'going uphill (grade > 5%)': T.grade > .05, 'going downhill (grade < -5%)': T.grade < -.05,
        'ridge (10 m above surroundings)': T.local_height > 10, 'valley (10 m below)': T.local_height < -10,
        'downwind ray': T.downwind > .5, 'upwind ray': T.downwind < -.5, 'high fuel map (top quarter)': T.fuel > fq,
        'village within 1 km': T.village_km < 1}
T['stratum'] = T.origin + '_' + T.band.astype(str)
def mh(e):
    D = pd.DataFrame(dict(f=T.fire, s=T.stratum, e=e.values.astype(int), y=T.y.values))
    D['a'] = D.e * D.y; D['b'] = D.e * (1 - D.y); D['c'] = (1 - D.e) * D.y; D['d'] = (1 - D.e) * (1 - D.y)
    g = D.groupby(['f', 's'])[['a', 'b', 'c', 'd']].sum(); n = g.sum(axis=1)
    num = (g.a * g.d / n).groupby(level=0).sum(); den = (g.b * g.c / n).groupby(level=0).sum()
    fires = num.index.values; bs = []
    for _ in range(300):
        sel = rng.choice(len(fires), len(fires)); bs.append(num.values[sel].sum() / den.values[sel].sum())
    h1 = T.y[e].mean(); h0 = T.y[~e].mean()
    return dict(OR=round(float(num.sum() / den.sum()), 2), lo=round(float(np.quantile(bs, .025)), 2), hi=round(float(np.quantile(bs, .975)), 2),
                share_of_steps=round(float(e.mean()), 3), raw_stop_per100_with=round(float(per100(h1)), 3), raw_stop_per100_without=round(float(per100(h0)), 3))
out['matched_stop_odds'] = {k: mh(e) for k, e in EXPO.items()}
print(json.dumps(out['matched_stop_odds'], indent=0))

# ---------- 2. held-out model
PIX = ['tree', 'grass', 'crop', 'water', 'road', 'tree_prev100', 'grade', 'local_height', 'slope', 'fuel', 'village_km', 'prior_burns', 'downwind']   # burned_earlier left out: same burn-label product as the scar (circular)
BASE = ['s', 'n_dots', 'frp', 'doy', 'wind_ms', 'th', 'is_first']
ST['is_first'] = (ST.kind == 'first').astype(int); T['is_first'] = (T.kind == 'first').astype(int)
prm = dict(n_estimators=300, learning_rate=.05, num_leaves=15, min_child_samples=200, subsample=.7, subsample_freq=1, colsample_bytree=.8, verbose=-1)
pred = {m: np.zeros(len(ST)) for m in ['base', 'full']}; contrib = np.zeros((len(ST), len(PIX) + len(BASE) + 1))
for s in sorted(T.season.unique()):
    tr = T.season != s; te = (ST.season == s).values
    for m, cols in [('base', BASE), ('full', BASE + PIX)]:
        mdl = lgb.LGBMClassifier(**prm).fit(T.loc[tr, cols].astype(float), T.y[tr])
        pred[m][te] = mdl.predict_proba(ST.loc[te, cols].astype(float))[:, 1]
        if m == 'full': contrib[te] = mdl.predict(ST.loc[te, cols].astype(float), pred_contrib=True)
ST['h_base'], ST['h_full'] = pred['base'], pred['full']
CB = pd.DataFrame(contrib[:, :-1], columns=BASE + PIX, index=ST.index)   # keep contributions tied to rows (ST is re-sorted below)
msk = (~ST.after_stop).values
out['step_auc'] = dict(distance_and_front_state=round(roc_auc_score(ST.stop[msk], ST.h_base[msk]), 3),
                       plus_ground=round(roc_auc_score(ST.stop[msk], ST.h_full[msk]), 3))
# within-origin AUC (does ground tell where on the same front's rays it stops)
def within_auc(col):
    v = []
    for _, g in ST[msk].groupby(['origin', 'band']):
        if 0 < g.stop.sum() < len(g): v.append((roc_auc_score(g.stop, g[col]), len(g)))
    v = np.array(v); return round(float(np.average(v[:, 0], weights=v[:, 1])), 4)
out['step_auc_within_same_front_and_distance'] = dict(distance_and_front_state=within_auc('h_base'), plus_ground=within_auc('h_full'))
# predicted reach per ray = expected distance before stopping
ST = ST.sort_values(['origin', 'ray', 'i_rel'])
def exp_reach(h):
    surv = np.exp(ST.assign(l=np.log1p(-np.clip(h, 0, .999))).groupby(['origin', 'ray']).l.cumsum())
    return (surv * 20).groupby([ST.origin, ST.ray]).sum()
RP = pd.DataFrame(dict(full=exp_reach(ST.h_full.values)))
first500 = ST[ST.s <= 500].groupby(['origin', 'ray'])
RP['uphill'] = first500.grade.mean(); RP['trees'] = first500.tree.mean(); RP['avoid_often_burnt'] = -first500.prior_burns.mean()
RP['avoid_crops'] = -first500.crop.mean(); RP['downwind'] = first500.downwind.mean(); RP['ridge'] = first500.local_height.mean()
act = []
for o in O.itertuples():
    for j, r in enumerate(o.reach):
        if np.isfinite(r): act.append((o.origin, j, r, o.censored[j]))
act = pd.DataFrame(act, columns=['origin', 'ray', 'reach', 'cens']).set_index(['origin', 'ray'])
RP = RP.join(act, how='inner')
rank = {}
good = RP.groupby(level=0).filter(lambda g: len(g) >= 18 and g.reach.std() > 0)
for col in ['full', 'uphill', 'trees', 'avoid_often_burnt', 'avoid_crops', 'downwind', 'ridge']:
    rho, hit, hit0 = [], [], []
    for oid, g in good.groupby(level=0):
        v = g[col].values; a = g.reach.values; rays = g.index.get_level_values(1).values
        if not np.isfinite(v).any() or np.nanstd(v) == 0: continue
        rho.append(spearmanr(v, a)[0])
        best = rays[np.nanargmax(a)]; pb = rays[np.nanargmax(v)]; hit.append(min(abs(best - pb), 36 - abs(best - pb)) <= 1)
        hit0.append(np.mean([min(abs(best - x), 36 - abs(best - x)) <= 1 for x in rays]))
    rho = np.array(rho)
    rank[col] = dict(median_rho=round(float(np.nanmedian(rho)), 3), share_rho_pos=round(float(np.nanmean(rho > 0)), 3),
                     farthest_direction_hit=round(float(np.mean(hit)), 3), chance=round(float(np.mean(hit0)), 3), n=len(rho))
out['which_direction_runs_farthest'] = rank
# feature importance and direction from contributions (pre-stop rows, held out)
names = BASE + PIX
Tm = ST[~ST.after_stop]; cb = CB.loc[Tm.index, names].values
imp = {n: round(float(np.abs(cb[:, i]).mean()), 4) for i, n in enumerate(names)}
out['mean_abs_contribution_logodds'] = dict(sorted(imp.items(), key=lambda x: -x[1]))
dep = {}
for n in ['grade', 'local_height', 'tree_prev100', 'fuel', 'prior_burns', 'village_km', 'slope', 'downwind', 's']:
    q = pd.qcut(Tm[n], 8, duplicates='drop'); i = names.index(n)
    dep[n] = [(round(float(iv.mid), 3), round(float(v), 3)) for iv, v in pd.Series(cb[:, i]).groupby(q.values, observed=True).mean().items()]
for n in ['tree', 'grass', 'crop', 'road', 'water']:
    i = names.index(n); dep[n] = [(int(k), round(float(v), 3)) for k, v in pd.Series(cb[:, i]).groupby(Tm[n].values).mean().items()]
out['effect_curves_logodds'] = dep

# ---------- 3. rules (fit on all but one season, lift checked out of season)
RULEF = ['tree', 'grass', 'crop', 'road', 'tree_prev100', 'grade', 'local_height', 'fuel', 'village_km', 'prior_burns', 'downwind', 's']
def leaves(clf, cols):
    t = clf.tree_; res = []
    def rec(n, conds):
        if t.feature[n] == _tree.TREE_UNDEFINED: res.append((n, ' and '.join(conds))); return
        f, th = cols[t.feature[n]], t.threshold[n]
        rec(t.children_left[n], conds + [f'{f} <= {th:.2f}']); rec(t.children_right[n], conds + [f'{f} > {th:.2f}'])
    rec(0, []); return dict(res)
clf = DecisionTreeClassifier(max_depth=4, min_samples_leaf=int(.02 * len(T)), random_state=0).fit(T[RULEF], T.y)
lv = clf.apply(T[RULEF]); base_h = T.y.mean(); L = leaves(clf, RULEF)
rules = []
for n, cond in L.items():
    m = lv == n; h = T.y[m].mean()
    seas = [T.y[m & (T.season == s).values].mean() / T.y[(T.season == s).values].mean() for s in sorted(T.season.unique()) if (m & (T.season == s).values).sum() > 500]
    rules.append(dict(rule=cond, share_steps=round(float(m.mean()), 3), stop_per100=round(float(per100(h)), 3), lift=round(float(h / base_h), 2),
                      lift_range_by_season=[round(float(np.min(seas)), 2), round(float(np.max(seas)), 2)] if seas else None, n_fires=int(T.fire[m].nunique())))
out['rules'] = sorted(rules, key=lambda r: -r['lift'])

# ---------- 4. shapes
from scipy.ndimage import gaussian_filter
EL = C.ELEV.astype(float)
sh = []
for o in O.itertuples():
    r = o.reach; ok = np.isfinite(r)
    if ok.sum() < 30 or np.nanmean(r) < 200: continue
    r = np.where(ok, r, np.nanmean(r)); th = np.radians(np.arange(36) * 10)
    P = np.c_[r * np.sin(th), r * np.cos(th)]; M = P.T @ P / 36; w, v = np.linalg.eigh(M)
    elong = np.sqrt(w[1] / max(w[0], 1)); axis = np.degrees(np.arctan2(v[0, 1], v[1, 1])) % 180
    rr, cc = C.rc_of(o.x, o.y); win = EL[max(rr - 50, 0):rr + 51, max(cc - 50, 0):cc + 51]
    gy, gx = np.gradient(gaussian_filter(win, 3), 20); gy = -gy        # north-positive
    J = np.array([[np.mean(gx * gx), np.mean(gx * gy)], [np.mean(gx * gy), np.mean(gy * gy)]]); jw, jv = np.linalg.eigh(J)
    grad_dir = np.degrees(np.arctan2(jv[0, 1], jv[1, 1])) % 180; grain = (grad_dir + 90) % 180; coher = (jw[1] - jw[0]) / (jw[1] + jw[0] + 1e-9)
    up = np.degrees(np.arctan2(np.mean(gx), np.mean(gy))) % 360
    lobe = np.degrees(np.arctan2(np.sum(r * np.sin(th)), np.sum(r * np.cos(th)))) % 360
    j0 = int(np.argmax(r)); prof = np.roll(r, -j0) / r.mean()
    if prof[1:18].sum() < prof[19:].sum(): prof = np.r_[prof[0], prof[1:][::-1]]
    sh.append(dict(origin=o.origin, kind=o.kind, elong=elong, axis=axis, grain=grain, coher=coher, up=up, lobe=lobe,
                   wind_axis=o.wind_to % 180 if np.isfinite(o.wind_to) else np.nan, wind_to=o.wind_to, wind_ms=o.wind_ms,
                   mean_reach=float(r.mean()), doy=o.doy, prof=prof))
SH = pd.DataFrame(sh)
ax_d = lambda a, b: np.abs(((a - b + 90) % 180) - 90)
dir_d = lambda a, b: np.abs(((a - b + 180) % 360) - 180)
el = SH.elong > 1.3; ter = el & (SH.coher > .3)
null = lambda n: [float(np.mean(ax_d(rng.uniform(0, 180, n), 0) <= 30)) for _ in range(1000)]
out['shapes'] = dict(n=len(SH), median_elongation=round(float(SH.elong.median()), 2), share_elongated_1_3=round(float(el.mean()), 3),
    axis_along_terrain_grain_within30=dict(share=round(float((ax_d(SH.axis[ter], SH.grain[ter]) <= 30).mean()), 3), chance=1 / 3, n=int(ter.sum()),
        p95_chance=round(float(np.quantile(null(int(ter.sum())), .95)), 3)),
    axis_along_wind_within30=dict(share=round(float((ax_d(SH.axis[el], SH.wind_axis[el]) <= 30).mean()), 3), chance=1 / 3, n=int(el.sum())),
    longest_lobe_vs_uphill=dict(mean_cos=round(float(np.cos(np.radians(dir_d(SH.lobe, SH.up))).mean()), 3), share_within_45=round(float((dir_d(SH.lobe, SH.up) <= 45).mean()), 3), chance=.25),
    longest_lobe_vs_downwind=dict(mean_cos=round(float(np.nanmean(np.cos(np.radians(dir_d(SH.lobe, SH.wind_to))))), 3), share_within_45=round(float(np.nanmean(dir_d(SH.lobe, SH.wind_to) <= 45)), 3), chance=.25))
Pm = np.stack(SH.prof.values); Pm = np.minimum(Pm, 4)
sil = {k: float(silhouette_score(Pm, KMeans(k, n_init=10, random_state=0).fit_predict(Pm))) for k in range(2, 7)}
k = max(sil, key=sil.get); km = KMeans(k, n_init=10, random_state=0).fit(Pm); SH['type'] = km.labels_
types = {}
for t in range(k):
    g = SH[SH.type == t]
    types[int(t)] = dict(n=len(g), share=round(len(g) / len(SH), 3), elong=round(float(g.elong.median()), 2), mean_reach_m=round(float(g.mean_reach.median())),
                         max_over_mean=round(float(km.cluster_centers_[t].max()), 2), share_new_front=round(float((g.kind != 'first').mean()), 3),
                         wind_ms=round(float(g.wind_ms.median()), 2), doy=round(float(g.doy.median())))
out['shape_types'] = dict(k=k, silhouette=round(sil[k], 3), silhouettes={int(a): round(b, 3) for a, b in sil.items()}, types=types,
                          kruskal_p={c: float(kruskal(*[SH[c][SH.type == t].dropna() for t in range(k)]).pvalue) for c in ['wind_ms', 'doy', 'coher']})
json.dump(out, open(f'{HERE}/results/ray_patterns.json', 'w'), indent=1, default=str)
print(json.dumps({k_: v for k_, v in out.items() if k_ != 'effect_curves_logodds'}, indent=1, default=str))

# ---------- figure
fig, ax = plt.subplots(2, 2, figsize=(15, 11))
mo = out['matched_stop_odds']; ks = sorted(mo, key=lambda k_: mo[k_]['OR']); yy = np.arange(len(ks))
ax[0, 0].errorbar([mo[k_]['OR'] for k_ in ks], yy, xerr=[[mo[k_]['OR'] - mo[k_]['lo'] for k_ in ks], [mo[k_]['hi'] - mo[k_]['OR'] for k_ in ks]], fmt='o', color='#c0392b')
ax[0, 0].axvline(1, color='k', lw=.7); ax[0, 0].set_xscale('log'); ax[0, 0].set_yticks(yy, ks, fontsize=9)
ax[0, 0].set_xlabel('how much likelier the front stops on this ground (1 = no effect)\nsame front, same distance, 95% range over fires')
ax[0, 0].set_title('A. What stops a front (matched within each front)', fontsize=10)
rk = out['which_direction_runs_farthest']; ks2 = list(rk)
ax[0, 1].bar(range(len(ks2)), [rk[k_]['farthest_direction_hit'] * 100 for k_ in ks2], color='#2c6fbb')
ax[0, 1].scatter(range(len(ks2)), [rk[k_]['chance'] * 100 for k_ in ks2], marker='_', s=600, color='k', label='chance')
ax[0, 1].set_xticks(range(len(ks2)), ['model (all ground)' if k_ == 'full' else k_ for k_ in ks2], rotation=25, fontsize=9)
ax[0, 1].set_ylabel('% of fronts: picked the direction that ran farthest (+/-10 deg)'); ax[0, 1].legend(); ax[0, 1].set_title('B. Which way does it run? (seasons held out)', fontsize=10)
for n_, c_ in [('grade', '#c0392b'), ('local_height', '#2c6fbb'), ('tree_prev100', '#27ae60'), ('fuel', '#8e44ad')]:
    xs_, ys_ = zip(*dep[n_]); xr = (np.array(xs_) - min(xs_)) / (max(xs_) - min(xs_) + 1e-9)
    ax[1, 0].plot(xr, ys_, 'o-', color=c_, label=f'{n_} ({min(xs_):.2g} to {max(xs_):.2g})')
ax[1, 0].axhline(0, color='k', lw=.6); ax[1, 0].set_xlabel('low -> high (scaled)'); ax[1, 0].set_ylabel('push on stop chance (log odds, + = stops more)'); ax[1, 0].legend(fontsize=8)
ax[1, 0].set_title('C. Model effect curves (held-out seasons)', fontsize=10)
th_ = np.radians(np.arange(36) * 10); a2 = fig.add_subplot(2, 2, 4, projection='polar'); ax[1, 1].axis('off')
for t in range(k):
    c = np.r_[km.cluster_centers_[t], km.cluster_centers_[t][0]]; a2.plot(np.r_[th_, th_[0]], c, lw=2, label=f"type {t}: {types[t]['share']*100:.0f}%")
a2.set_theta_zero_location('N'); a2.set_theta_direction(-1); a2.legend(fontsize=8, loc='lower left', bbox_to_anchor=(-.15, -.12)); a2.set_title('D. Front shape types (longest run at top)', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/ray_patterns.png', dpi=105)
