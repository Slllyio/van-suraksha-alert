"""Experiment 1: detections as true footprints (scan x track, rotated to the satellite track), not points.
1a  Short-gap pairs (two VIIRS passes of one fire < 2 h apart): how much of the apparent move is footprint geometry?
    - shift split into along-scan / along-track parts; shift vs pixel size;
    - the smallest move the two looks REQUIRE: 0 if the two footprint unions overlap, else the gap between them.
1b  Mid-fire photos (independent truth; forecast = VIIRS seen >= 1 h before the photo, 4 days, 4 km), AUC per photo:
    points / circles, axis blocks (old), rotated blocks, half-size blocks, footprint kernel, and the intersection
    constraint (a footprint that overlaps a near-time (<2 h) footprint of another sensor is cut to the overlap + 100 m).
    Extent: "inside the union of footprints" vs "inside 200 m circles" as a burned-by-photo map (accuracy, IoU).
1c  Reconstruction (continuity's nearest-look rule, all VIIRS looks of the fire before and after): T(x) = time of the
    nearest point / axis block / rotated block; pixel accuracy on the photos.
"""
import json, sys
import numpy as np, pandas as pd, shapely
from shapely.ops import unary_union
from s_lib import *
D = load_det(); D = D[D.type.fillna(0) != 2]
V = D[D.kind == 'viirs']
res = {}
# ---------- 1a
P = V[V.fire >= 0].groupby(['fire', 'pass_id']).agg(sensor=('sensor', 'first'), t=('t', 'min'), n=('x', 'size'),
        x=('x', 'mean'), y=('y', 'mean'), heading=('heading', 'first'), scan=('scan_m', 'mean'), track=('track_m', 'mean')).reset_index()
P = P.sort_values(['fire', 't']); rows = []
for f, g in P.groupby('fire'):
    g = g.reset_index(drop=True)
    for i in range(len(g) - 1):
        a, b = g.iloc[i], g.iloc[i + 1]; gap = (b.t - a.t).total_seconds() / 60
        if gap > 120 or a.sensor == b.sensor: continue
        da = V[(V.pass_id == a.pass_id) & (V.fire == f)]; db = V[(V.pass_id == b.pass_id) & (V.fire == f)]
        ua = unary_union([poly(r) for r in da.itertuples()]); ub = unary_union([poly(r) for r in db.itertuples()])
        us, ut = axes(a.heading); v = np.array([b.x - a.x, b.y - a.y])
        rows.append(dict(fire=f, gap_min=gap, s0=a.sensor, s1=b.sensor, n0=a.n, n1=b.n, shift=np.hypot(*v),
                         along_scan=abs(v @ us), along_track=abs(v @ ut), scan=(a.scan + b.scan) / 2, track=(a.track + b.track) / 2,
                         same_orient=bool(a.heading == b.heading), overlap=ua.intersects(ub), min_move=ua.distance(ub),
                         ov_share=ua.intersection(ub).area / min(ua.area, ub.area)))
Q = pd.DataFrame(rows); Q.to_csv(f'{OUT}/e1_short_pairs_footprints.csv', index=False)
Q['pix'] = np.sqrt(Q.scan * Q.track)
r = dict(pairs=len(Q), median_gap_min=float(Q.gap_min.median()), median_shift_m=round(Q['shift'].median()),
         median_along_scan=round(Q.along_scan.median()), median_along_track=round(Q.along_track.median()),
         median_scan_m=round(Q.scan.median()), median_track_m=round(Q.track.median()),
         spearman_shift_vs_pixel=round(Q[['shift', 'pix']].corr('spearman').iloc[0, 1], 3),
         share_footprints_overlap=round(Q.overlap.mean(), 3), share_required_move_zero=round((Q.min_move == 0).mean(), 3),
         required_move_median_m=round(Q.min_move.median(), 1), required_move_p90_m=round(Q.min_move.quantile(.9), 1),
         required_move_rate_p90_m_per_h=round((Q.min_move / (Q.gap_min / 60)).quantile(.9), 1),
         overlap_share_of_smaller_median=round(Q.ov_share.median(), 3))
r['shift_by_pixel'] = {f'{lo}-{hi}': round(Q[(Q.pix >= lo) & (Q.pix < hi)]['shift'].median()) for lo, hi in [(300, 420), (420, 520), (520, 650), (650, 900)]}
r['n_by_pixel'] = {f'{lo}-{hi}': int(((Q.pix >= lo) & (Q.pix < hi)).sum()) for lo, hi in [(300, 420), (420, 520), (520, 650), (650, 900)]}
res['1a_short_pairs'] = r; print(json.dumps(r, indent=1))
# ---------- photos
PH = photos()
Vt = V.reset_index(drop=True); allD = D.reset_index(drop=True)
def constrained(b):
    """Intersection constraint: each footprint in b that overlaps footprints of another sensor's pass < 2 h away is cut
    to that overlap (+100 m); others stay whole. Returns a shapely geometry (union)."""
    pieces = []; polys = {k: unary_union([poly(r) for r in g.itertuples()]) for k, g in b.groupby('pass_id')}
    pt = b.groupby('pass_id').agg(t=('t', 'min'), sensor=('sensor', 'first'))
    for k, g in b.groupby('pass_id'):
        partners = [j for j in pt.index if j != k and pt.sensor[j] != pt.sensor[k] and abs((pt.t[j] - pt.t[k]).total_seconds()) <= 7200]
        U = unary_union([polys[j] for j in partners]).buffer(100) if partners else None
        for r in g.itertuples():
            p = poly(r)
            if U is not None and p.intersects(U): pieces.append(p.intersection(U))
            else: pieces.append(p)
    return unary_union(pieces)
rows = []
for ph in PH:
    X, Y, y, T = ph['X'], ph['Y'], ph['y'], ph['T']
    if y.sum() == 0 or y.all(): continue
    cx, cy = X.mean(), Y.mean()
    win = lambda A: A[(A.t <= T - pd.Timedelta(hours=1)) & (A.t >= T - pd.Timedelta(days=4)) & (np.abs(A.x - cx) < 4000) & (np.abs(A.y - cy) < 4000)]
    v = win(Vt); b_all = win(allD)
    if not len(v): continue
    dp = np.hypot(X[:, None] - v.x.values[None], Y[:, None] - v.y.values[None])
    dax = foot_dist(X, Y, v, rotate=False); drot = foot_dist(X, Y, v); dhalf = foot_dist(X, Y, v, scale=.5)
    pts = shapely.points(X, Y)
    dcon = shapely.distance(pts, constrained(v)); dcon_m = shapely.distance(pts, constrained(b_all[b_all.kind != 'hotpix']))
    S = dict(points=-dp.min(1), kernel400=np.exp(-dp / 400).sum(1), blocks_axis=-dax.min(1), blocks_rot=-drot.min(1),
             blocks_half=-dhalf.min(1), foot_kernel200=np.exp(-drot / 200).sum(1), foot_kernel400=np.exp(-drot / 400).sum(1),
             constrained_viirs=-dcon, constrained_viirs_modis=-dcon_m)
    r = dict(fire=ph['fire'], event=ph['event'], season=ph['season'], big=ph['big'], n_px=len(y), share=y.mean(), n_viirs=len(v),
             n_pass=v.pass_id.nunique(), n_sens_pairs=int((v.groupby('pass_id').t.min().sort_values().diff().dt.total_seconds() < 7200).sum()))
    for k, s in S.items(): r['auc_' + k] = auc(y, s)
    # extent maps: burned-by-photo = inside union of footprints / inside 200 m circles / inside equal-area circles
    for nm, m in [('union_rot', drot.min(1) <= 0), ('union_axis', dax.min(1) <= 0), ('circle200', dp.min(1) <= 200),
                  ('circle_eqarea', dp.min(1) <= np.sqrt(v.scan_m * v.track_m / np.pi).median()), ('union_half', dhalf.min(1) <= 0),
                  ('constrained', dcon <= 0)]:
        r['acc_' + nm] = (m == y).mean(); r['iou_' + nm] = (m & (y == 1)).sum() / max((m | (y == 1)).sum(), 1)
        r['frac_' + nm] = m.mean()
    newg = drot.min(1) > 0
    if newg.sum() >= 20 and 0 < y[newg].sum() < newg.sum():
        for k, s in S.items(): r['aucnew_' + k] = auc(y[newg], s[newg])
    rows.append(r)
E = pd.DataFrame(rows); E.to_csv(f'{OUT}/e1_photo_forecast.csv', index=False)
meth = [c[4:] for c in E.columns if c.startswith('auc_')]
r = dict(photos=len(E), fires=int(E.fire.nunique()), mean_auc={k: round(E['auc_' + k].mean(), 4) for k in meth},
         mean_auc_new_ground={k: round(E['aucnew_' + k].mean(), 4) for k in meth if 'aucnew_' + k in E},
         n_new_ground=int(E['aucnew_points'].notna().sum()))
r['diff_vs_points_95'] = {k: boot_diff(E, 'auc_' + k, 'auc_points') for k in meth if k != 'points'}
r['diff_rot_vs_axis_95'] = boot_diff(E, 'auc_blocks_rot', 'auc_blocks_axis')
r['diff_constrained_vs_rot_95'] = boot_diff(E, 'auc_constrained_viirs', 'auc_blocks_rot')
r['diff_foot_kernel200_vs_kernel400_95'] = boot_diff(E, 'auc_foot_kernel200', 'auc_kernel400')
r['photos_with_near_time_pass_pair'] = int((E.n_sens_pairs > 0).sum())
sub = E[E.n_sens_pairs > 0]
r['constrained_on_photos_with_pairs'] = dict(n=len(sub), constrained=round(sub.auc_constrained_viirs.mean(), 4), blocks_rot=round(sub.auc_blocks_rot.mean(), 4),
                                            diff_95=boot_diff(sub, 'auc_constrained_viirs', 'auc_blocks_rot'))
r['extent'] = {nm: dict(acc=round(E['acc_' + nm].mean(), 4), iou=round(E['iou_' + nm].mean(), 4), mapped_share=round(E['frac_' + nm].mean(), 3))
               for nm in ['union_rot', 'union_axis', 'union_half', 'circle200', 'circle_eqarea', 'constrained']}
r['extent_true_share_burned'] = round(E.share.mean(), 3)
r['extent_diff_iou_union_rot_vs_circle200_95'] = boot_diff(E, 'iou_union_rot', 'iou_circle200')
r['extent_diff_acc_union_rot_vs_circle200_95'] = boot_diff(E, 'acc_union_rot', 'acc_circle200')
res['1b_photo_forecast'] = r; print(json.dumps(r, indent=1))
# ---------- 1c reconstruction: nearest-look time rule
rows = []
for ph in PH:
    X, Y, y, T = ph['X'], ph['Y'], ph['y'], ph['T']
    d = Vt[Vt.fire == ph['fire']]
    if len(d) == 0 or y.sum() == 0 or y.all(): continue
    th = (d.t - T).dt.total_seconds().values / 3600
    r = dict(fire=ph['fire'], season=ph['season'], big=ph['big'], before=int((th < 0).sum()), after=int((th > 0).sum()))
    for nm, dist in [('points', np.hypot(X[:, None] - d.x.values[None], Y[:, None] - d.y.values[None])),
                     ('blocks_axis', foot_dist(X, Y, d, rotate=False)), ('blocks_rot', foot_dist(X, Y, d)),
                     ('blocks_half', foot_dist(X, Y, d, scale=.5))]:
        # nearest footprint; ties inside several footprints -> the earliest (fire was there by then)
        dm = dist.min(1, keepdims=True); cand = np.where(dist <= dm + 1e-6, th[None], np.inf)
        tnn = cand.min(1); pred = tnn <= 0
        r['acc_' + nm] = (pred == y).mean(); r['auc_' + nm] = auc(y, -(tnn + dm[:, 0] / 15))
        # mean-of-ties variant: inside several footprints of different times -> average time
        tav = np.where(dist <= dm + 1e-6, th[None], np.nan); tav = np.nanmean(tav, 1)
        r['accmean_' + nm] = ((tav <= 0) == y).mean()
    rows.append(r)
R = pd.DataFrame(rows); R.to_csv(f'{OUT}/e1_photo_reconstruction.csv', index=False)
both = R[(R.before > 0) & (R.after > 0)]
r = dict(photos=len(R), photos_look_before_and_after=len(both),
         acc={k: round(R['acc_' + k].mean(), 4) for k in ['points', 'blocks_axis', 'blocks_rot', 'blocks_half']},
         acc_ties_mean={k: round(R['accmean_' + k].mean(), 4) for k in ['points', 'blocks_axis', 'blocks_rot', 'blocks_half']},
         acc_both_sides={k: round(both['acc_' + k].mean(), 4) for k in ['points', 'blocks_axis', 'blocks_rot', 'blocks_half']},
         diff_rot_vs_points_95=boot_diff(R, 'acc_blocks_rot', 'acc_points'), diff_rot_vs_axis_95=boot_diff(R, 'acc_blocks_rot', 'acc_blocks_axis'),
         diff_half_vs_points_95=boot_diff(R, 'acc_blocks_half', 'acc_points'))
res['1c_reconstruction'] = r; print(json.dumps(r, indent=1))
json.dump(res, open(f'{OUT}/e1_summary.json', 'w'), indent=1)
