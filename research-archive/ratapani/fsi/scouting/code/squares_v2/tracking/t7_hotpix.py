"""Tracking step 7: where inside the squares was the fire? Truth: Sentinel-2 / Landsat 20-30 m hot pixels
(fire-alert-scars/out/af) of a scene taken while the fire burned (~10:45 IST). Never used as input or for any choice.
For each fire map and each hot-pixel scene with >= 3 hot pixels inside the outline (+300 m):
 (a) ranking: which 40 m cells hold hot pixels at the scene minute? score per cell
       inversion : -|T_c + tau/2 - t_scene| (closeness of the cell's burning window to the scene time)
       nearest / idw4 / linear : same with the baseline arrival maps
       kernel    : sum over detections exp(-d/400 m) exp(-|dt|/6 h)
       pass centres : -(distance to the nearest pixel centre of the VIIRS pass nearest in time)
     -> AUC over the outline's cells.
 (b) placement: distance from the hot-pixel centre to
       pass centre  : centre of that nearest VIIRS pass's points (the round-17 "plain centre")
       inversion    : burning-weighted centre of the inversion at the scene minute
       sub-square   : burning-weighted centre at the VIIRS pass's own minute, inside that pass's footprints (+300 m)
     and median over hot pixels of the distance to the nearest predicted-burning cell / nearest pixel centre.
Usage: python3 t7_hotpix.py <config> -> results/t7_hotpix_<config>.csv/.json"""
import sys, os, json, glob
import numpy as np, pandas as pd, pyproj
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *
from t6_photos import load_map, baselines, foot_dist, mapdir

def auc(y, s): return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'base'
    from t4_run import config
    hyp, _ = config(name)
    tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
    H = pd.concat([pd.read_csv(f, usecols=['date', 'time_utc', 'lon', 'lat', 'scene']) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_20*.csv')])
    H['x'], H['y'] = tp(H.lon.values, H.lat.values); H['t'] = pd.to_datetime(H.date + ' ' + H.time_utc)
    H = H.drop_duplicates(['x', 'y', 't']); htree = cKDTree(H[['x', 'y']].values)
    D = data()['D']; rows = []
    files = sorted(glob.glob(f'{mapdir(name)}/*.npz'))
    for fn in files:
        fire = int(os.path.basename(fn)[:-4]); z = load_map(name, fire); t0 = z['t0']
        tr = z['tr']; cx = tr[2] + (z['cc'] + .5) * z['tr'][0]; cy = tr[5] - (z['rr'] + .5) * z['tr'][0]; T = z['T'].astype(float)
        ct = cKDTree(np.c_[cx, cy])
        d = D[(D.fire == fire) & (D.kind == 'viirs')]
        if not len(d): continue
        tlast = d.t.max()
        cand = H.iloc[np.unique(np.concatenate(htree.query_ball_point(np.c_[cx[::7], cy[::7]], 400)))] if len(cx) else H.iloc[:0]
        cand = cand[(cand.t >= t0 - pd.Timedelta(hours=36)) & (cand.t <= tlast + pd.Timedelta(hours=24))]
        if not len(cand): continue
        B = None
        for ts, h in cand.groupby('t'):
            dist, j = ct.query(h[['x', 'y']].values); h = h[dist <= 300]; jj = j[dist <= 300]
            if len(h) < 3: continue
            th = (ts - t0).total_seconds() / 3600
            if B is None: B = baselines(cx, cy, d, t0)
            hot = np.zeros(len(cx), bool); hot[jj[dist[dist <= 300] <= 40]] = True
            if hot.sum() == 0: hot[jj] = True
            tdet = (d.t - t0).dt.total_seconds().values / 3600
            # VIIRS pass nearest in time
            pk = d.pass_key.values[np.argmin(np.abs(tdet - th))]; dp = d[d.pass_key == pk]; tp_ = (dp.t.iloc[0] - t0).total_seconds() / 3600
            r = dict(fire=fire, season=t0.year, scene=h.scene.iloc[0], t_scene=str(ts), n_hot=len(h), gap_to_pass_h=tp_ - th, pass_pts=len(dp), cells=len(cx))
            sc = {'inversion': -np.abs(T + hyp['tau'] / 2 - th)}
            for m in ['nearest', 'idw4', 'linear']: sc[m] = -np.abs(B[m] - th)
            kern = np.zeros(len(cx))
            for t_, x_, y_ in zip(tdet, d.xc.values, d.yc.values): kern += np.exp(-np.hypot(cx - x_, cy - y_) / 400) * np.exp(-abs(t_ - th) / 6)
            sc['kernel'] = kern; sc['pass_centres'] = -np.hypot(cx[:, None] - dp.xc.values[None], cy[:, None] - dp.yc.values[None]).min(1)
            for m, s in sc.items(): r[f'auc_{m}'] = auc(hot, s)
            hc = h[['x', 'y']].values.mean(0)
            r['d_pass_centre'] = float(np.hypot(*(dp[['xc', 'yc']].values.mean(0) - hc)))
            b = expit((th - T) / hyp['s']) * expit((T + hyp['tau'] - th) / hyp['s'])
            if b.sum() < 1e-3: b = np.exp(-np.abs(T + hyp['tau'] / 2 - th))
            r['d_inversion'] = float(np.hypot(*(np.c_[cx, cy].T @ b / b.sum() - hc)))
            # sub-square at the pass minute inside the pass's footprints (+300 m)
            inF = foot_dist(cx, cy, dp).min(1) <= 300
            bk = expit((tp_ - T) / hyp['s']) * expit((T + hyp['tau'] - tp_) / hyp['s'])
            bk = np.where(inF, bk, 0)
            r['d_subsquare'] = float(np.hypot(*(np.c_[cx, cy].T @ bk / bk.sum() - hc))) if bk.sum() > 1e-3 else np.nan
            # per hot pixel: distance to nearest predicted burning cell (top cells, same count as hot cells) / pixel centre
            k = max(int(hot.sum()), 3); top = np.argsort(-sc['inversion'])[:k]
            r['dh_inversion'] = float(np.median(cKDTree(np.c_[cx[top], cy[top]]).query(h[['x', 'y']].values)[0]))
            r['dh_pass_centres'] = float(np.median(cKDTree(dp[['xc', 'yc']].values).query(h[['x', 'y']].values)[0]))
            topk = np.argsort(-kern)[:k]; r['dh_kernel'] = float(np.median(cKDTree(np.c_[cx[topk], cy[topk]]).query(h[['x', 'y']].values)[0]))
            rows.append(r)
    X = pd.DataFrame(rows); tag = name if len(name) < 40 else 'cfg'; X.to_csv(f'{OUT}/t7_hotpix_{tag}.csv', index=False)
    rng = np.random.default_rng(0)
    def bt(a, b, f=np.median):
        g = X.dropna(subset=[a, b]); fires = g.fire.unique(); v = []
        for _ in range(1000):
            k = rng.choice(fires, len(fires)); s = g.set_index('fire').loc[k]
            v.append(f(s[a] - s[b]))
        return [round(float(f(g[a] - g[b])), 3), round(float(np.quantile(v, .025)), 3), round(float(np.quantile(v, .975)), 3)]
    res = dict(scenes=len(X), fires=int(X.fire.nunique()), median_gap_to_pass_h=round(float(X.gap_to_pass_h.abs().median()), 2))
    res['auc_mean'] = {c[4:]: round(X[c].mean(), 4) for c in X.columns if c.startswith('auc_')}
    for m in ['nearest', 'idw4', 'linear', 'kernel', 'pass_centres']: res[f'auc_inversion_minus_{m}'] = bt('auc_inversion', f'auc_{m}', np.mean)
    res['median_dist_to_hot_centre_m'] = {c[2:]: round(X[c].median()) for c in ['d_pass_centre', 'd_inversion', 'd_subsquare']}
    res['inversion_minus_pass_centre_m'] = bt('d_inversion', 'd_pass_centre'); res['subsquare_minus_pass_centre_m'] = bt('d_subsquare', 'd_pass_centre')
    res['median_hotpixel_to_nearest_predicted_m'] = {c[3:]: round(X[c].median()) for c in ['dh_inversion', 'dh_pass_centres', 'dh_kernel']}
    res['dh_inversion_minus_pass_centres'] = bt('dh_inversion', 'dh_pass_centres'); res['dh_inversion_minus_kernel'] = bt('dh_inversion', 'dh_kernel')
    for lab, g in [('gap_le_3h', X[X.gap_to_pass_h.abs() <= 3]), ('gap_gt_3h', X[X.gap_to_pass_h.abs() > 3])]:
        res[lab] = dict(n=len(g), d_pass_centre=round(g.d_pass_centre.median()), d_inversion=round(g.d_inversion.median()), d_subsquare=round(g.d_subsquare.median()),
                        auc_inversion=round(g.auc_inversion.mean(), 4), auc_kernel=round(g.auc_kernel.mean(), 4), auc_pass_centres=round(g.auc_pass_centres.mean(), 4))
    json.dump(res, open(f'{OUT}/t7_hotpix_{tag}.json', 'w'), indent=1); print(json.dumps(res, indent=1))
