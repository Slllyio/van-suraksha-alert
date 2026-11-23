"""A1: decompose the pooled outward move of VIIRS small-gap pairs into
   true advance (v x gap)  +  edge-reach terms  +  geometry/coupling terms,
fitted jointly on fires and static industrial sites (static sites get no v term), separately day / night.

Per pair (A = earlier look, B = later look), outward projection p = (B - A - sensor offsets) . u/|u|, u = M - E.
Regressors (all EXOGENOUS: they do not depend on how much the fire grew):
  gap_h                       true advance (fires only)
  o20, o21                    sensor-specific radial reach: 1[B=s] - 1[A=s]  (antisymmetric in order; tests "satellite order")
  dpix                        linear pixel size B - A (m), sqrt(scan*track): edge reach from bigger off-nadir blocks
  dpix x fire                 lets fires and static sites differ
  geo                         (tanzB - tanzA) * uE: view-angle (east-west) shift projected on u
  coup                        (trace Sigma_B - trace Sigma_A) / (2 |u|): noise coupling because u uses the mid-point of A and B
                              (Sigma from the pooled noise model: pixel term k*pix^2/(12 n))
ENDOGENOUS terms (cluster change between looks), only in a second, 'conditional' model:
  dlnn = ln(nB/nA), dlnfrp = ln(FRP_B/FRP_A)
Speeds are re-estimated with the fitted nuisance terms removed, with the nuisance coefficients fitted on the
OTHER half of the seasons (even <-> odd), so the correction is held out. 95% CIs: bootstrap over fire clusters
(5 km cell x season) / static sites; 400 replicates.
Out: results/a1_*.json/csv, results/class_speed_correction.json, results/edge_term_by_pair.parquet (scratch copy too)."""
import json, os
import numpy as np, pandas as pd
POOL = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool'
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
rng = np.random.default_rng(20); CLIP = 2000.0; NB = 400

def load():
    F = pd.read_parquet(f'{POOL}/fires_small.parquet'); S = pd.read_parquet(f'{POOL}/static_small.parquet')
    G = pd.read_parquet(f'{POOL}/pairs3.parquet', columns=['tzA', 'tzB'])
    out = []
    for D, fire in ((F, 1), (S, 0)):
        D = D.copy(); D[['tzA', 'tzB']] = G.loc[D.index, ['tzA', 'tzB']].values
        D['fire'] = fire
        out.append(D)
    D = pd.concat(out)
    D['p'] = D.p_out.clip(-CLIP, CLIP)
    D['pg'] = D.p_grow.clip(-CLIP, CLIP)
    D['o20'] = (D.sB == 'NOAA-20') * 1.0 - (D.sA == 'NOAA-20')
    D['o21'] = (D.sB == 'NOAA-21') * 1.0 - (D.sA == 'NOAA-21')
    D['pixA'] = np.sqrt(D.scanA * D.trackA); D['pixB'] = np.sqrt(D.scanB * D.trackB)
    D['dpix'] = D.pixB - D.pixA
    ue = D.uE / D.u_len
    D['geo'] = (D.tzB - D.tzA).fillna(0) * ue * 100.0          # per 100 m of 'effective height'
    sig = lambda s, t, n: (0.592 * s ** 2 + 0.899 * t ** 2) / (12 * n)
    D['coup'] = (sig(D.scanB, D.trackB, D.nB) - sig(D.scanA, D.trackA, D.nA)) / (2 * np.maximum(D.u_len, 100.0))
    D['dlnn'] = np.log(D.nB / D.nA); D['dlnfrp'] = np.log(np.clip(D.frpB, .1, None) / np.clip(D.frpA, .1, None))
    D['forest'] = ~D.vtm.isin([170, 180, 190, 191, 200])
    D['even'] = D.season % 2 == 0
    return D

def design(d, terms):
    cols = []
    for t in terms:
        if t == 'gap_fire': cols.append(d.gap_h.values * d.fire.values)
        elif t == 'gap_static': cols.append(d.gap_h.values * (1 - d.fire.values))
        elif t == 'int_fire': cols.append(d.fire.values * 1.0)
        elif t == 'int_static': cols.append(1.0 - d.fire.values)
        elif t == 'dpix_fire': cols.append(d.dpix.values * d.fire.values)
        elif t == 'dpix_static': cols.append(d.dpix.values * (1 - d.fire.values))
        elif t.endswith('_fire'): cols.append(d[t[:-5]].values * d.fire.values)
        else: cols.append(d[t].values * 1.0)
    return np.column_stack(cols)

def fit(d, terms, y='p', nb=NB):
    X = design(d, terms); Y = d[y].values; ok = np.isfinite(X).all(1) & np.isfinite(Y); X, Y = X[ok], Y[ok]
    cl = pd.factorize(d.cl.values[ok])[0]; nc = cl.max() + 1; k = X.shape[1]
    XtX = np.zeros((nc, k, k)); XtY = np.zeros((nc, k))
    for i in range(k):
        XtY[:, i] = np.bincount(cl, X[:, i] * Y, nc)
        for j in range(i, k):
            XtX[:, i, j] = XtX[:, j, i] = np.bincount(cl, X[:, i] * X[:, j], nc)
    co = np.linalg.solve(XtX.sum(0), XtY.sum(0)); bs = []
    for _ in range(nb):
        s = rng.integers(0, nc, nc); bs.append(np.linalg.lstsq(XtX[s].sum(0), XtY[s].sum(0), rcond=None)[0])
    bs = np.array(bs)
    return {t: dict(coef=float(co[i]), lo=float(np.quantile(bs[:, i], .025)), hi=float(np.quantile(bs[:, i], .975))) for i, t in enumerate(terms)}, co, ok

def pooled_speed(d, col, nb=NB):
    v = d[col].values; g = d.gap_h.values; cl = pd.factorize(d.cl)[0]; nc = cl.max() + 1
    sv = np.bincount(cl, v, nc); sg = np.bincount(cl, g, nc)
    m = sv.sum() / sg.sum(); bs = [(sv[s].sum() / sg[s].sum()) for s in (rng.integers(0, nc, nc) for _ in range(nb))]
    return dict(m_h=round(m, 1), lo=round(float(np.quantile(bs, .025)), 1), hi=round(float(np.quantile(bs, .975)), 1), n=int(len(d)), clusters=int(nc))

if __name__ == '__main__':
    D = load()
    NUIS = ['o20', 'o21', 'dpix_fire', 'dpix_static', 'geo', 'coup']
    BASE = ['int_fire', 'int_static', 'gap_fire', 'gap_static']
    res = {}; corr_cols = {}
    D['p_corr'] = np.nan
    for dn in 'DN':
        d = D[D.dn == dn]
        r = {}
        r['naive_gapfit'], _, _ = fit(d[d.fire == 1], ['int_fire', 'gap_fire'])
        r['exogenous_all_seasons'], co, _ = fit(d, BASE + NUIS)
        r['exogenous_plus_cluster_change'], _, _ = fit(d, BASE + NUIS + ['dlnn_fire', 'dlnfrp_fire'])
        r['exogenous_no_intercepts'], _, _ = fit(d, ['gap_fire', 'gap_static'] + NUIS)
        # static null alone, with nuisance terms: does it explain the -27 m/h?
        s = d[d.fire == 0]
        r['static_raw_speed'] = pooled_speed(s.assign(q=s.p), 'q')
        res[dn] = r
    # held-out correction: nuisance coefficients fitted on the other season half (no intercepts, gap terms kept)
    D = D.reset_index().rename(columns={'index': 'pair_row'})
    D['nuis_m'] = np.nan
    for dn in 'DN':
      for even_tgt in (True, False):
        m = (D.dn == dn) & (D.even == even_tgt)
        X = design(D[m], NUIS); _, co_h, _ = fit(D[(D.dn == dn) & (D.even != even_tgt)], ['gap_fire', 'gap_static'] + NUIS, nb=1)
        D.loc[m, 'nuis_m'] = X @ co_h[2:]
    D['p_corr'] = D.p - D.nuis_m
    D['pg_corr'] = D.pg - D.nuis_m * 0  # later-growth projection: nuisance terms are defined on u, not g; left raw
    rows = []
    for dn in 'DN':
        for nm, sub in [('fires, all', (D.fire == 1)), ('fires, forest+scrub', (D.fire == 1) & D.forest), ('fires, farm', (D.fire == 1) & (D.vtm == 170)),
                        ('static null', D.fire == 0)]:
            d = D[sub & (D.dn == dn)]
            rr = dict(dn=dn, set=nm)
            a = pooled_speed(d, 'p'); b = pooled_speed(d, 'p_corr')
            rr.update(raw=f"{a['m_h']} ({a['lo']} to {a['hi']})", corrected=f"{b['m_h']} ({b['lo']} to {b['hi']})", n=a['n'],
                      raw_m_h=a['m_h'], corr_m_h=b['m_h'], corr_lo=b['lo'], corr_hi=b['hi'], mean_nuis_m=round(float(d.nuis_m.mean()), 2))
            if nm != 'static null':
                g, _, _ = fit(d.assign(p=d.p_corr), ['int_fire', 'gap_fire'], nb=300)
                rr['corr_gapfit_v'] = f"{g['gap_fire']['coef']:.1f} ({g['gap_fire']['lo']:.1f} to {g['gap_fire']['hi']:.1f})"
                rr['corr_gapfit_a_m'] = f"{g['int_fire']['coef']:.1f} ({g['int_fire']['lo']:.1f} to {g['int_fire']['hi']:.1f})"
            rows.append(rr)
    T = pd.DataFrame(rows); T.to_csv(f'{OUT}/a1_corrected_speeds.csv', index=False)
    # endogenous check: speed in pairs where the cluster did not change (same pixel count)
    chk = {}
    for dn in 'DN':
        d = D[(D.fire == 1) & (D.dn == dn)]
        for lab, m in [('n unchanged', d.nA == d.nB), ('n grew', d.nB > d.nA), ('n shrank', d.nB < d.nA),
                       ('FRP fell >30%', d.dlnfrp < np.log(.7)), ('FRP rose >30%', d.dlnfrp > np.log(1.3)),
                       ('single pixel both looks', (d.nA == 1) & (d.nB == 1)),
                       ('B pixels smaller by >50 m', d.dpix < -50), ('B pixels larger by >50 m', d.dpix > 50)]:
            chk[f'{dn} {lab}'] = pooled_speed(d[m], 'p_corr')
    res['by_cluster_change'] = chk
    json.dump(res, open(f'{OUT}/a1_decomposition.json', 'w'), indent=1)
    pd.set_option('display.width', 250); print(T.to_string())
    for dn in 'DN':
        print(dn); print(pd.DataFrame(res[dn]['exogenous_all_seasons']).T.round(3).to_string())
        print(pd.DataFrame(res[dn]['exogenous_plus_cluster_change']).T.round(3).to_string())
        print('naive', res[dn]['naive_gapfit'], 'static raw', res[dn]['static_raw_speed'])
    print(json.dumps(chk, indent=0))
    # per-pair edge/nuisance term for other threads (fires only), keyed on pairs.parquet row
    E = D[D.fire == 1][['pair_row', 'dn', 'nuis_m']].rename(columns={'nuis_m': 'edge_m'})
    E.to_parquet(f'{OUT}/edge_term_by_pair.parquet', index=False)
    D.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r20_a/pairs_corr.parquet')
