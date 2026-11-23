"""Rays and ground features for every statewide front (events from r1_events.py). Same rules as fire-continuity c10 (reach) and
c15 (leak-free features), on all-MP layers instead of Ratapani ones:
  reach: 36 rays every 10 deg, 20 m steps to 4 km from the front's dot centre; the ray starts where it first enters the scar (within
    500 m) and stops at the first step after which 3 pixels (60 m) in a row are unburned; each front owns the ground nearer to it
    than to the fire's other fronts; a ray cut by another front or the window is 'censored' (reach unknown, not scored).
  features, from the dot centre along the full 0-2 km ray (the scar is never an input):
    distance to the first road (Overture 2026-09, within 40 m), first forest edge (60 m of non-tree, ESA WorldCover 10 m 2021),
    first cropland, first valley floor (> 10 m below the 1 km mean, Copernicus DEM 30 m); over 0-300 m and 300-1000 m: tree,
    grass/shrub, crop share, grade, local height, slope, share of earlier seasons burnt (tiger-reserve scars of earlier years);
    dots: ray vs the FRP-weighted offset of the front's dots (hot side), vs the dots' long axis, vs the bearing from earlier dots.
  The Ratapani fuel map and ERA5 wind (no effect in c9/c10) are not used.
Out: $RW_SCRATCH/rays/<event>.parquet, one row per (front, ray)."""
import os, pickle, sys, json, warnings
from multiprocessing import Pool
import numpy as np, pandas as pd
warnings.simplefilter('ignore')
os.environ.setdefault('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR'); os.environ.setdefault('CPL_VSIL_CURL_ALLOWED_EXTENSIONS', '.tif')
[os.environ.setdefault('CURL_CA_BUNDLE', c) for c in [os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')] if c]
[os.environ.setdefault(k, os.environ['CURL_CA_BUNDLE']) for k in ('GDAL_CURL_CA_BUNDLE', 'PROJ_CURL_CA_BUNDLE') if os.environ.get('CURL_CA_BUNDLE')]   # rasterio otherwise uses certifi only
os.environ.setdefault('GDAL_HTTP_MAX_RETRY', '5'); os.environ.setdefault('GDAL_HTTP_RETRY_DELAY', '2')
SCR = os.environ['RW_SCRATCH']; OUT = f'{SCR}/rays'; os.makedirs(OUT, exist_ok=True)
STEP, MAXS, NRAY, PAD = 20.0, 4000.0, 36, 5000.0
WC_URL = 'https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{}_Map.tif'
DEM_URL = 'https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{0}_00_{1}_00_DEM/Copernicus_DSM_COG_10_{0}_00_{1}_00_DEM.tif'


def read_grid(urls, tr, W, H, resampling, dtype):
    import rasterio
    from rasterio.vrt import WarpedVRT
    out = np.zeros((H, W), dtype)
    for u in urls:
        try:
            with rasterio.open(u) as src, WarpedVRT(src, crs='EPSG:32643', transform=tr, width=W, height=H, resampling=resampling, nodata=0) as v:
                a = v.read(1)
            out = np.where(a != 0, a, out).astype(dtype)
        except Exception as e:
            if 'not recognized' not in str(e) and '404' not in str(e) and 'No such file' not in str(e): raise
    return out


def layers(x0, y1, W, H):
    from pyproj import Transformer
    from rasterio.transform import from_origin
    from rasterio.enums import Resampling
    inv = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform
    lo, la = inv(np.array([x0, x0 + W * STEP, x0, x0 + W * STEP]), np.array([y1, y1, y1 - H * STEP, y1 - H * STEP]))
    tr = from_origin(x0, y1, STEP, STEP)
    wct = {f'N{int(np.floor(a / 3) * 3):02d}E{int(np.floor(o / 3) * 3):03d}' for a in [la.min(), la.max()] for o in [lo.min(), lo.max()]}
    wc = read_grid([WC_URL.format(t) for t in wct], tr, W, H, Resampling.nearest, np.uint8)
    dt = {(f'N{int(np.floor(a)):02d}', f'E{int(np.floor(o)):03d}') for a in [la.min(), la.max()] for o in [lo.min(), lo.max()]}
    el = read_grid([DEM_URL.format(*t) for t in dt], tr, W, H, Resampling.bilinear, np.float32)
    return tr, wc, el


def one(task):
    try:
        return _one(task)
    except Exception as e:
        print('skip', task[0]['event'], str(e)[:80], flush=True); return 0


def _one(task):
    ev, roads_wkb, past = task
    f = f'{OUT}/{ev["event"]}.parquet'
    if os.path.exists(f): return 0
    from rasterio import features
    from scipy.ndimage import uniform_filter, binary_dilation
    from shapely import wkb as W_
    O = ev['origins']; scar = ev['scar']
    bx = np.r_[scar.bounds[0], scar.bounds[2], [o['x'] for o in O]]; by = np.r_[scar.bounds[1], scar.bounds[3], [o['y'] for o in O]]
    x0, y1 = np.floor((bx.min() - PAD) / STEP) * STEP, np.ceil((by.max() + PAD) / STEP) * STEP
    Wd, Hd = int((bx.max() + PAD - x0) / STEP), int((y1 - by.min() + PAD) / STEP)
    tr, wc, el = layers(x0, y1, Wd, Hd)
    dom = features.rasterize([scar], out_shape=(Hd, Wd), transform=tr).astype(bool)
    rd = np.zeros((Hd, Wd), bool)
    if roads_wkb:
        rd = features.rasterize([(W_.loads(g), 1) for g in roads_wkb], out_shape=(Hd, Wd), transform=tr, all_touched=True).astype(bool)
    rd = binary_dilation(rd, iterations=2)
    pb = np.zeros((Hd, Wd), np.float32)
    for g in past: pb += features.rasterize([g], out_shape=(Hd, Wd), transform=tr).astype(np.float32)
    pb /= max(ev['season'] - 2017, 1)
    elf = el.astype(float); loc = elf - uniform_filter(elf, 51)
    gy, gx = np.gradient(elf, STEP); slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    tree = wc == 10; grass = np.isin(wc, [20, 30]); crop = wc == 40
    S = np.arange(0, MAXS + 1, STEP); Sf = np.arange(20, 2001, 20.0)
    OXY = np.array([[o['x'], o['y']] for o in O]); rows = []
    rc = lambda X, Y: (np.floor((y1 - Y) / STEP).astype(int), np.floor((X - x0) / STEP).astype(int))
    for oi, o in enumerate(O):
        for j in range(NRAY):
            az = np.radians(j * 10)
            # reach (c10)
            X = o['x'] + S * np.sin(az); Y = o['y'] + S * np.cos(az); rr, cc = rc(X, Y)
            inb = (rr >= 0) & (rr < Hd) & (cc >= 0) & (cc < Wd); rr2, cc2 = np.clip(rr, 0, Hd - 1), np.clip(cc, 0, Wd - 1)
            ins = dom[rr2, cc2] & inb
            own = np.ones(len(S), bool)
            if len(OXY) > 1: own = np.hypot(X[:, None] - OXY[None, :, 0], Y[:, None] - OXY[None, :, 1]).argmin(1) == oi
            ent = np.where(ins[:26])[0]; reach, cens = np.nan, True
            if len(ent):
                e = ent[0]; out3 = ~ins & np.r_[~ins[1:], True] & np.r_[~ins[2:], True, True]
                lim = np.where(~(own & inb))[0]; lim = lim[lim > e]; lim = lim[0] if len(lim) else len(S)
                st = np.where(out3 & (np.arange(len(S)) > e))[0]; st = st[0] if len(st) else None
                if st is not None and st >= lim: st = None
                reach = (S[st] if st is not None else S[lim - 1]) - S[e]; cens = st is None
            # features (c15, leak-free)
            X = o['x'] + Sf * np.sin(az); Y = o['y'] + Sf * np.cos(az); rr, cc = rc(X, Y); rr, cc = np.clip(rr, 0, Hd - 1), np.clip(cc, 0, Wd - 1)
            t_ = tree[rr, cc]; nt3 = np.r_[[not t_[i:i + 3].any() for i in range(len(Sf) - 2)], False, False]
            fd = lambda m: float(Sf[np.argmax(m)]) if m.any() else 4000.0
            ev_ = elf[rr, cc]; gr = np.gradient(ev_, STEP)
            rec = dict(event=ev['event'], origin=o['origin'], ray=j, reach=reach, cens=cens,
                       d_road=fd(rd[rr, cc]), d_edge=fd(nt3), d_crop=fd(crop[rr, cc]), d_valley=fd(loc[rr, cc] < -10))
            for lo_, hi in [(0, 300), (300, 1000)]:
                m = (Sf > lo_) & (Sf <= hi)
                rec.update({f'tree_{lo_}_{hi}': t_[m].mean(), f'grass_{lo_}_{hi}': grass[rr, cc][m].mean(), f'crop_{lo_}_{hi}': crop[rr, cc][m].mean(),
                            f'grade_{lo_}_{hi}': gr[m].mean(), f'local_height_{lo_}_{hi}': loc[rr, cc][m].mean(), f'slope_{lo_}_{hi}': slope[rr, cc][m].mean(),
                            f'prior_burns_{lo_}_{hi}': pb[rr, cc][m].mean()})
            azd = j * 10
            rec['hot_side'] = np.cos(np.radians(azd - o['hot_b'])) * min(o['hot_m'], 300) / 300
            rec['along_dots'] = abs(np.cos(np.radians(azd - o['ax']))) * np.log(o['el']) if np.isfinite(o['ax']) else 0.0
            rec['momentum'] = np.cos(np.radians(azd - o['mom'])) if np.isfinite(o['mom']) else np.nan
            rows.append(rec)
    pd.DataFrame(rows).to_parquet(f)
    return 1


def tasks():
    from shapely.strtree import STRtree
    E = pickle.load(open(f'{SCR}/events.pkl', 'rb'))
    if len(sys.argv) > 1: E = E[:int(sys.argv[1])]
    RD = pd.read_parquet(f'{SCR}/mp_roads_bbox.parquet')
    from pyproj import Transformer
    inv = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform
    allsc = [(e['season'], e['scar']) for e in pickle.load(open(f'{SCR}/events.pkl', 'rb'))]
    tree = STRtree([g for _, g in allsc]); seas = np.array([s for s, _ in allsc])
    for ev in E:
        O = ev['origins']; b = ev['scar'].bounds
        bx = [b[0], b[2]] + [o['x'] for o in O]; by = [b[1], b[3]] + [o['y'] for o in O]
        lo, la = inv(np.array([min(bx) - PAD, max(bx) + PAD]), np.array([min(by) - PAD, max(by) + PAD]))
        m = (RD.x1.values >= lo[0]) & (RD.x0.values <= lo[1]) & (RD.y1.values >= la[0]) & (RD.y0.values <= la[1])
        from shapely import wkb as W_
        from shapely.ops import transform as stf
        to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
        rw = [W_.dumps(stf(to43, W_.loads(g))) for g in RD.wkb.values[m]]
        from shapely.geometry import box
        idx = tree.query(box(min(bx) - PAD, min(by) - PAD, max(bx) + PAD, max(by) + PAD))
        past = [allsc[i][1] for i in idx if seas[i] < ev['season']]
        yield ev, rw, past


if __name__ == '__main__':
    n = 0
    with Pool(int(os.environ.get('RW_PROCS', '6'))) as P:
        for k, r in enumerate(P.imap_unordered(one, tasks(), chunksize=1)):
            n += r
            if k % 100 == 0: print(k, n, flush=True)
    print('done', n)
