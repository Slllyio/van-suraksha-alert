"""Score the learned footprint model the Rethink thread's way (research/reframe/scripts/exp_spread.py): a fire is the group of
VIIRS cells (S-NPP, NOAA-20, NOAA-21) active on day t; candidates are unburned cells within 1.5 km; a candidate 'burns' when its
first burn day or a VIIRS point falls in (t, t+2]. Metric: share of burning candidate cells caught by the top-5 cells per fire.
Modes:  prep out_prefix                 -> <prefix>_events.parquet, <prefix>_cells.parquet, <prefix>_pts.parquet (same construction as exp_spread.py)
        score prefix modeldir k/n out   -> my per-cell scores for fires with at least one burning candidate (shardable)
        eval prefix scores.parquet[,..] -> top-k recall for my scores, their baselines, their full model, their full + my score"""
import sys, json, numpy as np, pandas as pd, time
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, common as C
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
SEASONS = list(range(2017, 2025))


def prep(prefix):
    c = D.cells().set_index('cell_id'); n = len(c); XY = c[['x', 'y']].values; tree = cKDTree(XY)
    v = D.viirs(); b = D.burns(); w = D.weather().set_index('date'); lp = D.lean_preds()
    ter = pd.read_csv(D.PF + 'ratapani/ee/terrain.csv').set_index('cell_id').reindex(c.index)
    fsi = pd.read_csv('/mnt/project-files/research/reframe/results/cell_fsi_prone.csv').set_index('cell_id').fsi_prone.reindex(c.index).fillna(3).values
    elev = ter.elev_m_mean.values; slope = ter.slope_deg_mean.values; forest = c.forest_frac.values
    fb = b[b['first']].copy(); fb['bday'] = fb.vday.fillna((fb.ws + (fb.we - fb.ws) / 2).dt.floor('D'))
    LP = lp.pivot_table(index='date', columns='cell_id', values='pipeline_lean')
    ev_rows, cell_rows, pt_rows = [], [], []
    for Y in SEASONS:
        days = pd.date_range(f'{Y}-01-01', f'{Y}-06-30'); T = len(days); d0 = days[0]
        A = np.zeros((T, n), bool); g = v[(v.date >= d0) & (v.date <= days[-1])]
        A[(g.date - d0).dt.days.values, g.cell_id.values] = True
        NIGHT = np.zeros((T, n)); np.add.at(NIGHT, ((g.date - d0).dt.days.values, g.cell_id.values), (g.daynight == 'N').values.astype(float))
        FRP = np.zeros((T, n)); np.add.at(FRP, ((g.date - d0).dt.days.values, g.cell_id.values), g.frp.values)
        f = fb[fb.season == Y]
        bday = np.full(n, 10 ** 6); k = (f.bday - d0).dt.days.values; bday[f.cell_id.values] = k
        seen = np.full(n, 10 ** 6); seen[f.cell_id.values] = (f.we - d0).dt.days.values
        firstV = np.where(A.any(0), A.argmax(0), 10 ** 6)
        for t in np.nonzero((days >= pd.Timestamp(f'{Y}-02-01')) & (days <= pd.Timestamp(f'{Y}-06-20')))[0]:
            act = np.nonzero(A[t])[0]
            if len(act) == 0: continue
            burned_known = (seen <= t) | (firstV <= t)
            fut = ((bday > t) & (bday <= t + 2)) | A[t + 1:t + 3].any(0)
            pairs = cKDTree(XY[act]).query_pairs(750, output_type='ndarray')
            M = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(act), len(act))) if len(pairs) else coo_matrix((len(act), len(act)))
            ncomp, lab = connected_components(M, directed=False)
            lpt = LP.loc[days[t]].reindex(range(n)).values if days[t] in LP.index else np.full(n, np.nan)
            lpt = np.where(np.isnan(lpt), np.nanmedian(lpt) if np.isfinite(lpt).any() else 0.02, lpt)
            prev = A[max(t - 3, 0):t].any(0)
            for q in range(ncomp):
                cells_q = act[lab == q]
                ring = np.unique(np.concatenate(tree.query_ball_point(XY[cells_q], 1500 + 1)))
                cand = ring[~burned_known[ring] & ~A[t, ring] & (bday[ring] > t)]
                if len(cand) == 0: continue
                dist, near = cKDTree(XY[cells_q]).query(XY[cand])
                y_c = fut[cand]
                age = int(prev[ring].sum() > 0) + int(A[max(t - 1, 0), cells_q].any())
                fid = f'{Y}-{t}-{q}'
                e = dict(season=Y, date=days[t], fire=fid, n_active=len(cells_q), frp=FRP[t, cells_q].sum(), age=age, night=float(NIGHT[t, cells_q].sum() > 0),
                         n_cand=len(cand), unburned_share=len(cand) / len(ring), cand_lean=lpt[cand].mean(), cand_forest=forest[cand].mean(),
                         cand_fsi=fsi[cand].mean(), san_today=int(A[t].sum()), san_l3=int(A[max(t - 2, 0):t + 1].sum()),
                         doy=days[t].dayofyear, spread=int(y_c.any()), n_new=int(y_c.sum()))
                for col in ('T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'vpd7', 'WS10M'): e[col] = w.loc[days[t], col]
                ev_rows.append(e)
                pts = g[g.cell_id.isin(cells_q) & (g.date == days[t])]
                pt_rows.append(pd.DataFrame(dict(fire=fid, season=Y, x=pts.x.values, y=pts.y.values, t=pts.dt.values, frp=pts.frp.values, daynight=pts.daynight.values)))
                cell_rows.append(pd.DataFrame(dict(fire=fid, season=Y, date=days[t], cell_id=cand, y=y_c.astype(int), dist=dist,
                         n_act_1km=[len(x) for x in cKDTree(XY[cells_q]).query_ball_point(XY[cand], 1000)],
                         lean=lpt[cand], forest=forest[cand], fsi=fsi[cand], slope=slope[cand],
                         delev=elev[cand] - elev[cells_q[near]], frp_near=FRP[t, cells_q[near]], n_active=len(cells_q), night=float(NIGHT[t, cells_q].sum() > 0),
                         ring_burned=burned_known[ring].mean(), doy=days[t].dayofyear, rh=e['RH2M'], vpd7=e['vpd7'])))
        print(Y, len(ev_rows), flush=True)
    pd.DataFrame(ev_rows).to_parquet(prefix + '_events.parquet'); pd.concat(cell_rows, ignore_index=True).to_parquet(prefix + '_cells.parquet')
    pd.concat(pt_rows, ignore_index=True).to_parquet(prefix + '_pts.parquet')


def score_(prefix, mdir, k_n, out):
    import lightgbm as lgb, footprint as fp, sim
    Cc = pd.read_parquet(prefix + '_cells.parquet'); P = pd.read_parquet(prefix + '_pts.parquet')
    fires = sorted(Cc[Cc.y == 1].fire.unique()); k, n = map(int, k_n.split('/')); fires = fires[k::n]
    models = {s: lgb.Booster(model_file=f'{mdir}/loso_{s}.txt') for s in SEASONS}
    rows, wx = [], {}; tt = time.time()
    for i, fid in enumerate(fires):
        pts = P[P.fire == fid]; s = int(pts.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        ev = pd.DataFrame(dict(x=pts.x.values, y=pts.y.values, t=pd.to_datetime(pts.t.values), season=s, frp=pts.frp.values, daynight=pts.daynight.values))
        ev['overpass'] = ev.t.min().floor('h'); ev = ev.sort_values('t')
        try:
            X, y, meta = fp.fire_features(ev, wx[s])
        except Exception as ex:
            print('fail', fid, ex, flush=True); continue
        i0, i1, j0, j1 = meta['win']; mask = meta['mask']
        p = np.zeros(mask.shape, np.float32); p[mask] = models[s].predict(X)
        cid = fp.CELL[i0:i1, j0:j1]
        cand = Cc[Cc.fire == fid]
        for c_ in cand.cell_id.values:
            m = (cid == c_) & mask
            rows.append(dict(fire=fid, cell_id=int(c_), fp_mean=float(p[m].mean()) if m.any() else 0.0, fp_max=float(p[m].max()) if m.any() else 0.0,
                             fp_sum=float(p[m].sum()), n_px=int(m.sum())))
        if i % 50 == 0:
            print(i, len(fires), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


def evaluate(prefix, scores):
    Cc = pd.read_parquet(prefix + '_cells.parquet')
    S = pd.concat([pd.read_parquet(f) for f in scores.split(',')], ignore_index=True)
    d = Cc.merge(S, on=['fire', 'cell_id'], how='left')
    pos_fires = set(Cc[Cc.y == 1].fire); d = d[d.fire.isin(pos_fires)].copy()
    print('fires with burning candidates', d.fire.nunique(), 'of', Cc.fire.nunique(), '; scored', d[d.fp_mean.notna()].fire.nunique())
    d = d[d.fp_mean.notna()].copy()
    d['rnd'] = np.random.default_rng(0).random(len(d)); d['neg_dist'] = -d.dist
    feats_full = ['dist', 'n_act_1km', 'night', 'lean', 'forest', 'fsi', 'slope', 'delev', 'frp_near', 'n_active', 'ring_burned', 'doy', 'rh', 'vpd7']
    # their models retrained on the same rows (LOSO 2017-24, their params), with and without my score
    PB = dict(num_leaves=7, min_data_in_leaf=50)
    def run(df, feats):
        raw = pd.Series(np.nan, index=df.index)
        for s in SEASONS:
            tr, te = df[df.season != s], df[df.season == s]
            if len(te): raw.loc[te.index], _ = C.fit_predict(tr, te, feats, 'y', 300, PB)
        return raw
    d['their_full'] = run(d, feats_full); d['their_full_plus_fp'] = run(d, feats_full + ['fp_mean', 'fp_max']); d['lean_only'] = d.lean
    res = {}
    for k in (3, 5, 10):
        res[f'top{k}'] = {name: C.topk_recall(d, name, 'y', 'fire', k) for name in ['rnd', 'neg_dist', 'lean_only', 'fp_mean', 'fp_max', 'fp_sum', 'their_full', 'their_full_plus_fp']}
        res[f'top{k}']['ceiling'] = C.topk_ceiling(d, 'y', 'fire', k)
    res['auc'] = {name: round(float(C.roc_auc_score(d.y, d[name])), 4) for name in ['neg_dist', 'lean_only', 'fp_mean', 'fp_max', 'their_full', 'their_full_plus_fp']}
    res['n_fires'] = int(d.fire.nunique()); res['n_cells'] = int(len(d)); res['n_pos'] = int(d.y.sum())
    print(json.dumps(res, indent=1)); json.dump(res, open(prefix + '_eval.json', 'w'), indent=1)
    d.to_parquet(prefix + '_scored.parquet')


if __name__ == '__main__':
    m = sys.argv[1]
    if m == 'prep': prep(sys.argv[2])
    elif m == 'score': score_(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif m == 'eval': evaluate(sys.argv[2], sys.argv[3])
