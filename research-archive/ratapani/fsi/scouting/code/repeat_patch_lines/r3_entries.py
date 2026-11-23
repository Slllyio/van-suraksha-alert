"""Step 3. Entry side of every fire that burned into a repeat-burn patch, patch consistency, and entry-side line proposals.
Patch edge: the ring of 60 m cells just outside the patch, split into ~1 km edge segments (k-means on ring cell positions,
n = round(ring length / 1 km)). For each fire that burned >= 1 ha of a patch's forest:
  inside     - a first-look VIIRS dot (its own 60 m footprint cell) lies in the patch -> 'started inside'
  entered    - otherwise: spread path (4-connected, inside the fire's own outline) from the first-look dot cells; entry point =
               the patch cells reached first; edge segment = segment of the nearest ring cell.
               Cross-checks: (a) daily scar growth - patch cells covered by the earliest chained daily outline; (b) dot order - the
               last dot outside the patch before the first dot inside it.
  unreached  - the patch part is not connected to the start inside the outline (another start / gap in the outline)
Bearing = direction from the patch centre to the entry point (0 = north, clockwise).
Patch-year = the fire that burned most of the patch that season (one entry per season).
Line proposal (only from the seasons defining the patch): >= 3 entered patch-years and >= 60% of them through one segment -> line
= that segment's ring cells (outside the patch, along its boundary). Alternatives: whole ring; nearest existing road/track window
(round-25 Overture road candidates, centre within 2 km of the segment centre).
Chance check: modal-segment share expected if the same number of entries fell on segments at random (by segment length).
Run: python r3_entries.py tr3 | all5     Out (scratch r26): entries_<set>.parquet, patches_<set>.parquet, lines_<set>.pkl"""
import pickle, glob, sys
import numpy as np, pandas as pd
from numba import njit
from scipy import ndimage as ndi
from scipy.cluster.vq import kmeans2
from scipy.spatial import cKDTree
from multiprocessing import Pool
import c26 as C

RNG = np.random.default_rng(26)


@njit(cache=True)
def bfs_dist(M, H, W, src):
    n = H * W; d = -np.ones(n, np.int32); q = np.empty(n, np.int64); h = 0; t = 0
    for s in src:
        if M[s] and d[s] < 0: d[s] = 0; q[t] = s; t += 1
    while h < t:
        i = q[h]; h += 1; r = i // W; c = i % W
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr = r + dr; cc = c + dc
            if rr < 0 or rr >= H or cc < 0 or cc >= W: continue
            j = rr * W + cc
            if M[j] and d[j] < 0: d[j] = d[i] + 1; q[t] = j; t += 1
    return d


def bearing(dx, dy):
    return (np.degrees(np.arctan2(dx, dy)) + 360) % 360


def segments(lab60, FOR, W):
    """ring cells, segment ids, centroid etc. per patch."""
    P = {}
    objs = ndi.find_objects(lab60)
    for i, sl in enumerate(objs):
        if sl is None: continue
        p = i + 1
        r0 = max(sl[0].start - 1, 0); r1 = min(sl[0].stop + 1, lab60.shape[0]); c0 = max(sl[1].start - 1, 0); c1 = min(sl[1].stop + 1, lab60.shape[1])
        sub = lab60[r0:r1, c0:c1] == p
        ring = ndi.binary_dilation(sub, np.ones((3, 3), bool)) & ~sub & (lab60[r0:r1, c0:c1] == 0)
        rr, cc = np.nonzero(ring); pr, pc = np.nonzero(sub)
        gr, gc = rr + r0, cc + c0
        pts = np.c_[gc, gr].astype(float)
        km = len(pts) * C.RES / 1000 * 0.9          # ring cells x 60 m, x0.9 for diagonal steps (8-connected ring)
        k = max(1, int(round(km / C.SEG_KM)))
        if k > 1 and len(pts) > k:
            np.random.seed(p)
            _, seg = kmeans2(pts, k, minit='++', seed=p)
        else:
            seg = np.zeros(len(pts), int)
        _, seg = np.unique(seg, return_inverse=True)
        fo = FOR[pr + r0, pc + c0]
        P[p] = dict(ring=(gr * W + gc).astype(np.int64), seg=seg.astype(np.int16), nseg=int(seg.max() + 1), cx=float((pc + c0).mean()), cy=float((pr + r0).mean()),
                    ring_km=km, forest_ha=float(fo.sum() * C.CELL_HA), area_ha=float(len(pr) * C.CELL_HA), tree=cKDTree(pts),
                    seg_km=np.bincount(seg, minlength=int(seg.max() + 1)) * C.RES / 1000 * 0.9)
    return P


def unpack(b, n):
    return np.unpackbits(b)[:n].astype(bool)


def one(args):
    key, pset = args
    L = pickle.load(open(C.SC + f'fires_{key}.pkl', 'rb')); H, W = L['H'], L['W']
    FOR = unpack(L['forest'], H * W).reshape(H, W)
    Z = np.load(C.SC + f'patches_{key}.npz'); lab = Z['lab_' + pset]
    lab60 = np.kron(lab, np.ones((C.AGG, C.AGG), np.int32))[:H, :W]
    if lab.max() == 0: return key, [], {}, {}
    P = segments(lab60, FOR, W)
    rows = []
    for fi, f in enumerate(L['fires']):
        h, w = f['shape']; M = unpack(f['M'], h * w).reshape(h, w)
        lc = lab60[f['r0']:f['r0'] + h, f['c0']:f['c0'] + w]
        fo = FOR[f['r0']:f['r0'] + h, f['c0']:f['c0'] + w]
        hit = lc[M & fo]
        if hit.size == 0 or hit.max() == 0: continue
        cnt = np.bincount(hit, minlength=lab.max() + 1); cnt[0] = 0
        ps = np.nonzero(cnt >= 3)[0]
        if len(ps) == 0: continue
        src = f['dotc'] if len(f['dotc']) else f['ign']
        if len(src) == 0:
            for p in ps: rows.append(dict(key=key, div=L['div'], fi=fi, fire=f['fire'], year=f['year'], patch=int(p), burn_ha=float(cnt[p] * C.CELL_HA), fire_ha=f['ha'], near=False, inside=False, status='no_start'))
            continue
        Mf = M.ravel(); lcf = lc.ravel()
        d = bfs_dist(Mf, h, w, src.astype(np.int64))
        day = np.zeros(h * w, np.int16); day[Mf] = f['day']
        sx = (src % w).mean() + f['c0']; sy = (src // w).mean() + f['r0']
        dots = f['dots']; dcell = dots[:, 0].astype(np.int64); dt = dots[:, 1]; okd = dcell >= 0
        for p in ps:
            pm = Mf & (lcf == p)
            idx = np.nonzero(pm)[0]
            Q = P[p]
            row = dict(key=key, div=L['div'], fi=fi, fire=f['fire'], year=f['year'], patch=int(p), burn_ha=float(cnt[p] * C.CELL_HA), fire_ha=f['ha'],
                       near=bool(np.isin(f['ign'], idx).any()), inside=bool(np.isin(src, idx).any()) if len(f['dotc']) else False)
            dd = d[idx]
            if row['inside'] and len(f['dotc']): row['status'] = 'inside'
            elif (dd >= 0).any():
                row['status'] = 'entered'   # 'from_out' below: entry point >= 400 m (beyond VIIRS location error) from the first-look dots
                m = dd >= 0; dmin = dd[m].min(); e = idx[m & (dd <= dmin + 1)]
                ex = (e % w).mean() + f['c0']; ey = (e // w).mean() + f['r0']
                _, j = Q['tree'].query([ex, ey]); row['seg'] = int(Q['seg'][j])
                row['bear'] = float(bearing(ex - Q['cx'], Q['cy'] - ey)); row['travel'] = float(bearing(ex - sx, sy - ey))
                row['ex'], row['ey'] = float(ex), float(ey); row['sx'], row['sy'] = float(sx), float(sy); row['dist_km'] = float(dmin * C.RES / 1000); row['from_out'] = bool(dmin * C.RES >= 400)
                # (a) daily growth
                dy = day[idx]; e2 = idx[dy == dy.min()]
                _, j = Q['tree'].query([(e2 % w).mean() + f['c0'], (e2 // w).mean() + f['r0']]); row['seg_day'] = int(Q['seg'][j])
                row['day_entry'] = int(dy.min()); row['patch_days'] = int(dy.max() - dy.min())
                # (b) dot order
                inp = np.zeros(len(dots), bool); inp[okd] = lcf[dcell[okd]] == p
                if inp.any():
                    ti = dt[inp].min(); pr_ = okd & ~inp & (dt < ti - 0.01)
                    if pr_.any():
                        tl = dt[pr_].max(); g = dcell[pr_ & (dt == tl)]
                        _, j = Q['tree'].query([(g % w).mean() + f['c0'], (g // w).mean() + f['r0']]); row['seg_dot'] = int(Q['seg'][j])
                    else: row['seg_dot'] = -1
            else: row['status'] = 'unreached'
            rows.append(row)
    meta = {p: dict(nseg=Q['nseg'], cx=Q['cx'], cy=Q['cy'], ring_km=Q['ring_km'], forest_ha=Q['forest_ha'], area_ha=Q['area_ha'], seg_km=Q['seg_km']) for p, Q in P.items()}
    rings = {p: (Q['ring'], Q['seg']) for p, Q in P.items()}
    print(key, pset, len(P), 'patches', len(rows), 'fire-patch rows', flush=True)
    return key, rows, meta, rings


def circ_R(b):
    a = np.radians(b); return float(np.hypot(np.cos(a).mean(), np.sin(a).mean())) if len(a) else np.nan


def chance_share(n, segkm, nsim=2000):
    pr = segkm / segkm.sum(); x = RNG.multinomial(n, pr, size=nsim).max(1) / n
    return float(x.mean()), x


def summarise(E, meta, years):
    """per patch, dominant fire per season among the defining seasons."""
    out = []
    E = E[E.year.isin(years)]
    for (key, p), g in E.groupby(['key', 'patch']):
        m = meta[key][p]
        dom = g.sort_values('burn_ha', ascending=False).drop_duplicates('year')
        ent = dom[dom.status == 'entered']
        r = dict(key=key, div=g['div'].iloc[0], patch=p, nseg=m['nseg'], ring_km=m['ring_km'], forest_ha=m['forest_ha'], n_years=len(dom),
                 n_inside=int((dom.status == 'inside').sum()), n_near=int(dom.near.sum()), n_entered=len(ent), n_unreached=int((dom.status == 'unreached').sum()),
                 n_fires=g.fire.nunique(), patch_burn_ha=float(dom.burn_ha.sum()))
        if len(ent):
            vc = ent.seg.value_counts(); r['mode_seg'] = int(vc.index[0]); r['mode_n'] = int(vc.iloc[0]); r['mode_share'] = float(vc.iloc[0] / len(ent))
            r['R_bear'] = circ_R(ent.bear.values); r['R_travel'] = circ_R(ent.travel.values)
            a = np.radians(ent.bear.values); r['mean_bear'] = float(bearing(np.sin(a).mean(), np.cos(a).mean()))
            if len(ent) >= 3:
                cs, sims = chance_share(len(ent), m['seg_km']); r['chance_share'] = cs; r['p_chance'] = float((sims >= r['mode_share'] - 1e-9).mean())
            ok = ent.seg_day.notna(); r['agree_day'] = float((ent.seg_day[ok] == ent.seg[ok]).mean()) if ok.any() else np.nan
            okd = ent.seg_dot.fillna(-1) >= 0; r['agree_dot'] = float((ent.seg_dot[okd] == ent.seg[okd]).mean()) if okd.any() else np.nan
            r['mode_seg_km'] = float(m['seg_km'][r['mode_seg']])
            eo = ent[ent.from_out.astype(bool)]; r['n_from_out'] = len(eo)
            if len(eo): vo = eo.seg.value_counts(); r['mode_share_out'] = float(vo.iloc[0] / len(eo)); r['mode_seg_out'] = int(vo.index[0])
            r['ha_via_mode'] = float(ent[ent.seg == r['mode_seg']].burn_ha.sum())
        out.append(r)
    S = pd.DataFrame(out)
    S['consistent'] = (S.n_entered.fillna(0) >= 3) & (S.mode_share.fillna(0) >= 0.6)
    S['consistent_out'] = (S.n_from_out.fillna(0) >= 3) & (S.mode_share_out.fillna(0) >= 0.6)
    return S


def main(pset):
    keys = [p.split('patches_')[1][:-4] for p in sorted(glob.glob(C.SC + 'patches_*.npz'))]
    with Pool(4) as pool: res = pool.map(one, [(k, pset) for k in keys], chunksize=1)
    E = pd.DataFrame(sum([r[1] for r in res], [])); meta = {r[0]: r[2] for r in res}; rings = {r[0]: r[3] for r in res}
    E.to_parquet(C.SC + f'entries_{pset}.parquet')
    years = list(C.TRAIN) if pset.startswith('tr') else list(C.ALL)
    S = summarise(E, meta, years); S.to_parquet(C.SC + f'patches_{pset}.parquet')
    pickle.dump(dict(meta=meta, rings=rings), open(C.SC + f'rings_{pset}.pkl', 'wb'))
    print(pset, 'patches with fires', len(S), 'consistent', int(S.consistent.sum()), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
