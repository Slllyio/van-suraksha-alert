"""ECOSTRESS 70 m land-surface temperature over active fires (Akkshay 17 Oct 08:25Z "then use 70m thermal sensor").
Step 1 (no login needed): every ECO_L2T_LSTE granule over Ratapani from the NASA catalogue (results/ecostress_granules.csv),
        matched to fires by time (pass between the fire's first and last detection) and by tile (scar centre inside the tile).
Step 2 (needs a NASA Earthdata login): download LST, QC, cloud, view_zenith, LST_err per granule (~0.5 MB each), keep a
        2 km margin around each matched fire's scar, drop the rest. Clips go to the scratchpad cache (rebuildable).
Login: environment variable EARTHDATA_TOKEN (Earthdata bearer token). Never stored in a file, in code, or in chat.
"""
import os, sys, json, pickle, urllib.request, urllib.parse, tempfile
import numpy as np, pandas as pd, rasterio, requests
from rasterio.windows import from_bounds
from concurrent.futures import ThreadPoolExecutor
R = '/mnt/project-files/research/big-fires/results'
CACHE = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/ecostress'; os.makedirs(CACHE, exist_ok=True)
TOK = os.environ.get('EARTHDATA_TOKEN')
SP = f'{R}/fire_scars.pkl' if os.path.exists(f'{R}/fire_scars.pkl') else '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/fire_scars.pkl'
S = pickle.load(open(SP, 'rb'))
LAYERS = ['LST', 'QC', 'cloud', 'view_zenith', 'LST_err']
# ---- step 1: granules (all tiles), time + tile match
gpath = f'{R}/ecostress_granules.csv'
if not os.path.exists(gpath):
    rows = []
    for sn, ver in [('ECO_L2T_LSTE', '002'), ('ECO_L2T_LSTE', '003')]:
        page = 1
        while True:
            q = urllib.parse.urlencode({'short_name': sn, 'version': ver, 'bounding_box': '77.3174,22.7850,78.0848,23.1363', 'page_size': 2000, 'page_num': page})
            d = json.load(urllib.request.urlopen(f'https://cmr.earthdata.nasa.gov/search/granules.json?{q}', timeout=60)); e = d['feed']['entry']
            rows += [dict(product=sn, ver=ver, id=g['title'], t0=g.get('time_start'), day=g.get('day_night_flag')) for g in e]
            if len(e) < 2000: break
            page += 1
    pd.DataFrame(rows).to_csv(gpath, index=False)
E = pd.read_csv(gpath); E['t0'] = pd.to_datetime(E.t0).dt.tz_localize(None); E['tile'] = E.id.str.split('_').str[5]
TILES = {'43QGF': (699960.0, 2490280.0, 809720.0, 2600040.0)}   # left, bottom, right, top from the first file read; others filled on the fly
def tile_bounds(tile, gid, ver):
    if tile in TILES: return TILES[tile]
    u = f'https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/ECO_L2T_LSTE.{ver}/{gid}/{gid}_QC.tif'
    r = requests.get(u, headers={'Authorization': f'Bearer {TOK}'}, timeout=120)
    with tempfile.NamedTemporaryFile(suffix='.tif') as f:
        f.write(r.content); f.flush()
        with rasterio.open(f.name) as ds: b = ds.bounds
    TILES[tile] = (b.left, b.bottom, b.right, b.top); return TILES[tile]
P = pd.read_csv(f'{R}/passes.csv', parse_dates=['t']); span = P.groupby('fire').t.agg(['min', 'max'])
pairs = []
for fid, r in span.iterrows():
    c = S[fid].centroid; sel = E[(E.t0 >= r['min']) & (E.t0 <= r['max'])]
    for _, g in sel.iterrows():
        pairs.append(dict(fire=fid, granule=g.id, ver=g.ver, tile=g.tile, t0=g.t0, day=g.day, cx=c.x, cy=c.y))
PR = pd.DataFrame(pairs); print('time matches (all tiles):', len(PR), 'granules', PR.granule.nunique())
if not TOK: print('NO EARTHDATA_TOKEN: stopping after the time match.'); sys.exit(0)
keep = []
for _, r in PR.iterrows():
    l, b, rt, t = tile_bounds(r.tile, r.granule, f'{int(r.ver):03d}')
    if l <= r.cx <= rt and b <= r.cy <= t: keep.append(r)
PR = pd.DataFrame(keep); print('tile-covered pairs:', len(PR), 'granules', PR.granule.nunique(), 'fires', PR.fire.nunique(), 'tiles', dict(PR.tile.value_counts()))
def fetch(gid, ver):
    """download the 5 layers of one granule, clip every fire matched to it, return per-fire records"""
    sub = PR[PR.granule == gid]; out = []
    if all(os.path.exists(f'{CACHE}/{f}_{gid}.npz') for f in sub.fire): return [(f, gid, 'cached') for f in sub.fire]
    arrs = {}
    try:
        for lay in LAYERS:
            u = f'https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/ECO_L2T_LSTE.{ver}/{gid}/{gid}_{lay}.tif'
            r = requests.get(u, headers={'Authorization': f'Bearer {TOK}'}, timeout=180)
            if r.status_code == 404 and lay == 'LST_err': continue   # version 3 has no LST_err layer
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix='.tif') as f:
                f.write(r.content); f.flush()
                with rasterio.open(f.name) as ds: arrs[lay] = (ds.read(1), ds.transform, ds.nodata)
    except Exception as e:
        return [(f, gid, f'fail {str(e)[:80]}') for f in sub.fire]
    for fid in sub.fire:
        x0, y0, x1, y1 = S[fid].buffer(2000).bounds; rec = {}
        for lay, (a, tr, nod) in arrs.items():
            w = from_bounds(x0, y0, x1, y1, tr).round_offsets().round_lengths(); r0, c0 = int(w.row_off), int(w.col_off); h, wd = int(w.height), int(w.width)
            clip = np.full((h, wd), np.nan if a.dtype.kind == 'f' else 0, dtype=a.dtype)
            rr0, cc0 = max(r0, 0), max(c0, 0); rr1, cc1 = min(r0 + h, a.shape[0]), min(c0 + wd, a.shape[1])
            if rr1 > rr0 and cc1 > cc0: clip[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0] = a[rr0:rr1, cc0:cc1]
            rec[lay] = clip; rec['transform'] = np.array([tr.a, tr.b, tr.c + c0 * tr.a, tr.d, tr.e, tr.f + r0 * tr.e])
        np.savez_compressed(f'{CACHE}/{fid}_{gid}.npz', **rec); out.append((fid, gid, 'ok'))
    return out
jobs = PR.drop_duplicates('granule')[['granule', 'ver']].values
with ThreadPoolExecutor(4) as ex: res = sum(ex.map(lambda j: fetch(j[0], f'{int(j[1]):03d}'), jobs), [])
st = pd.DataFrame(res, columns=['fire', 'granule', 'status']); print(st.status.str[:6].value_counts().to_dict())
PR.merge(st, on=['fire', 'granule']).to_csv(f'{R}/ecostress_matches.csv', index=False)
