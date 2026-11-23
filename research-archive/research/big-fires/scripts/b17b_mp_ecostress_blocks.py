"""Section 14b/14c redone on all-MP fires: fetch ECOSTRESS 70 m LST for every (event, pass) pair in results/mp_ecostress_pairs.csv
(from b17_mp_ecostress_count.py), find hot pixels around the VIIRS blocks of the alerts within +-1 h, and measure where they sit
in / between the blocks. No scar outline is needed: the background is the median clear LST in a 1.5-3 km ring around the VIIRS
cluster, a pixel is hot at >10 K above it, and a pass "shows the fire" when >=3 hot pixels lie within 600 m of a block centre and
the hot share there is >=3x the share in the ring.
Login: EARTHDATA_TOKEN (environment only). Clips go to the scratchpad; results to results/mp_ecostress_passes.csv, results/mp_between_blocks.json.
Run: NMAX=200 python3 b17b_...py for a test batch."""
import os, sys, json, tempfile, numpy as np, pandas as pd, rasterio, requests
from rasterio.windows import from_bounds
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
R = '/mnt/project-files/research/big-fires/results'; M = '/mnt/project-files/fire-alert-scars/mp/out'
SC = os.environ.get('MP_ECO_SCRATCH', '/tmp/claude-0/mp_eco'); CL = f'{SC}/clips'; os.makedirs(CL, exist_ok=True)
TOK = os.environ.get('EARTHDATA_TOKEN')   # 17 Oct: the secret is an agent-proxy header on *.nasa.gov; without the variable no header is sent
HDR = {'Authorization': f'Bearer {TOK}'} if TOK else {}
PR = pd.read_csv(f'{R}/mp_ecostress_pairs.csv', parse_dates=['t0'])
if os.environ.get('NMAX'): PR = PR.sample(int(os.environ['NMAX']), random_state=0)
import re
ver = {g: int(re.match(r'ECOv(\d{3})', g).group(1)) for g in PR.granule.unique()}   # collection version is in the granule id
A = pd.read_csv(f'{M}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'scan', 'track', 'event_id'])
A = A[A.instrument == 'VIIRS']; A = A[A.event_id.isin(PR.event_id)]
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True); A['x'], A['y'] = to43.transform(A.longitude.values, A.latitude.values)
A['pix_w_m'] = A.scan * 1000; A['pix_h_m'] = A.track * 1000
LAYERS = ['LST', 'QC', 'cloud']
def one(gid):
    """download one granule's 3 layers, clip +-3 km around each matched event's VIIRS cluster, save in EPSG:32643 point form"""
    sub = PR[PR.granule == gid]; out = []
    todo = [e for e in sub.event_id if not os.path.exists(f'{CL}/{e}_{gid}.npz')]
    if not todo: return [(e, gid, 'cached') for e in sub.event_id]
    arrs = {}
    try:
        for lay in LAYERS:
            u = f'https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/ECO_L2T_LSTE.{int(ver[gid]):03d}/{gid}/{gid}_{lay}.tif'
            r = requests.get(u, headers=HDR, timeout=180); r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix='.tif') as f:
                f.write(r.content); f.flush()
                with rasterio.open(f.name) as ds: arrs[lay] = (ds.read(1), ds.transform, ds.crs)
    except Exception as ex:
        return [(e, gid, f'fail {str(ex)[:80]}') for e in sub.event_id]
    lst, tr, crs = arrs['LST']; to_tile = Transformer.from_crs('EPSG:32643', crs, always_xy=True); back = Transformer.from_crs(crs, 'EPSG:32643', always_xy=True)
    for eid in todo:
        a = A[A.event_id == eid]; cx, cy = a.x.mean(), a.y.mean(); tx, ty = to_tile.transform(cx, cy)
        w = from_bounds(tx - 3000, ty - 3000, tx + 3000, ty + 3000, tr).round_offsets().round_lengths()
        r0, c0, h, wd = int(w.row_off), int(w.col_off), int(w.height), int(w.width)
        rr0, cc0, rr1, cc1 = max(r0, 0), max(c0, 0), min(r0 + h, lst.shape[0]), min(c0 + wd, lst.shape[1])
        if rr1 - rr0 < 20 or cc1 - cc0 < 20: out.append((eid, gid, 'off_tile')); continue
        rr, cc = np.mgrid[rr0:rr1, cc0:cc1]; px = tr.c + (cc + 0.5) * tr.a; py = tr.f + (rr + 0.5) * tr.e
        X, Y = back.transform(px.ravel(), py.ravel())
        np.savez_compressed(f'{CL}/{eid}_{gid}.npz', x=X.astype(np.float32), y=Y.astype(np.float32), lst=lst[rr0:rr1, cc0:cc1].ravel(),
                            cloud=arrs['cloud'][0][rr0:rr1, cc0:cc1].ravel(), qc=arrs['QC'][0][rr0:rr1, cc0:cc1].ravel())
        out.append((eid, gid, 'ok'))
    return out
jobs = PR.granule.unique(); print('granules to fetch', len(jobs), 'pairs', len(PR), flush=True)
st = []
with ThreadPoolExecutor(int(os.environ.get('WORKERS', 4))) as ex:
    for i, res in enumerate(ex.map(one, jobs)):
        st += res
        if i % 50 == 0: print(i, len(jobs), flush=True)
ST = pd.DataFrame(st, columns=['event_id', 'granule', 'status']); print(ST.status.str[:6].value_counts())
# ---- analysis
def place(hx, hy, blocks):
    bx, by, bw, bh = blocks.x.values, blocks.y.values, blocks.pix_w_m.values, blocks.pix_h_m.values; cx, cy = bx.mean(), by.mean()
    d = np.hypot(hx[:, None] - bx[None], hy[:, None] - by[None]); nearest = d.min(1); i = d.argmin(1)
    u = np.maximum(np.abs(hx - bx[i]) / (bw[i] / 2), np.abs(hy - by[i]) / (bh[i] / 2)); dc = np.hypot(hx - cx, hy - cy)
    return dict(n_hot=len(hx), d_nearest_centre_med=float(np.median(nearest)), u_med=float(np.median(u)), share_u_gt_0_5=float((u > 0.5).mean()),
                share_in_block=float((u <= 1).mean()), share_closer_to_cluster_centre=float((dc < nearest).mean()),
                hot_offset_from_cluster_centre=float(np.hypot(hx.mean() - cx, hy.mean() - cy)),
                block_sep=float(np.hypot(bx[:, None] - bx[None], by[:, None] - by[None]).max()) if len(bx) > 1 else 0.0)
rows = []
for _, r in ST[ST.status == 'ok'].iterrows():
    z = np.load(f'{CL}/{r.event_id}_{r.granule}.npz'); lst = z['lst'].astype(float); clear = np.isfinite(lst) & (lst > 250) & (z['cloud'] == 0)
    t0 = PR[(PR.event_id == r.event_id) & (PR.granule == r.granule)].t0.iloc[0]
    v = A[(A.event_id == r.event_id) & ((A.t - t0).abs() <= pd.Timedelta(hours=1))]
    if v.empty: continue
    dmin = np.hypot(z['x'][:, None] - v.x.values[None], z['y'][:, None] - v.y.values[None]).min(1)
    near = dmin <= 600; ring = (dmin >= 1500) & (dmin <= 3000)
    if (clear & ring).sum() < 200 or (clear & near).sum() < 20: rows.append(dict(event_id=r.event_id, granule=r.granule, t0=t0, usable=False)); continue
    bg = np.median(lst[clear & ring]); hot = (lst - bg > 10) & clear
    sh_near, sh_ring = hot[near].mean(), hot[ring].mean(); vis = (hot & near).sum() >= 3 and sh_near >= 3 * max(sh_ring, 1e-4)
    rec = dict(event_id=r.event_id, granule=r.granule, t0=t0, usable=True, day=t0.hour >= 1 and t0.hour <= 13, bg=bg, n_hot_near=int((hot & near).sum()), visible=bool(vis))
    if vis:
        for sat, g in v.groupby('satellite'):
            rec2 = dict(rec, sensor=sat, n_blocks=len(g), **place(z['x'][hot & near], z['y'][hot & near], g)); rows.append(rec2)
    else: rows.append(rec)
D = pd.DataFrame(rows); D.to_csv(f'{R}/mp_ecostress_passes.csv', index=False)
U = D.drop_duplicates(['event_id', 't0']); V = D[D.visible == True].copy(); V['kind'] = np.where(V.n_blocks == 1, 'single block', np.where(V.n_blocks == 2, '2 blocks', '3+ blocks'))
out = dict(pairs=int(len(PR)), fetched_ok=int((ST.status == 'ok').sum()), usable=int(U.usable.sum()), visible=int(U.visible.sum()),
           visible_share=round(float(U[U.usable].visible.mean()), 3), day_visible_share=round(float(U[U.usable & (U.day == True)].visible.mean()), 3), by_kind={})
for k, g in V.groupby('kind'):
    out['by_kind'][k] = dict(passes=int(len(g)), hot_to_nearest_block_centre_m=round(float(g.d_nearest_centre_med.median())), position_in_block_0centre_1edge=round(float(g.u_med.median()), 2),
                             share_in_outer_half=round(float(g.share_u_gt_0_5.mean()), 2), share_inside_block=round(float(g.share_in_block.mean()), 2),
                             share_closer_to_cluster_centre=round(float(g.share_closer_to_cluster_centre.mean()), 2), hot_centre_offset_from_cluster_centre_m=round(float(g.hot_offset_from_cluster_centre.median())))
two = V[V.n_blocks == 2]
if len(two): out['two_blocks'] = {'adjacent_<500m': dict(passes=int((two.block_sep < 500).sum()), share_closer_to_cluster_centre=round(float(two[two.block_sep < 500].share_closer_to_cluster_centre.mean()), 2)),
                                  'far_>=500m': dict(passes=int((two.block_sep >= 500).sum()), share_closer_to_cluster_centre=round(float(two[two.block_sep >= 500].share_closer_to_cluster_centre.mean()), 2))}
out['random_inside_block_reference'] = dict(position=0.71, share_in_outer_half=0.75)
json.dump(out, open(f'{R}/mp_between_blocks.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
