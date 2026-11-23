"""Section 14c on all of Madhya Pradesh with 30 m Sentinel-2 / Landsat hot pixels (Akkshay 17 Oct 18:50Z "go").
Same hot-pixel rule as fire-alert-scars/scripts/af_scan.py (Planetary Computer, no login), but read as a 4 km window
around each VIIRS day-pass cluster instead of whole Ratapani scenes. A pass = one satellite's alerts of one forest event
within the same 15 min; scene within 3.5 h before the pass (S2/Landsat ~05:00-05:30 UTC, VIIRS day ~07:30-09:00 UTC).
Stages: 1 scene matching (results/mp_hotpix_pairs.csv), 2 fetch hot pixels (scratch mp_hotpix/), 3 block-position measures
(results/mp_hotpix_passes.csv, results/mp_hotpix_between_blocks.json, figures/9_mp_between_blocks.png).
Env: NMAX caps fetched pairs (default 6000, 3+ block and 2-block passes first), THREADS (default 8)."""
import os, sys, json, warnings, numpy as np, pandas as pd, rasterio, pystac_client, planetary_computer as pc
from rasterio.windows import from_bounds
from pyproj import Transformer
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings('ignore')
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF', GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='2')
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'; M = '/mnt/project-files/fire-alert-scars/mp/out'
SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/mp_hotpix'; os.makedirs(SC, exist_ok=True)
NMAX = int(os.environ.get('NMAX', 6000)); THREADS = int(os.environ.get('THREADS', 8))
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True)
# ---- VIIRS day passes on forest events
A = pd.read_csv(f'{M}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'scan', 'track', 'event_id'])
A = A[A.instrument == 'VIIRS']; ev = pd.read_csv(f'{M}/mp_events.csv', usecols=['event_id', 'forest']); A = A[A.event_id.isin(ev[ev.forest].event_id)].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A = A[(A.t.dt.hour >= 6) & (A.t.dt.hour < 11)]; A['x'], A['y'] = to43.transform(A.longitude.values, A.latitude.values)
A['pix_w_m'] = A.scan * 1000; A['pix_h_m'] = A.track * 1000; A['pass_id'] = A.event_id + '|' + A.satellite + '|' + A.t.dt.floor('15min').astype(str)
P = A.groupby('pass_id').agg(event_id=('event_id', 'first'), satellite=('satellite', 'first'), t=('t', 'min'), n_blocks=('x', 'size'), lon=('longitude', 'mean'), lat=('latitude', 'mean'), x=('x', 'mean'), y=('y', 'mean')).reset_index()
P['date'] = P.t.dt.strftime('%Y-%m-%d'); print('day passes', len(P), 'events', P.event_id.nunique(), flush=True)
# ---- stage 1: scenes over MP per month, matched by footprint + date + gap
ppath = f'{R}/mp_hotpix_pairs.csv'
if not os.path.exists(ppath):
    cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1'); rows = []
    for yr in range(2017, 2026):
        for m0, m1 in [('02-15', '03-31'), ('04-01', '05-15'), ('05-16', '06-15')]:
            for col, s in (('sentinel-2-l2a', 's2'), ('landsat-c2-l2', 'ls')):
                q = {'eo:cloud_cover': {'lt': 80}}
                if s == 'ls': q['platform'] = {'in': ['landsat-8', 'landsat-9']}
                for it in cat.search(collections=[col], bbox=[74.0, 21.0, 82.9, 26.9], datetime=f'{yr}-{m0}/{yr}-{m1}T23:59:59Z', query=q).items():
                    rows.append(dict(scene=it.id, sensor=s, t_scene=it.datetime.replace(tzinfo=None), date=it.datetime.strftime('%Y-%m-%d'), geom=shape(it.geometry), cloud=it.properties.get('eo:cloud_cover')))
            print(yr, m0, len(rows), flush=True)
    S = pd.DataFrame(rows); print('scenes', len(S), flush=True)
    pairs = []
    for d, g in S.groupby('date'):
        pp = P[P.date == d]
        if pp.empty: continue
        tree = STRtree(list(g.geom)); gi = g.reset_index(drop=True)
        for _, r in pp.iterrows():
            for j in tree.query(Point(r.lon, r.lat), predicate='within'):
                gap = (r.t - gi.t_scene.iloc[j]).total_seconds() / 3600
                if 0 <= gap <= 3.5: pairs.append(dict(pass_id=r.pass_id, event_id=r.event_id, satellite=r.satellite, t=r.t, n_blocks=r.n_blocks, x=r.x, y=r.y, scene=gi.scene.iloc[j], sensor=gi.sensor.iloc[j], t_scene=gi.t_scene.iloc[j], gap_h=round(gap, 2), cloud=gi.cloud.iloc[j]))
    PR = pd.DataFrame(pairs); PR.to_csv(ppath, index=False); print('pairs', len(PR), PR.groupby(PR.n_blocks.clip(upper=3)).size().to_dict(), flush=True)
PR = pd.read_csv(ppath, parse_dates=['t', 't_scene'])
# ---- stage 2: sample and fetch
PR['kind'] = np.where(PR.n_blocks == 1, 'single block', np.where(PR.n_blocks == 2, '2 blocks', '3+ blocks'))
quota = {'3+ blocks': int(NMAX * 0.4), '2 blocks': int(NMAX * 0.4), 'single block': NMAX - 2 * int(NMAX * 0.4)}   # balanced by block count
sel = pd.concat([PR[PR.kind == k].sample(frac=1, random_state=0).head(n) for k, n in quota.items()]).drop_duplicates('pass_id')
print('fetching', len(sel), sel.kind.value_counts().to_dict(), flush=True)
BANDS = {'s2': dict(red='B04', nir='B8A', swir2='B12'), 'ls': dict(red='red', nir='nir08', swir2='swir22')}
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1'); _items = {}
def item(scene, sensor):
    if scene not in _items:
        col = 'sentinel-2-l2a' if sensor == 's2' else 'landsat-c2-l2'
        _items[scene] = pc.sign(next(cat.search(collections=[col], ids=[scene]).items()))
    return _items[scene]
def fetch(r):
    f = f'{SC}/{r.pass_id.replace("|", "_").replace(":", "")}_{r.scene[:40]}.npz'
    if os.path.exists(f): return 'cached'
    try:
        it = item(r.scene, r.sensor); b = {}; ref = None
        for k, a in BANDS[r.sensor].items():
            with rasterio.open(it.assets[a].href) as src:
                if ref is None:
                    tx, ty = Transformer.from_crs('EPSG:32643', src.crs, always_xy=True).transform(r.x, r.y)
                    bounds = (tx - 2000, ty - 2000, tx + 2000, ty + 2000); crs = src.crs
                    w = from_bounds(*bounds, src.transform if src.res[0] >= 20 else src.transform).round_offsets().round_lengths()
                    res = max(src.res[0], 20.0); n = int(4000 / res); ref = (bounds, n)
                w = from_bounds(*ref[0], src.transform)
                x = src.read(1, window=w, out_shape=(ref[1], ref[1]), boundless=True, fill_value=0).astype(np.float32)
            if r.sensor == 's2':
                off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
                b[k] = np.where(x > 0, (x - off) / 10000.0, np.nan)
            else: b[k] = np.where(x > 0, x * 0.0000275 - 0.2, np.nan)
        with np.errstate(all='ignore'):
            ndfi = (b['swir2'] - b['nir']) / (b['swir2'] + b['nir']); dnr = b['nir'] - b['red']
            fire = (ndfi > 0.5) & (dnr > -0.05) & (dnr < 0.15) & (b['swir2'] > 0.10)
            if r.sensor == 'ls': fire |= (b['swir2'] / b['nir'] > 2.5) & (b['swir2'] - b['nir'] > 0.3) & (b['swir2'] > 0.5)
        n = ref[1]; res = 4000 / n; rr, cc = np.where(fire)
        px = ref[0][0] + (cc + 0.5) * res; py = ref[0][3] - (rr + 0.5) * res
        X, Y = Transformer.from_crs(crs, 'EPSG:32643', always_xy=True).transform(px, py) if len(rr) else ([], [])
        valid = int(np.isfinite(b['swir2']).sum())
        np.savez_compressed(f, x=np.asarray(X, np.float32), y=np.asarray(Y, np.float32), valid=valid, n=n)
        return 'ok'
    except Exception as e:
        return f'fail {str(e)[:60]}'
st = []
with ThreadPoolExecutor(THREADS) as ex:
    for i, s in enumerate(ex.map(fetch, [r for _, r in sel.iterrows()])):
        st.append(s)
        if i % 200 == 0: print(i, len(sel), pd.Series(st).str[:6].value_counts().to_dict(), flush=True)
sel = sel.assign(status=st); print(sel.status.str[:6].value_counts(), flush=True)
# ---- stage 3: where the hot pixels sit
def place(hx, hy, blocks):
    bx, by, bw, bh = blocks.x.values, blocks.y.values, blocks.pix_w_m.values, blocks.pix_h_m.values; cx, cy = bx.mean(), by.mean()
    d = np.hypot(hx[:, None] - bx[None], hy[:, None] - by[None]); nearest = d.min(1); i = d.argmin(1)
    u = np.maximum(np.abs(hx - bx[i]) / (bw[i] / 2), np.abs(hy - by[i]) / (bh[i] / 2)); dc = np.hypot(hx - cx, hy - cy)
    return dict(n_hot=len(hx), d_nearest_centre_med=float(np.median(nearest)), u_med=float(np.median(u)), share_u_gt_0_5=float((u > 0.5).mean()), share_in_block=float((u <= 1).mean()),
                share_closer_to_cluster_centre=float((dc < nearest).mean()), hot_offset_from_cluster_centre=float(np.hypot(hx.mean() - cx, hy.mean() - cy)),
                block_sep=float(np.hypot(bx[:, None] - bx[None], by[:, None] - by[None]).max()) if len(bx) > 1 else 0.0)
rows = []
for _, r in sel[sel.status.isin(['ok', 'cached'])].iterrows():
    f = f'{SC}/{r.pass_id.replace("|", "_").replace(":", "")}_{r.scene[:40]}.npz'; z = np.load(f)
    blocks = A[A.pass_id == r.pass_id]; hx, hy = z['x'], z['y']
    rec = dict(pass_id=r.pass_id, event_id=r.event_id, satellite=r.satellite, sensor=r.sensor, gap_h=r.gap_h, n_blocks=r.n_blocks, kind=r.kind, valid_share=float(z['valid']) / float(z['n']) ** 2, n_hot_window=len(hx))
    if len(hx):
        near = np.hypot(hx[:, None] - blocks.x.values[None], hy[:, None] - blocks.y.values[None]).min(1) <= 600; hx, hy = hx[near], hy[near]
    rec['visible'] = bool(len(hx) >= 3)
    if rec['visible']: rec.update(place(hx, hy, blocks))
    rows.append(rec)
D = pd.DataFrame(rows); D.to_csv(f'{R}/mp_hotpix_passes.csv', index=False); V = D[D.visible]
out = dict(pairs_matched=int(len(PR)), fetched=int(len(D)), usable_clear=int((D.valid_share > 0.8).sum()), visible=int(len(V)), visible_share=round(float(D.visible.mean()), 3), by_kind={}, by_satellite={})
for k, g in V.groupby('kind'):
    out['by_kind'][k] = dict(passes=int(len(g)), hot_pixels_median=float(g.n_hot.median()), hot_to_nearest_block_centre_m=round(float(g.d_nearest_centre_med.median())), position_in_block_0centre_1edge=round(float(g.u_med.median()), 2),
                             share_in_outer_half=round(float(g.share_u_gt_0_5.mean()), 2), share_inside_block=round(float(g.share_in_block.mean()), 2), share_closer_to_cluster_centre=round(float(g.share_closer_to_cluster_centre.mean()), 2),
                             hot_centre_offset_from_cluster_centre_m=round(float(g.hot_offset_from_cluster_centre.median())), block_separation_m=round(float(g.block_sep.median())))
for k, g in V.groupby('satellite'): out['by_satellite'][k] = dict(passes=int(len(g)), hot_to_nearest_block_centre_m=round(float(g.d_nearest_centre_med.median())), position_in_block=round(float(g.u_med.median()), 2), share_in_outer_half=round(float(g.share_u_gt_0_5.mean()), 2))
two = V[V.n_blocks == 2]
out['two_blocks'] = {'adjacent_<500m': dict(passes=int((two.block_sep < 500).sum()), share_between_centres=round(float(two[two.block_sep < 500].share_closer_to_cluster_centre.mean()), 2)),
                     'far_>=500m': dict(passes=int((two.block_sep >= 500).sum()), share_between_centres=round(float(two[two.block_sep >= 500].share_closer_to_cluster_centre.mean()), 2))}
# bootstrap CI on the headline share
rng = np.random.default_rng(0); b = [V.share_u_gt_0_5.sample(len(V), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(500)]
out['share_in_outer_half_all'] = dict(value=round(float(V.share_u_gt_0_5.mean()), 3), ci95=[round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)])
out['random_inside_block_reference'] = dict(position=0.71, share_in_outer_half=0.75)
json.dump(out, open(f'{R}/mp_hotpix_between_blocks.json', 'w'), indent=1); print(json.dumps(out, indent=1))
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
for k in ['single block', '2 blocks', '3+ blocks']:
    g = V[V.kind == k]
    if len(g): ax[0].hist(g.u_med, bins=np.linspace(0, 2.5, 26), histtype='step', label=f'{k} (n={len(g)})')
ax[0].axvline(0.71, ls='--', c='k', label='random inside block'); ax[0].set_xlabel('hot-pixel position in nearest VIIRS block (0 centre, 1 edge, >1 outside)'); ax[0].legend(fontsize=8)
ax[1].scatter(two.block_sep, two.share_closer_to_cluster_centre, s=6, alpha=.5); ax[1].axvline(500, ls='--', c='k'); ax[1].set_xlabel('two-block passes: distance between block centres (m)'); ax[1].set_ylabel('share of hot pixels between the centres')
fig.suptitle('All-MP fires, 30 m Sentinel-2/Landsat hot pixels within 3.5 h of a VIIRS day pass'); fig.tight_layout(); fig.savefig(f'{FG}/9_mp_between_blocks.png', dpi=130)
