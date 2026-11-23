"""Experiment C: a fire is burning now (VIIRS cells on day t). (1) Will it spread to new ground within 1.5 km in the next 2 days?
(2) If so, which nearby cells? New ground = cells whose first burn this season has not happened by day t (scored like SCORING.md: cells already burned are masked).
A nearby cell 'burns' when its first burn day (VIIRS date where one lies in the scar window, else window midpoint) or a VIIRS point
falls in (t, t+2]. Fires = connected groups of VIIRS cells (8-neighbour) active on day t."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, common as C
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from sklearn.isotonic import IsotonicRegression

c = D.cells().set_index('cell_id'); n = len(c); XY = c[['x', 'y']].values; tree = cKDTree(XY)
v = D.viirs(); b = D.burns(); w = D.weather().set_index('date'); lp = D.lean_preds()
ter = pd.read_csv(D.PF + 'ratapani/ee/terrain.csv').set_index('cell_id').reindex(c.index)
fsi = pd.read_csv('/mnt/project-files/research/reframe/results/cell_fsi_prone.csv').set_index('cell_id').fsi_prone.reindex(c.index).fillna(3).values
elev = ter.elev_m_mean.values; slope = ter.slope_deg_mean.values; forest = c.forest_frac.values
fb = b[b['first']].copy(); fb['bday'] = fb.vday.fillna((fb.ws + (fb.we - fb.ws) / 2).dt.floor('D'))
LP = lp.pivot_table(index='date', columns='cell_id', values='pipeline_lean')
ev_rows, cell_rows = [], []
for Y in D.SEASONS:
    days = pd.date_range(f'{Y}-01-01', f'{Y}-06-30'); T = len(days); d0 = days[0]
    A = np.zeros((T, n), bool); g = v[(v.date >= d0) & (v.date <= days[-1])]
    A[(g.date - d0).dt.days.values, g.cell_id.values] = True
    NIGHT = np.zeros((T, n)); np.add.at(NIGHT, ((g.date - d0).dt.days.values, g.cell_id.values), (g.daynight == 'N').values.astype(float))
    FRP = np.zeros((T, n)); np.add.at(FRP, ((g.date - d0).dt.days.values, g.cell_id.values), g.frp.values)
    f = fb[fb.season == Y]
    bday = np.full(n, 10 ** 6); k = (f.bday - d0).dt.days.values; bday[f.cell_id.values] = k
    seen = np.full(n, 10 ** 6); seen[f.cell_id.values] = (f.we - d0).dt.days.values     # scar known from window end
    firstV = np.where(A.any(0), A.argmax(0), 10 ** 6)
    for t in np.nonzero((days >= pd.Timestamp(f'{Y}-02-01')) & (days <= pd.Timestamp(f'{Y}-06-20')))[0]:
        act = np.nonzero(A[t])[0]
        if len(act) == 0: continue
        burned_known = (seen <= t) | (firstV <= t)                       # ground known burned by end of day t
        fut = ((bday > t) & (bday <= t + 2)) | A[t + 1:t + 3].any(0)     # burns in (t, t+2]
        pairs = cKDTree(XY[act]).query_pairs(750, output_type='ndarray')
        M = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(act), len(act))) if len(pairs) else coo_matrix((len(act), len(act)))
        ncomp, lab = connected_components(M, directed=False)
        lpt = LP.loc[days[t]].reindex(range(n)).values if days[t] in LP.index else np.full(n, np.nan)
        lpt = np.where(np.isnan(lpt), np.nanmedian(lpt) if np.isfinite(lpt).any() else 0.02, lpt)
        prev = A[max(t - 3, 0):t].any(0)
        for q in range(ncomp):
            cells_q = act[lab == q]
            ring = np.unique(np.concatenate(tree.query_ball_point(XY[cells_q], 1500 + 1)))
            cand = ring[~burned_known[ring] & ~A[t, ring] & (bday[ring] > t)]   # cells whose first burn already happened (seen or not) are not new ground
            if len(cand) == 0: continue
            dist, near = cKDTree(XY[cells_q]).query(XY[cand])
            y_c = fut[cand]
            age = int(prev[ring].sum() > 0) + int(A[max(t - 1, 0), cells_q].any())
            e = dict(season=Y, date=days[t], fire=f'{Y}-{t}-{q}', n_active=len(cells_q), frp=FRP[t, cells_q].sum(), age=age, night=float(NIGHT[t, cells_q].sum() > 0),
                     n_cand=len(cand), unburned_share=len(cand) / len(ring), cand_lean=lpt[cand].mean(), cand_forest=forest[cand].mean(),
                     cand_fsi=fsi[cand].mean(), san_today=int(A[t].sum()), san_l3=int(A[max(t - 2, 0):t + 1].sum()),
                     doy=days[t].dayofyear, spread=int(y_c.any()), n_new=int(y_c.sum()))
            for col in ('T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'vpd7', 'WS10M'): e[col] = w.loc[days[t], col]
            ev_rows.append(e)
            # direction cue (spread thread): yesterday's/earlier VIIRS cells near this fire -> today's cells; cosine of candidate bearing
            # direction cue from the latest two passes only (spread thread, section 4f): centroid of the earlier pass's points within
            # 1.5 km -> centroid of the latest pass's points of this fire; cosine with each candidate's bearing from the fire
            cosd = np.full(len(cand), np.nan)
            pts = g[g.cell_id.isin(cells_q) & (g.date == days[t])]
            T1 = pts.dt.max(); last = pts[pts.dt == T1]
            near_pts = g[(g.dt < T1) & (g.dt >= T1 - pd.Timedelta(hours=36))]
            if len(near_pts):
                dd = cKDTree(last[['x', 'y']].values).query(near_pts[['x', 'y']].values)[0]
                near_pts = near_pts[dd <= 1500]
                if len(near_pts):
                    T0 = near_pts.dt.max(); p0 = near_pts[near_pts.dt == T0][['x', 'y']].values.mean(0)
                    vdir = last[['x', 'y']].values.mean(0) - p0
                    if np.hypot(*vdir) > 100:
                        rel = XY[cand] - last[['x', 'y']].values.mean(0)
                        cosd = (rel @ vdir) / (np.hypot(rel[:, 0], rel[:, 1]) * np.hypot(*vdir) + 1e-9)
            # daily cue: earlier VIIRS cells near this fire (last 3 days) -> today's cells
            cosday = np.full(len(cand), np.nan); pc = np.nonzero(prev)[0]
            if len(pc):
                pc = pc[cKDTree(XY[cells_q]).query(XY[pc])[0] <= 1500]
                if len(pc):
                    vd2 = XY[cells_q].mean(0) - XY[pc].mean(0)
                    if np.hypot(*vd2) > 1:
                        rel = XY[cand] - XY[cells_q].mean(0)
                        cosday = (rel @ vd2) / (np.hypot(rel[:, 0], rel[:, 1]) * np.hypot(*vd2) + 1e-9)
            cell_rows.append(pd.DataFrame(dict(dir_cos=cosd, dir_day=cosday, fire=e['fire'], season=Y, date=days[t], cell_id=cand, y=y_c.astype(int), dist=dist,
                         n_act_1km=[len(x) for x in cKDTree(XY[cells_q]).query_ball_point(XY[cand], 1000)],
                         lean=lpt[cand], forest=forest[cand], fsi=fsi[cand], slope=slope[cand],
                         delev=elev[cand] - elev[cells_q[near]], frp_near=FRP[t, cells_q[near]], n_active=len(cells_q), night=float(NIGHT[t, cells_q].sum() > 0),
                         ring_burned=burned_known[ring].mean(), doy=days[t].dayofyear, rh=e['RH2M'], vpd7=e['vpd7'])))
    print(Y, len(ev_rows), flush=True)
E = pd.DataFrame(ev_rows); Cc = pd.concat(cell_rows, ignore_index=True)
E.to_parquet(D.OUT + 'spread_events.parquet'); Cc.to_parquet(D.OUT + 'spread_cells.parquet')
CV = list(range(2017, 2025)); TEST = [2025, 2026]
PB = dict(num_leaves=7, min_data_in_leaf=50)

def run(df, feats, y):
    raw = pd.Series(np.nan, index=df.index)
    for hold, train in [([s], [x for x in CV if x != s]) for s in CV] + [(TEST, CV)]:
        tr, te = df[df.season.isin(train)], df[df.season.isin(hold)]
        raw.loc[te.index], _ = C.fit_predict(tr, te, feats, y, 300, PB)
    out = pd.Series(np.nan, index=df.index)
    for hold in [[s] for s in CV] + [TEST]:
        cal = df.season.isin([x for x in CV if x not in hold]); m = df.season.isin(hold)
        out[m] = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4).fit(raw[cal], df.loc[cal, y]).predict(raw[m])
    return out

res = {'events': {}, 'cells': {}}
EF = {'climatology': ['doy'], 'fsi_fire_prone_map': ['doy', 'cand_fsi'], 'size_only': ['doy', 'n_active', 'n_cand'],
      'full': ['doy', 'n_active', 'night', 'frp', 'age', 'n_cand', 'unburned_share', 'cand_lean', 'cand_forest', 'cand_fsi', 'san_today', 'san_l3',
               'T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'vpd7', 'WS10M']}
PE = {k: run(E, f, 'spread') for k, f in EF.items()}
for split, m in (('loso_2017_24', E.season.isin(CV)), ('test_2025_26', E.season.isin(TEST))):
    r = {k: C.skill(E.spread[m], PE[k][m], ref=PE['climatology'][m] if k != 'climatology' else None) for k in EF}
    r['reliability_full'] = C.reliability(E.spread[m], PE['full'][m]); r['n_fires'] = int(m.sum())
    r['mean_new_cells_if_spread'] = round(float(E.n_new[m & (E.spread == 1)].mean()), 2)
    res['events'][split] = r; print('events', split, {k: (r[k]['auc'], r[k]['base_rate'], r[k].get('bss_vs_ref')) for k in EF}, flush=True)
CF = {'distance_only': ['dist'], 'fsi_fire_prone_map': ['fsi'], 'dist_plus_fsi': ['dist', 'fsi'],
      'full_no_direction': ['dist', 'n_act_1km', 'night', 'lean', 'forest', 'fsi', 'slope', 'delev', 'frp_near', 'n_active', 'ring_burned', 'doy', 'rh', 'vpd7'],
      'full_pass_direction': ['dir_cos', 'dist', 'n_act_1km', 'night', 'lean', 'forest', 'fsi', 'slope', 'delev', 'frp_near', 'n_active', 'ring_burned', 'doy', 'rh', 'vpd7'],
      'full': ['dir_day', 'dist', 'n_act_1km', 'night', 'lean', 'forest', 'fsi', 'slope', 'delev', 'frp_near', 'n_active', 'ring_burned', 'doy', 'rh', 'vpd7']}
PC = {k: run(Cc, f, 'y') for k, f in CF.items()}
Cc['rnd'] = np.random.default_rng(0).random(len(Cc))
for split, m in (('loso_2017_24', Cc.season.isin(CV)), ('test_2025_26', Cc.season.isin(TEST))):
    d = Cc[m].copy(); r = {'n_candidate_cells': int(len(d)), 'n_fires': int(d.fire.nunique())}
    for k in CF:
        d[k] = PC[k][m].values; r[k] = C.skill(d.y, d[k], ref=d['distance_only'] if k != 'distance_only' else None)
        for K in (3, 5, 10): r[k][f'recall_top{K}_per_fire'] = C.topk_recall(d, k, 'y', 'fire', K)
    for K in (3, 5, 10): r[f'random_top{K}'] = C.topk_recall(d, 'rnd', 'y', 'fire', K); r[f'ceiling_top{K}'] = C.topk_ceiling(d, 'y', 'fire', K)
    r['reliability_full'] = C.reliability(d.y, d['full'])
    res['cells'][split] = r; print('cells', split, {k: (r[k]['auc'], r[k]['recall_top5_per_fire']) for k in CF}, r['random_top5'], r['ceiling_top5'], flush=True)
json.dump(res, open('/mnt/project-files/research/reframe/results/spread.json', 'w'), indent=1); print('DONE')
