"""[big-fires b19d, 20 Oct: arrow vs VIIRS dots once the arrow can actually ARRIVE live.]
Live, the mid-fire Sentinel-2 scene (~10:30-10:45 IST) is published ~5-6 h later (~16:00-17:00 IST). By then the afternoon VIIRS look
(~13:30 IST, in by ~14:30 IST) is known. So, on the same usable passes as b19b (results/statewide_direction_rows.csv, skip empty):
  a) arrow         : burnt patch centroid -> hot-pixel centroid (b19b, unchanged)
  b) dots_before   : earlier looks centroid -> latest look BEFORE the scene (b19b, unchanged)
  c) dots_arrival  : same rule with every VIIRS look up to scene + 6 h (Ta)
  d) truth at arrival, from b19b's VIIRS-look timing map (T, hours after the scene):
       scar_arrival : outline pixels outside the burnt patch with T > 6 (scar not yet burning by Ta)
       24h_arrival  : outline pixels outside the burnt patch with 6 < T <= 30 (new burning in the 24 h after Ta)
     (b19b's original truths, scar remainder and 0-24 h new burning, are recomputed too as a check.)
All directions are compared with (truth centroid - burnt patch centroid), as in b19b. Within-45-deg share with 95% CI by fire (bootstrap
over fires), paired differences bootstrapped by fire, early fires = <= 2 VIIRS looks before the scene.
Inputs: results/mp_hotpix_passes.csv, mp_hotpix_pairs.csv, statewide_direction_rows.csv; fire-alert-scars/mp/out alerts + scars;
scenes from Planetary Computer (mid scene and b19b's recorded before-fire scene id). Scene cache in /tmp (S2DIR_SCRATCH).
Scar geometry: GEOM=backup (default) reads the old appended history file the same way b19b did (stops at the first corrupt block), so the
outlines match b19b's run; GEOM=current uses part1 + the per-batch folder + redo folder.
Output: results/arrow_at_arrival.json, results/arrow_at_arrival.md (+ per-pass rows in /tmp only).
  python3 b19d_arrow_at_arrival.py
"""
import os, sys, json, gzip, csv, glob, warnings, numpy as np, pandas as pd, rasterio, pystac_client, planetary_computer as pc
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio import features
from scipy import ndimage
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely import wkt
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as stransform
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings('ignore')
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF', GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='2')
THREADS = int(os.environ.get('THREADS', 8)); GEOM = os.environ.get('GEOM', 'backup'); LAG = float(os.environ.get('LAG_H', 6))
R = '/mnt/project-files/research/big-fires/results'; MO = '/mnt/project-files/fire-alert-scars/mp/out'
SC = os.environ.get('S2DIR_SCRATCH', '/tmp/claude-0/s2dir_b19d'); os.makedirs(SC, exist_ok=True)
LINK = 750.0; RES = 20.0
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
# ---- the same usable passes as b19b
OLD = pd.read_csv(f'{R}/statewide_direction_rows.csv'); OLD = OLD[OLD.skip.isna()].set_index('pass_id')
P = pd.read_csv(f'{R}/mp_hotpix_passes.csv'); PR = pd.read_csv(f'{R}/mp_hotpix_pairs.csv', parse_dates=['t', 't_scene'])
P = P[(P.visible == True) & (P.n_hot >= 3)][['pass_id', 'event_id', 'satellite']]
S = P.merge(PR, on=['pass_id', 'event_id', 'satellite']).sort_values(['sensor', 'gap_h'], ascending=[False, True]).drop_duplicates('pass_id')
S = S[S.pass_id.isin(OLD.index)].reset_index(drop=True)
S = S[[OLD.loc[p, 'scene'] == s for p, s in zip(S.pass_id, S.scene)]].reset_index(drop=True); print('passes', len(S), 'of', len(OLD), flush=True)
# ---- alerts
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
A = A[A.instrument == 'VIIRS'].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = to43(A.longitude.values, A.latitude.values); A = A.reset_index(drop=True); AT = cKDTree(A[['x', 'y']].values)
# ---- scars
need = set()
for r in S.itertuples():
    for i in AT.query_ball_point([r.x, r.y], 3000):
        if abs((A.t.iat[i] - r.t_scene).total_seconds()) <= 80 * 3600: need.add(A.event_id.iat[i])
G = {}; csv.field_size_limit(10 ** 9)
srcs = [f'{MO}/scars_mp_hist_geom.backup_2026-10-18.csv.gz'] if GEOM == 'backup' else \
    [f'{MO}/scars_mp_hist_geom_part1.csv.gz'] + sorted(glob.glob(f'{MO}/scars_mp_hist_geom/*.csv.gz')) + sorted(glob.glob(f'{MO}/scars_mp_hist_redo_geom/*.csv.gz'))
for fn in srcs:
    try:
        with gzip.open(fn, 'rt') as fh:
            rd = csv.reader(fh); next(rd)
            for row in rd:
                if len(row) == 2 and row[0] in need:
                    try: G[row[0]] = wkt.loads(row[1])
                    except Exception: pass
    except Exception as e: print(os.path.basename(fn), 'read up to a partial block:', str(e)[:60], flush=True)
for f in ['scars_rest_of_mp.csv', 'scars_tiger_reserves.csv']:
    g = pd.read_csv(f'{MO}/{f}', usecols=['event_id', 'status', 'geometry']); g = g[g.event_id.isin(need) & g.status.isin(['scar', 'scar_faint']) & g.geometry.notna()]
    for r in g.itertuples():
        if r.event_id not in G: G[r.event_id] = shape(json.loads(r.geometry))
print('scar geometries', len(G), 'of', len(need), flush=True)
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1', modifier=pc.sign_inplace)
BANDS = {'s2': dict(red='B04', nir='B8A', swir2='B12'), 'ls': dict(red='red', nir='nir08', swir2='swir22')}
COL = {'s2': 'sentinel-2-l2a', 'ls': 'landsat-c2-l2'}


def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]


def read(it, sensor, tr, W, H):   # identical to b19b
    b = {}
    for k, a in BANDS[sensor].items():
        with rasterio.open(it.assets[a].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=tr, width=W, height=H, resampling=Resampling.bilinear, nodata=0) as v:
            x = v.read(1).astype(np.float32)
        if sensor == 's2':
            off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
            b[k] = np.where(x > 0, (x - off) / 1e4, np.nan)
        else: b[k] = np.where(x > 0, x * 0.0000275 - 0.2, np.nan)
    if sensor == 'ls' and 'qa_pixel' in it.assets:
        with rasterio.open(it.assets['qa_pixel'].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=tr, width=W, height=H, resampling=Resampling.nearest, nodata=1) as v:
            q = v.read(1).astype(np.int64)
        bad = (q & (1 << 3) | q & (1 << 4) | q & 1) > 0
        for k in b: b[k][bad] = np.nan
    if sensor == 's2' and 'SCL' in it.assets:
        with rasterio.open(it.assets['SCL'].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=tr, width=W, height=H, resampling=Resampling.nearest, nodata=0) as v:
            q = v.read(1)
        bad = np.isin(q, [0, 1, 3, 8, 9, 10])
        for k in b: b[k][bad] = np.nan
    return b


def ang(a, b): return float(np.degrees(np.abs(np.arctan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))))


def dots_dir(kk):
    """earlier looks centroid -> latest look (looks = alerts split at > 2 h gaps); None if only one look"""
    kk = kk.assign(lk=(kk.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1); k = kk.lk.max()
    if k < 1: return None, int(k + 1)
    return kk[kk.lk == k][['x', 'y']].values.mean(0) - kk[kk.lk < k][['x', 'y']].values.mean(0), int(k + 1)


def one(r):
    try:
        Ts = r.t_scene; Ta = Ts + pd.Timedelta(hours=LAG)
        near = A.iloc[AT.query_ball_point([r.x, r.y], 3000)]; near = near[(near.t >= Ts - pd.Timedelta(hours=72)) & (near.t <= Ts + pd.Timedelta(hours=30))].reset_index(drop=True)
        lab = clusters(near[['x', 'y']].values); keep = set(lab[(near.event_id == r.event_id).values])
        if not keep: keep = {lab[np.argmin(np.hypot(near.x - r.x, near.y - r.y))]}
        d = near[np.isin(lab, list(keep))].sort_values('t').reset_index(drop=True)
        kn = d[d.t < Ts]; ka = d[d.t <= Ta]; mid_looks = d[(d.t >= Ts) & (d.t <= Ta)]
        if not len(kn): return dict(pass_id=r.pass_id, skip='no VIIRS look before scene')
        geoms = [G[e] for e in d.event_id.unique() if e in G]
        if not geoms: return dict(pass_id=r.pass_id, skip='no scar')
        poly = stransform(lambda x, y, z=None: to43(x, y), unary_union(geoms))
        if poly.area < 2e4: return dict(pass_id=r.pass_id, skip='scar < 2 ha')
        xs = np.r_[d.x, poly.bounds[0], poly.bounds[2]]; ys = np.r_[d.y, poly.bounds[1], poly.bounds[3]]
        x0, x1, y0, y1 = xs.min() - 800, xs.max() + 800, ys.min() - 800, ys.max() + 800
        if x1 - x0 > 12000 or y1 - y0 > 12000: return dict(pass_id=r.pass_id, skip='too big')
        W, H = int((x1 - x0) / RES), int((y1 - y0) / RES); tr = from_origin(x0, y1, RES, RES)
        dom = features.rasterize([(mapping(poly), 1)], out_shape=(H, W), transform=tr).astype(bool).ravel()
        rr, cc = np.mgrid[0:H, 0:W]; Px = np.c_[(x0 + (cc + .5) * RES).ravel(), (y1 - (rr + .5) * RES).ravel()]
        # timing map (b19b): hours after the scene at which each outline pixel burns
        d['lk'] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
        tl = d.groupby('lk').t.min(); th = ((tl - Ts).dt.total_seconds() / 3600).values
        Dk = np.stack([np.maximum(cKDTree(d[d.lk == k][['x', 'y']].values).query(Px[dom])[0] - 265, 0) for k in tl.index], 1)
        w = 1 / (Dk + 50) ** 4; w /= w.sum(1, keepdims=True); T = np.full(len(Px), np.inf); T[dom] = (w * th[None]).sum(1)
        # scenes (mid = matched scene; before = the scene id b19b recorded)
        f = f'{SC}/{r.pass_id.replace("|", "_").replace(":", "").replace(" ", "_")}.npz'
        if os.path.exists(f):
            z = np.load(f); mid = {k: z['m_' + k] for k in BANDS['s2']}; pre = {k: z['p_' + k] for k in BANDS['s2']}
        else:
            it = next(cat.search(collections=[COL[r.sensor]], ids=[r.scene]).items()); mid = read(it, r.sensor, tr, W, H)
            pit = next(cat.search(collections=[COL[r.sensor]], ids=[OLD.loc[r.pass_id, 'pre_scene']]).items()); pre = read(pit, r.sensor, tr, W, H)
            np.savez_compressed(f, **{'m_' + k: v.astype(np.float32) for k, v in mid.items()}, **{'p_' + k: v.astype(np.float32) for k, v in pre.items()})
        with np.errstate(all='ignore'):
            nbr = lambda b: (b['nir'] - b['swir2']) / (b['nir'] + b['swir2'])
            dmid = nbr(pre) - nbr(mid)
            ndfi = (mid['swir2'] - mid['nir']) / (mid['swir2'] + mid['nir']); dnr = mid['nir'] - mid['red']
            hot = (ndfi > 0.5) & (dnr > -0.05) & (dnr < 0.15) & (mid['swir2'] > 0.10)
            if r.sensor == 'ls': hot |= (mid['swir2'] / mid['nir'] > 2.5) & (mid['swir2'] - mid['nir'] > 0.3) & (mid['swir2'] > 0.5)
        hot = np.nan_to_num(hot).astype(bool)
        if hot.sum() < 3: return dict(pass_id=r.pass_id, skip='< 3 hot pixels in window')
        BL = (np.isfinite(dmid) & (dmid >= 0.10)) | hot
        xy = kn[['x', 'y']].values; lb, nl = ndimage.label(BL)
        if nl:
            lx = lb.ravel(); dd0 = cKDTree(xy).query(Px)[0]
            keep_l = set(np.unique(lx[hot.ravel() & (lx > 0)])) | set(np.unique(lx[(dd0 <= 300) & (lx > 0)]))
            BL = np.isin(lb, list(keep_l))
        br = BL.ravel(); hxy = Px[hot.ravel()]
        if br.sum() < 10: return dict(pass_id=r.pass_id, skip='burnt patch < 10 px')
        cb = Px[br].mean(0); arrow = hxy.mean(0) - cb
        vb, nlb = dots_dir(kn); va, nla = dots_dir(ka)
        truths = dict(scar=dom & ~br, h24=dom & (T > 0) & (T <= 24) & ~br,                    # b19b truths (check)
                      scar_arrival=dom & ~br & (T > LAG), h24_arrival=dom & (T > LAG) & (T <= LAG + 24) & ~br)
        o = dict(pass_id=r.pass_id, event_id=r.event_id, sensor=r.sensor, t_scene=str(Ts), looks_before=nlb, looks_to_arrival=nla,
                 alerts_scene_to_arrival=len(mid_looks), look_scene_to_arrival=bool(len(mid_looks)),
                 hours_scene_to_first_later_look=float((mid_looks.t.min() - Ts).total_seconds() / 3600) if len(mid_looks) else np.nan,
                 scar_ha=dom.sum() * .04, burnt_ha=br.sum() * .04, hot_px=int(hot.sum()))
        for nm, msk in truths.items():
            o[f'px_{nm}'] = int(msk.sum())
            if msk.sum() >= 50:
                tv = Px[msk].mean(0) - cb
                o[f'ang_arrow_{nm}'] = ang(arrow, tv)
                if vb is not None: o[f'ang_dotsb_{nm}'] = ang(vb, tv)
                if va is not None: o[f'ang_dotsa_{nm}'] = ang(va, tv)
        return o
    except Exception as e:
        return dict(pass_id=r.pass_id, skip='error ' + str(e)[:80])


rows = []
with ThreadPoolExecutor(THREADS) as ex:
    for i, o in enumerate(ex.map(one, list(S.itertuples()))):
        rows.append(o)
        if i % 25 == 0: print(i, len(S), flush=True)
Rr = pd.DataFrame(rows); Rr.to_csv(f'{SC}/arrow_at_arrival_rows.csv', index=False)
U = Rr[Rr.skip.isna()].copy() if 'skip' in Rr else Rr.copy()
# ---- check against b19b
chk = {}
for new_c, old_c in (('ang_arrow_scar', 'ang_arrow_scar'), ('ang_dotsb_scar', 'ang_dots_scar'), ('ang_arrow_h24', 'ang_arrow_24h'), ('ang_dotsb_h24', 'ang_dots_24h')):
    m = U.set_index('pass_id')[new_c].dropna(); o_ = OLD[old_c].reindex(m.index); ok = o_.notna()
    chk[new_c] = dict(n_new=int(len(m)), n_old=int(OLD[old_c].notna().sum()), n_both=int(ok.sum()), same_within_1deg=int((np.abs(m[ok] - o_[ok]) <= 1).sum()))

rng = np.random.default_rng(0); NB = 2000


def boot_by_fire(Z, fn):
    ev = Z.event_id.values; ue = np.unique(ev); idx = {e: np.where(ev == e)[0] for e in ue}
    b = [fn(Z.iloc[np.concatenate([idx[e] for e in rng.choice(ue, len(ue))])]) for _ in range(NB)]
    return [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]


def sc(Z, c):
    Z = Z.dropna(subset=[c])
    if not len(Z): return dict(n=0)
    f = lambda z: float((z[c] <= 45).mean())
    return dict(n=int(len(Z)), fires=int(Z.event_id.nunique()), within_45=round(f(Z), 3), ci=boot_by_fire(Z, f), median_angle=round(float(Z[c].median()), 1))


def paired(Z, a, b):
    Z = Z.dropna(subset=[a, b])
    if not len(Z): return dict(n=0)
    f = lambda z: float((z[a] <= 45).mean() - (z[b] <= 45).mean())
    return dict(n=int(len(Z)), fires=int(Z.event_id.nunique()), first=round(float((Z[a] <= 45).mean()), 3), second=round(float((Z[b] <= 45).mean()), 3),
                diff=round(f(Z), 3), diff_ci_by_fire=boot_by_fire(Z, f))


res = dict(script='b19d_arrow_at_arrival.py', lag_hours=LAG, geometry_source=GEOM, b19b_used=int(len(OLD)), passes_run=int(len(Rr)), used=int(len(U)),
           skipped=Rr.skip.value_counts().to_dict() if 'skip' in Rr else {}, check_vs_b19b=chk,
           viirs_look_scene_to_arrival=dict(passes=int(U.look_scene_to_arrival.sum()), of=int(len(U)),
                                            median_hours_scene_to_that_look=round(float(U.hours_scene_to_first_later_look.median()), 2),
                                            early_le2_looks=[int(U[U.looks_before <= 2].look_scene_to_arrival.sum()), int((U.looks_before <= 2).sum())]),
           dots_available=dict(before_scene=int(U.looks_before.ge(2).sum()), up_to_arrival=int(U.looks_to_arrival.ge(2).sum()), of=int(len(U))),
           notes='within_45 = share of passes whose direction is within 45 deg of (truth centroid - burnt patch centroid); CIs bootstrap over fires (2000). '
                 'dots_before = earlier looks -> latest look before the scene; dots_arrival = same rule with looks up to scene + LAG h. '
                 'scar_arrival = scar outside the burnt patch not burning by scene + LAG (timing map); h24_arrival = new burning in the 24 h after scene + LAG.')
for nm in ('scar_arrival', 'h24_arrival', 'scar', 'h24'):
    a, b, c = f'ang_arrow_{nm}', f'ang_dotsb_{nm}', f'ang_dotsa_{nm}'
    if a not in U: continue
    Z = U.dropna(subset=[a]); E = Z[Z.looks_before <= 2]
    o = dict(arrow=sc(Z, a), dots_before=sc(Z, b), dots_arrival=sc(Z, c),
             paired_arrow_minus_dots_arrival=paired(Z, a, c), paired_arrow_minus_dots_before=paired(Z, a, b),
             paired_dots_arrival_minus_dots_before=paired(Z, c, b),
             early_le2_looks=dict(arrow=sc(E, a), dots_before=sc(E, b), dots_arrival=sc(E, c), paired_arrow_minus_dots_arrival=paired(E, a, c)),
             later_ge3_looks=dict(arrow=sc(Z[Z.looks_before >= 3], a), dots_arrival=sc(Z[Z.looks_before >= 3], c),
                                  paired_arrow_minus_dots_arrival=paired(Z[Z.looks_before >= 3], a, c)),
             with_look_scene_to_arrival=dict(arrow=sc(Z[Z.look_scene_to_arrival], a), dots_arrival=sc(Z[Z.look_scene_to_arrival], c),
                                             paired_arrow_minus_dots_arrival=paired(Z[Z.look_scene_to_arrival], a, c)))
    three = Z.dropna(subset=[b, c]); o['same_passes_all_three'] = dict(n=int(len(three)), arrow=sc(three, a), dots_before=sc(three, b), dots_arrival=sc(three, c))
    res[f'truth_{nm}'] = o
json.dump(res, open(f'{R}/arrow_at_arrival.json', 'w'), indent=1); print(json.dumps(res, indent=1))
