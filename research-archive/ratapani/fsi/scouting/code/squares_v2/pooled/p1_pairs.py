"""Step 1: every pair of passes by two different sensors that look at the same ground within 0-4 h (small gaps, incl.
Terra/Aqua MODIS), plus VIIRS pass pairs 10-14 h apart (the 12 h gap, any two VIIRS sensors incl. the same one).
For each pass pair, the points of both passes (fires: FIRMS type 0; static industrial: type 2) are linked into groups
(points closer than LINK m, union of both passes, so a group is "the same fire seen by both"). Every group that has
points in both passes is one pair row: the earlier look (A) and the later look (B), each with its own time.
Each look is summarised by its own detections only (centroid, FRP-weighted centroid, pixel count, pixel size, footprint
area, FRP, brightness). Nothing is merged across sensors.
Also a signed view-angle proxy per pass: the along-track pixel size grows monotonically away from nadir, so a quadratic
fit of track size against the across-track coordinate gives the nadir line; side = sign(across-track - nadir).
Out (scratch): pairs.parquet
"""
import os, sys
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
A = pd.read_parquet(f'{SC}/pts.parquet')
A = A[A.type.isin([0, 2])].reset_index(drop=True)
A['heading'] = np.where(A.daynight == 'D', 347.0, 193.0)
A.loc[A.sensor == 'Terra', 'heading'] = np.where(A.loc[A.sensor == 'Terra', 'daynight'] == 'D', 193.0, 347.0)
h = np.radians(A.heading.values)
A['p_scan'] = A.x * np.cos(h) - A.y * np.sin(h)        # coordinate along the scan direction
A['p_track'] = A.x * np.sin(h) + A.y * np.cos(h)
A['area'] = A.scan_m * A.track_m
# signed side of nadir per pass
side = np.zeros(len(A), np.int8); nadir_in = {}
for (s, p), g in A.groupby(['sensor', 'pass_id']):
    if len(g) < 30 or g.p_scan.max() - g.p_scan.min() < 2e5: continue
    q = (g.p_scan.values - g.p_scan.mean()) / 1e5
    c2, c1, c0 = np.polyfit(q, g.track_m.values, 2)
    if c2 <= 0: continue
    p0 = -c1 / (2 * c2)
    side[g.index.values] = np.sign(q - p0).astype(np.int8)
    nadir_in[(s, p)] = bool(q.min() < p0 < q.max())
A['side'] = side
print('passes with a side fit', len(nadir_in), 'nadir inside the MP box', np.mean(list(nadir_in.values())).round(3))
P = A.groupby(['sensor', 'pass_id']).t.min().reset_index().sort_values('t').reset_index(drop=True)
P['viirs'] = ~P.sensor.isin(['Terra', 'Aqua'])
idx = {k: g.index.values for k, g in A.groupby(['sensor', 'pass_id'])}
X = A.x.values; Y = A.y.values
pp = []
tv = P.t.values.astype('datetime64[s]').astype(np.int64)
for i in range(len(P)):
    for j in range(i + 1, len(P)):
        g = (tv[j] - tv[i]) / 60
        if g > 14 * 60: break
        a, b = P.iloc[i], P.iloc[j]
        small = g <= 240 and a.sensor != b.sensor
        long_ = 600 <= g <= 840 and a.viirs and b.viirs
        if small or long_: pp.append((i, j, g))
print('pass pairs', len(pp))
LAT = A.latitude.values; COS = np.cos(np.radians(LAT))
TS = A.t.values.astype('datetime64[s]').astype(np.int64).astype(float); LON = A.longitude.values; FRP = A.frp.values
SCN = A.scan_m.values; TRK = A.track_m.values; AR = A.area.values; BT = A.bright_ti4.values; SD = A.side.values; IH = A.ist_h.values
def look(ix):
    w = np.clip(FRP[ix], .01, None)
    return dict(t=pd.Timestamp(TS[ix].mean(), unit='s'), n=len(ix), lat=LAT[ix].mean(), lon=LON[ix].mean(),
                latw=np.average(LAT[ix], weights=w), lonw=np.average(LON[ix], weights=w),
                frp=FRP[ix].sum(), frp_max=FRP[ix].max(), scan=SCN[ix].mean(), track=TRK[ix].mean(), area=AR[ix].sum(),
                bt4=BT[ix].max(), side=int(np.sign(SD[ix].sum())), ist=float(IH[ix].mean()))
rows = []
for k, (i, j, g) in enumerate(pp):
    a, b = P.iloc[i], P.iloc[j]
    ia, ib = idx[(a.sensor, a.pass_id)], idx[(b.sensor, b.pass_id)]
    modis = (not a.viirs) or (not b.viirs); link = 2000.0 if modis else 1000.0
    for typ in (0, 2):
        ja = ia[A.type.values[ia] == typ]; jb = ib[A.type.values[ib] == typ]
        if not len(ja) or not len(jb): continue
        # only points of A near some point of B and vice versa can form a both-pass group: prefilter
        ta, tb = cKDTree(np.c_[X[ja], Y[ja]]), cKDTree(np.c_[X[jb], Y[jb]])
        na = np.array([len(v) > 0 for v in tb.query_ball_point(np.c_[X[ja], Y[ja]], 3 * link)])
        nb = np.array([len(v) > 0 for v in ta.query_ball_point(np.c_[X[jb], Y[jb]], 3 * link)])
        ja, jb = ja[na], jb[nb]
        if not len(ja) or not len(jb): continue
        U = np.r_[ja, jb]; lab_ab = np.r_[np.zeros(len(ja), bool), np.ones(len(jb), bool)]
        tr = cKDTree(np.c_[X[U], Y[U]]); e = tr.query_pairs(link, output_type='ndarray')
        M = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(U), len(U)))
        nc, lab = connected_components(M, directed=False)
        for c in np.unique(lab):
            m = lab == c
            if not (m & ~lab_ab).any() or not (m & lab_ab).any(): continue
            LA, LB = look(U[m & ~lab_ab]), look(U[m & lab_ab])
            r = dict(typ=typ, sA=a.sensor, sB=b.sensor, gap_min=(LB['t'] - LA['t']).total_seconds() / 60, dn=A.daynight.values[ja[0]])
            r.update({f'{q}A': v for q, v in LA.items()}); r.update({f'{q}B': v for q, v in LB.items()})
            c0 = np.cos(np.radians((LA['lat'] + LB['lat']) / 2))
            r['dE'] = (LB['lon'] - LA['lon']) * 111320 * c0; r['dN'] = (LB['lat'] - LA['lat']) * 110574
            r['dEw'] = (LB['lonw'] - LA['lonw']) * 111320 * c0; r['dNw'] = (LB['latw'] - LA['latw']) * 110574
            vt = A.vtm.values[U[m]]; r['vtm'] = int(np.bincount(np.clip(vt, 0, 255)).argmax())
            rows.append(r)
    if k % 2000 == 0: print(k, len(rows), flush=True)
R = pd.DataFrame(rows)
R['season'] = R.tA.dt.year
R.to_parquet(f'{SC}/pairs.parquet')
print(len(R)); print(R.groupby(['typ', 'sA', 'sB']).size().to_string())
