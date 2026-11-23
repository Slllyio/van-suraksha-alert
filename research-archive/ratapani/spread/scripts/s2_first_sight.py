"""FIRST SIGHTING (Akkshay Oct 18 05:02Z "so whats next"): passes where the 30 m scene saw the fire before any VIIRS dot.
scene_only = burnt patch touching hot pixels + 24.1 ha per hot-pixel front, at scene time; viirs_first = today's rule at the first VIIRS look;
viirs_same_area = first look dots with the scene map's area; both = scene + first look. Truth = burned by scene + 24 h.
Based on: Statewide version of section 10/11: does a mid-fire 30 m Sentinel-2/Landsat scene (burnt patch + hot line) improve the 24 h forecast
across Madhya Pradesh? (Akkshay Oct 18 04:14Z "go".)
Fires: big-fires b18 visible passes (mp_hotpix_passes.csv, >= 3 hot pixels, scene 0-3.5 h before a VIIRS day pass), one scene per pass
(Sentinel-2 first, smallest gap). Fire = VIIRS alerts (mp_alert_event.csv, S-NPP + NOAA-20) within 3 km of the pass and -72 h..+30 h of
the scene, single-linked at 750 m, keeping the cluster that holds the pass's event. Needs >= 1 VIIRS look before the scene.
Outline = union of the statewide burn scars (fire-alert-scars/mp: history, rest of MP, tiger reserves) of the cluster's events.
Timing truth (built here, Ratapani's method simplified): each VIIRS look pulls a pixel's burn time toward its own time with weight
1 / (straight-line distance to that look's 375 m blocks + 50 m)^4, inside the outline. (Ratapani used walking distance inside the outline
and a burning clock; this uses straight lines and clock time.) Truth = outline pixels with burn time <= scene + 24 h.
Scene (Planetary Computer, no login): mid-fire scene = the matched one; before-fire scene = latest same-collection scene 3-40 days before
the fire's first alert with >= 70% clear pixels in the window. Burnt patch LIVE = NBR(before) - NBR(mid) >= 0.10, plus the scene's hot
pixels (af_scan rule), patches touching a hot pixel or within 300 m of a VIIRS dot. No final scar and no post-fire scene used.
Rules at the scene time (blocks = 265 m discs around dots seen so far):
  rule        : blocks + 24.1 ha per active front, nearest to dots
  scene       : blocks + burnt patch + 24.1 ha per active front, nearest to dots or hot pixels
  same_area   : dots only, with the scene rule's total area
  python3 s2_statewide.py [NMAX]
"""
import os, sys, json, warnings, numpy as np, pandas as pd, rasterio, pystac_client, planetary_computer as pc
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
NMAX = int(sys.argv[1]) if len(sys.argv) > 1 else 1500; THREADS = int(os.environ.get('THREADS', 8))
R = '/mnt/project-files/research/big-fires/results'; MO = '/mnt/project-files/fire-alert-scars/mp/out'; SC = '/tmp/claude-0/statewide'; OUT = '/tmp/claude-0/firstsight'
MED = 24.1; LINK = 750.0; RES = 20.0
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
# ---- passes with a visible mid-fire scene
P = pd.read_csv(f'{R}/mp_hotpix_passes.csv'); PR = pd.read_csv(f'{R}/mp_hotpix_pairs.csv', parse_dates=['t', 't_scene'])
P = P[(P.visible == True) & (P.n_hot >= 3)][['pass_id', 'event_id', 'satellite']]
S = P.merge(PR, on=['pass_id', 'event_id', 'satellite']).sort_values(['sensor', 'gap_h'], ascending=[False, True]).drop_duplicates('pass_id')
S = S.sample(frac=1, random_state=0).head(NMAX).reset_index(drop=True); print('passes', len(S), flush=True)
# ---- alerts
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'scan', 'track', 'event_id'])
A = A[A.instrument == 'VIIRS'].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = to43(A.longitude.values, A.latitude.values); A = A.reset_index(drop=True); AT = cKDTree(A[['x', 'y']].values)
# ---- scars (geometry by event id)
need = set()
for r in S.itertuples():
    for i in AT.query_ball_point([r.x, r.y], 3000):
        if abs((A.t.iat[i] - r.t_scene).total_seconds()) <= 80 * 3600: need.add(A.event_id.iat[i])
G = {}
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom   # new split layout (Oct 18 07:00Z)
H = read_hist_geom(); H = H[H.event_id.isin(need)]
for e, w in zip(H.event_id, H.geometry):
    try: G[e] = wkt.loads(w)
    except Exception: pass
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


def read(it, sensor, tr, W, H):
    b = {}
    for k, a in BANDS[sensor].items():
        with rasterio.open(it.assets[a].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=tr, width=W, height=H, resampling=Resampling.bilinear, nodata=0) as v:
            x = v.read(1).astype(np.float32)
        if sensor == 's2':
            off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
            b[k] = np.where(x > 0, (x - off) / 1e4, np.nan)
        else: b[k] = np.where(x > 0, x * 0.0000275 - 0.2, np.nan)
    if sensor == 'ls' and 'qa_pixel' in it.assets:     # Landsat cloud / shadow mask
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


def one(r):
    try:
        Ts = r.t_scene
        near = A.iloc[AT.query_ball_point([r.x, r.y], 3000)]; near = near[(near.t >= Ts - pd.Timedelta(hours=72)) & (near.t <= Ts + pd.Timedelta(hours=30))].reset_index(drop=True)
        if not len(near): return dict(pass_id=r.pass_id, skip='no alerts')
        lab = clusters(near[['x', 'y']].values); keep = set(lab[(near.event_id == r.event_id).values])
        if not keep: keep = {lab[np.argmin(np.hypot(near.x - r.x, near.y - r.y))]}
        d = near[np.isin(lab, list(keep))].sort_values('t').reset_index(drop=True)
        if (d.t < Ts).any(): return dict(pass_id=r.pass_id, skip='VIIRS saw it before the scene')
        T1 = d.t.min(); kn = d[d.t <= T1 + pd.Timedelta(hours=2)]   # first VIIRS look (the comparison)
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
        # timing truth
        d['lk'] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
        tl = d.groupby('lk').t.min(); th = ((tl - Ts).dt.total_seconds() / 3600).values
        Dk = np.stack([np.maximum(cKDTree(d[d.lk == k][['x', 'y']].values).query(Px[dom])[0] - 265, 0) for k in tl.index], 1)
        w = 1 / (Dk + 50) ** 4; w /= w.sum(1, keepdims=True); T = np.full(len(Px), np.inf); T[dom] = (w * th[None]).sum(1)
        truth = dom & (T <= 24); new = dom & (T > 0) & (T <= 24)
        # scenes
        f = f'{OUT}/{r.pass_id.replace("|", "_").replace(":", "").replace(" ", "_")}.npz'
        if os.path.exists(f):
            z = np.load(f); mid = {k: z['m_' + k] for k in BANDS['s2']}; pre = {k: z['p_' + k] for k in BANDS['s2']}; pre_id = str(z['pre_id'])
        else:
            it = next(cat.search(collections=[COL[r.sensor]], ids=[r.scene]).items()); mid = read(it, r.sensor, tr, W, H)
            lon, lat = r.x, r.y; ll = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform(r.x, r.y)
            t0 = d.t.min(); q = {'eo:cloud_cover': {'lt': 40}}
            if r.sensor == 'ls': q['platform'] = {'in': ['landsat-8', 'landsat-9']}
            cands = sorted(cat.search(collections=[COL[r.sensor]], intersects={'type': 'Point', 'coordinates': list(ll)},
                                      datetime=f'{(t0 - pd.Timedelta(days=40)):%Y-%m-%d}/{(t0 - pd.Timedelta(days=3)):%Y-%m-%d}', query=q).items(),
                           key=lambda i: i.datetime, reverse=True)
            pre = None; pre_id = ''
            for c in cands[:6]:
                b = read(c, r.sensor, tr, W, H)
                if np.isfinite(b['nir'][dom.reshape(H, W)] if dom.any() else b['nir']).mean() >= .7: pre, pre_id = b, c.id; break
            if pre is None: return dict(pass_id=r.pass_id, skip='no clear before-fire scene')
            np.savez_compressed(f, **{'m_' + k: v.astype(np.float32) for k, v in mid.items()}, **{'p_' + k: v.astype(np.float32) for k, v in pre.items()}, pre_id=pre_id)
        with np.errstate(all='ignore'):
            nbr = lambda b: (b['nir'] - b['swir2']) / (b['nir'] + b['swir2'])
            dmid = nbr(pre) - nbr(mid)
            ndfi = (mid['swir2'] - mid['nir']) / (mid['swir2'] + mid['nir']); dnr = mid['nir'] - mid['red']
            hot = (ndfi > 0.5) & (dnr > -0.05) & (dnr < 0.15) & (mid['swir2'] > 0.10)
            if r.sensor == 'ls': hot |= (mid['swir2'] / mid['nir'] > 2.5) & (mid['swir2'] - mid['nir'] > 0.3) & (mid['swir2'] > 0.5)
        hot = np.nan_to_num(hot).astype(bool)
        if hot.sum() < 3: return dict(pass_id=r.pass_id, skip='< 3 hot pixels in window')
        BL = (np.isfinite(dmid) & (dmid >= 0.10)) | hot
        lb, nl = ndimage.label(BL)
        BL = np.isin(lb, list(set(np.unique(lb[hot & (lb > 0)]))))     # patches touching a hot pixel only (no VIIRS yet)
        br = BL.ravel(); hxy = Px[hot.ravel()]; xy = kn[['x', 'y']].values
        def place(score, base, n):
            s = np.where(base, -1, score); m = np.zeros(len(s), bool); m[np.argsort(s, kind='stable')[:n]] = True; return m
        nh = len(set(clusters(hxy)))                                   # fronts seen by the scene
        dh = cKDTree(hxy).query(Px)[0]; dd = cKDTree(xy).query(Px)[0]; foot = dd <= 265
        nact = len(set(clusters(xy)))                                  # fronts at the first VIIRS look
        nS = int(br.sum() + MED * nh / .04); fS = place(dh, br, nS)                       # scene alone, at scene time
        nR = int(foot.sum() + MED * nact / .04); fR = place(dd, foot, nR)                  # wait for first VIIRS look
        fB = place(dd, foot, nS)                                                            # first VIIRS look, scene's area
        fr = foot | br; nC = int(fr.sum() + MED * max(nact, nh) / .04); fC = place(np.minimum(dd, dh), fr, nC)   # both at first look
        lead_h = (T1 - Ts).total_seconds() / 3600
        return dict(pass_id=r.pass_id, event_id=r.event_id, sensor=r.sensor, scene=r.scene, pre_scene=pre_id, year=Ts.year, t_scene=str(Ts), lead_h=lead_h,
                    fronts_scene=nh, fronts_viirs=nact, dots_first=len(xy), scar_ha=dom.sum() * .04, truth_ha=truth.sum() * .04,
                    burnt_ha=br.sum() * .04, burnt_in_scar=float((br & dom).sum() / max(br.sum(), 1)), hot_px=int(hot.sum()),
                    scene_only=so(fS, truth), viirs_first=so(fR, truth), viirs_same_area=so(fB, truth), both=so(fC, truth),
                    area_scene=fS.sum() * .04, area_viirs=fR.sum() * .04)
    except Exception as e:
        return dict(pass_id=r.pass_id, skip='error ' + str(e)[:80])


rows = []
with ThreadPoolExecutor(THREADS) as ex:
    for i, o in enumerate(ex.map(one, list(S.itertuples()))):
        rows.append(o)
        if i % 50 == 0: print(i, len(S), pd.DataFrame(rows).get('skip', pd.Series(dtype=str)).fillna('ok').value_counts().to_dict(), flush=True)
Rr = pd.DataFrame(rows); Rr.to_csv(f'{OUT}/first_sight_rows.csv', index=False)
U = Rr[Rr.skip.isna()] if 'skip' in Rr else Rr
res = dict(passes_tried=len(Rr), used=len(U), skipped=Rr.skip.value_counts().to_dict() if 'skip' in Rr else {})
rng = np.random.default_rng(0)
def summ(Z):
    o = dict(n=len(Z), events=int(Z.event_id.nunique()), lead_h=round(float(Z.lead_h.median()), 2))
    for c in ['scene_only', 'viirs_first', 'viirs_same_area', 'both', 'burnt_in_scar', 'area_scene', 'area_viirs', 'truth_ha']: o[c] = round(float(Z[c].median()), 4); o[c + '_mean'] = round(float(Z[c].mean()), 4)
    for a, b in [('scene_only', 'viirs_first'), ('scene_only', 'viirs_same_area'), ('both', 'viirs_first')]:
        dl = (Z[a] - Z[b]).values
        o[f'{a}_vs_{b}_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
        o[f'{a}_vs_{b}_better/worse'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
    return o
if len(U):
    res['all'] = summ(U); res['by_sensor'] = {s: summ(z) for s, z in U.groupby('sensor') if len(z) > 10}
json.dump(res, open(f'{OUT}/first_sight.json', 'w'), indent=1); print(json.dumps(res, indent=1))
