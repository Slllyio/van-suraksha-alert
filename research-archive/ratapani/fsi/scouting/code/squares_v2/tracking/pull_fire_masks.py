"""Pull VIIRS 375 m active-fire masks (VNP14IMG / VJ114IMG / VJ214IMG) and their geolocation (VNP03IMG / VJ103IMG /
VJ203IMG) for every viewing pass of the tracking run fires (Ratapani rebuild fires + photo-test fires), crop each granule
at once to a small window, and delete the granule. READY TO RUN, NOT RUN (no token exists yet).

Where the files are (CMR check, 17 Oct 2026, metadata only): the v002 fire masks are served by LP DAAC cloud
(data.lpdaac.earthdatacloud.nasa.gov, ~2.3-3.1 MB per 6-min granule); the 03IMG geolocation by LAADS cloud
(data.laadsdaac.earthdatacloud.nasa.gov, ~155-185 MB per granule). Both take the same Earthdata Bearer token; both
redirect to a signed S3 URL, which is fetched WITHOUT the header.

Token: read ONLY from the environment variable EARTHDATA_TOKEN (a project environment secret); if it is absent the
script sends no header and relies on the agent proxy injecting the saved secret into *.nasa.gov requests (17 Oct 2026). It is never printed,
logged or written; it is sent only as an "Authorization: Bearer" header to NASA download hosts (allow-list below), never
to CMR search and never across a redirect to another host.

Input : results/fire_mask_pull_plan.csv (one row per fire x viewing pass: pass_key, sensor, t_utc, lon/lat box of the
        fire outline + 1.5 km; written by this thread, see squares_v2_tracking.md)
Output: <out>/crops/<pass_key>.npz  one crop per pass, covering the union of the boxes of all fires that use that pass:
          fire_mask (uint8 classes, below), algorithm_qa (uint32), lat, lon (float32, pixel centres), sensor_zenith,
          sensor_azimuth (float32 deg, from the 03IMG file), row0/col0 (window origin in the granule), granule names,
          and every FP_* array restricted to fire pixels inside the window.
        <out>/index.csv  pass_key, file, sensor, granule start time, window size, n fire pixels, status
Fire mask classes (VIIRS 375 m active-fire user guide): 0 not processed, 1 bow-tie deletion, 2 sun glint, 3 water,
        4 cloud, 5 land (clear, no fire), 6 unclassified land, 7 low / 8 nominal / 9 high confidence fire.
        t2_lib.Fire reads these as: 7-9 flagged; 3, 5 "looked, no fire"; 4, 6, 2 "no information"; 0, 1 "missing".

Usage:
  python3 pull_fire_masks.py --plan            # CMR search only (no token needed): granule count and total size
  EARTHDATA_TOKEN=... python3 pull_fire_masks.py [--out DIR] [--max-gb 2] [--only-big] [--no-geo] [--limit N]
  --no-geo: skip the 03IMG files (~10x the size of the mask files); then only passes that flagged a fire pixel get a
            crop, geolocated from that pass's FP_latitude/FP_longitude and FP_line/FP_sample (affine fit per window).
Resumable: passes already in index.csv with status ok are skipped.
"""
import argparse, os, sys, json, time, re, tempfile, shutil
from urllib.parse import urlparse
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = f'{HERE}/results/fire_mask_pull_plan.csv'
DEF_OUT = os.environ.get('TR_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_track') + '/fire_masks'
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'
FIRE = {'S-NPP': 'VNP14IMG', 'NOAA-20': 'VJ114IMG', 'NOAA-21': 'VJ214IMG'}
GEO = {'S-NPP': 'VNP03IMG', 'NOAA-20': 'VJ103IMG', 'NOAA-21': 'VJ203IMG'}
TOKEN_HOSTS = ('ladsweb.modaps.eosdis.nasa.gov', 'data.laadsdaac.earthdatacloud.nasa.gov', 'data.lpdaac.earthdatacloud.nasa.gov',
               'e4ftl01.cr.usgs.gov', 'nrt3.modaps.eosdis.nasa.gov', 'nrt4.modaps.eosdis.nasa.gov')
PAD_PX = 8          # extra pixels around the fires' boxes


def get_token():
    tok = os.environ.get('EARTHDATA_TOKEN', '').strip()
    if not tok:     # proxy route: the cloud environment's agent proxy adds the Bearer header to *.nasa.gov itself
        print('EARTHDATA_TOKEN not set: sending no Authorization header (relying on the proxy-injected secret).')
    return tok


def cmr_granules(sess, short_name, t0, t1, box):
    """All granules of short_name intersecting box (W,S,E,N) in [t0, t1]; newest version kept per granule start time."""
    p = dict(short_name=short_name, temporal=f'{t0:%Y-%m-%dT%H:%M:%SZ},{t1:%Y-%m-%dT%H:%M:%SZ}',
             bounding_box=','.join(f'{v:.4f}' for v in box), page_size=50)
    for k in range(4):
        try:
            r = sess.get(CMR, params=p, timeout=60); r.raise_for_status(); break
        except Exception as e:
            if k == 3: raise
            time.sleep(5 * (k + 1))
    out = []
    for g in r.json().get('feed', {}).get('entry', []):
        links = [l['href'] for l in g.get('links', []) if l.get('rel', '').endswith('/data#') and l['href'].startswith('https')
                 and l['href'].split('?')[0].endswith(('.nc', '.h5', '.hdf'))]
        if not links: continue
        links.sort(key=lambda u: 'earthdatacloud' not in u)        # NASA cloud archive link first
        ver = re.search(r'\.(\d{3})\.\d{13}', g.get('producer_granule_id', '') or g.get('title', ''))
        out.append(dict(name=g.get('producer_granule_id') or g.get('title'), start=pd.Timestamp(g['time_start']).tz_localize(None),
                        size_mb=float(g.get('granule_size') or 0), url=links[0], version=ver.group(1) if ver else '000'))
    if not out: return []
    o = pd.DataFrame(out).sort_values('version').drop_duplicates('start', keep='last')
    return o.sort_values('start').to_dict('records')


def stream(sess, url, token, dest):
    """Download url to dest; Bearer only to allow-listed NASA hosts; redirects followed by hand so the header never
    leaves those hosts."""
    for _ in range(6):
        host = urlparse(url).hostname or ''
        hdr = {'Authorization': f'Bearer {token}'} if token and host in TOKEN_HOSTS else {}
        r = sess.get(url, headers=hdr, stream=True, allow_redirects=False, timeout=120)
        if r.status_code in (301, 302, 303, 307, 308):
            url = r.headers['Location']; r.close(); continue
        if r.status_code in (401, 403):
            r.close(); sys.exit(f'Download refused ({r.status_code}) by {host}: the token is invalid, expired, or lacks the '
                                'LAADS application approval. Nothing more was downloaded.')
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for ch in r.iter_content(1 << 20): f.write(ch)
        return os.path.getsize(dest)
    raise RuntimeError('too many redirects')


def h5find(h, name):
    """Dataset by name, anywhere in the file, ignoring case / spaces / underscores."""
    key = name.lower().replace(' ', '').replace('_', ''); hit = []
    h.visititems(lambda n, o: hit.append(o) if hasattr(o, 'shape') and n.split('/')[-1].lower().replace(' ', '').replace('_', '') == key else None)
    return hit[0] if hit else None


def scaled(ds, sl):
    a = ds[sl].astype(np.float32); at = ds.attrs
    fv = at.get('_FillValue'); sf = at.get('scale_factor'); of = at.get('add_offset')
    if fv is not None: a[ds[sl] == np.asarray(fv).ravel()[0]] = np.nan
    if sf is not None: a = a * float(np.asarray(sf).ravel()[0])
    if of is not None: a = a + float(np.asarray(of).ravel()[0])
    return a


def window_from_geo(lat, lon, box):
    W, S, E, N = box
    m = (lat >= S) & (lat <= N) & (lon >= W) & (lon <= E)
    if not m.any(): return None
    r, c = np.where(m)
    return max(r.min() - PAD_PX, 0), min(r.max() + PAD_PX + 1, lat.shape[0]), max(c.min() - PAD_PX, 0), min(c.max() + PAD_PX + 1, lat.shape[1])


def crop_pass(sess, token, pk, sensor, t, box, tmp, out, use_geo):
    """One pass: find its granules, download each (mask, then geo), crop, delete. Returns an index row."""
    t0, t1 = t - pd.Timedelta(minutes=9), t + pd.Timedelta(minutes=9)
    fg = cmr_granules(sess, FIRE[sensor], t0, t1, box)
    if not fg: return dict(pass_key=pk, status='no_granule')
    import h5py
    parts = []
    for g in fg:
        fpath = os.path.join(tmp, 'mask.nc'); stream(sess, g['url'], token, fpath)
        with h5py.File(fpath, 'r') as h:
            fm = h5find(h, 'fire mask'); qa = h5find(h, 'algorithm QA')
            fp = {k: h5find(h, k) for k in ['FP_line', 'FP_sample', 'FP_latitude', 'FP_longitude']}
            fpall = {}
            h.visititems(lambda n, o: fpall.__setitem__(n.split('/')[-1], o[()]) if hasattr(o, 'shape') and n.split('/')[-1].startswith('FP_') else None)
            if use_geo:
                gg = [x for x in cmr_granules(sess, GEO[sensor], g['start'] - pd.Timedelta(seconds=30), g['start'] + pd.Timedelta(seconds=30), box)
                      if abs((x['start'] - g['start']).total_seconds()) < 30]
                if not gg: os.remove(fpath); continue
                gpath = os.path.join(tmp, 'geo.nc'); stream(sess, gg[0]['url'], token, gpath)
                with h5py.File(gpath, 'r') as hg:
                    la, lo = h5find(hg, 'latitude'), h5find(hg, 'longitude')
                    win = window_from_geo(la[()], lo[()], box)
                    if win is None: os.remove(gpath); os.remove(fpath); continue
                    sl = np.s_[win[0]:win[1], win[2]:win[3]]
                    geo = dict(lat=scaled(la, sl), lon=scaled(lo, sl), sensor_zenith=scaled(h5find(hg, 'sensor_zenith'), sl),
                               sensor_azimuth=scaled(h5find(hg, 'sensor_azimuth'), sl), geo_granule=gg[0]['name'])
                os.remove(gpath)
            else:   # geolocate from this pass's fire pixels only (affine lat/lon in line/sample)
                if fp['FP_line'] is None or not len(fp['FP_line']): os.remove(fpath); continue
                L, Sm, La, Lo = (fp[k][()] for k in ['FP_line', 'FP_sample', 'FP_latitude', 'FP_longitude'])
                W, S_, E, N = box; k = (La >= S_) & (La <= N) & (Lo >= W) & (Lo <= E)
                if not k.any(): os.remove(fpath); continue
                rr, cc = L[k].astype(int), Sm[k].astype(int); pad = PAD_PX + 30
                win = (max(rr.min() - pad, 0), min(rr.max() + pad + 1, fm.shape[0]), max(cc.min() - pad, 0), min(cc.max() + pad + 1, fm.shape[1]))
                sl = np.s_[win[0]:win[1], win[2]:win[3]]
                A = np.c_[np.ones(k.sum()), rr, cc]
                if k.sum() >= 3 and np.linalg.matrix_rank(A) == 3:
                    RR, CC = np.mgrid[win[0]:win[1], win[2]:win[3]]; Z = np.c_[np.ones(RR.size), RR.ravel(), CC.ravel()]
                    geo = dict(lat=(Z @ np.linalg.lstsq(A, La[k], rcond=None)[0]).reshape(RR.shape).astype(np.float32),
                               lon=(Z @ np.linalg.lstsq(A, Lo[k], rcond=None)[0]).reshape(RR.shape).astype(np.float32), geo_from='FP_affine')
                else: geo = dict(geo_from='FP_points_only')
            m = fpall.get('FP_line')
            inw = (m >= win[0]) & (m < win[1]) & (fpall['FP_sample'] >= win[2]) & (fpall['FP_sample'] < win[3]) if m is not None and len(m) else np.zeros(0, bool)
            fpw = {k: np.asarray(v)[inw] for k, v in fpall.items() if np.ndim(v) == 1 and len(v) == len(inw)}
            parts.append(dict(fire_mask=fm[sl].astype(np.uint8), algorithm_qa=qa[sl].astype(np.uint32) if qa is not None else np.zeros(0),
                              row0=win[0], col0=win[2], granule=g['name'], granule_start=str(g['start']), **geo, **fpw))
        os.remove(fpath)
    if not parts: return dict(pass_key=pk, status='outside_window')
    fn = f"{out}/crops/{pk.replace('|', '_').replace(' ', '')}.npz"
    flat = {}
    for i, p in enumerate(parts):          # a pass split across two granules keeps both parts, suffix _0 / _1
        for k, v in p.items(): flat[f'{k}_{i}'] = np.asarray(v)
    np.savez_compressed(fn, n_parts=len(parts), sensor=sensor, pass_key=pk, **flat)
    return dict(pass_key=pk, file=os.path.basename(fn), sensor=sensor, granule_start=parts[0]['granule_start'], n_parts=len(parts),
                shape=str(parts[0]['fire_mask'].shape), n_fire_px=int(sum((p['fire_mask'] >= 7).sum() for p in parts)),
                bytes=os.path.getsize(fn), status='ok')


def plan_boxes(only_big=False):
    X = pd.read_csv(PLAN, parse_dates=['t_utc'])
    if only_big: X = X[X.big]
    g = X.groupby('pass_key').agg(sensor=('sensor', 'first'), t=('t_utc', 'median'), W=('lon0', 'min'), S=('lat0', 'min'),
                                  E=('lon1', 'max'), N=('lat1', 'max'), fires=('fire', 'nunique'), flagged=('flagged', 'any')).reset_index()
    return g.sort_values('t').reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEF_OUT); ap.add_argument('--max-gb', type=float, default=2.0)
    ap.add_argument('--only-big', action='store_true'); ap.add_argument('--no-geo', action='store_true')
    ap.add_argument('--limit', type=int, default=0); ap.add_argument('--plan', action='store_true')
    a = ap.parse_args()
    import requests
    sess = requests.Session(); G = plan_boxes(a.only_big)
    if a.limit: G = G.head(a.limit)
    if a.plan:     # CMR metadata only: no token, nothing downloaded
        rows = []
        for r in G.itertuples():
            box = (r.W, r.S, r.E, r.N); t0, t1 = r.t - pd.Timedelta(minutes=9), r.t + pd.Timedelta(minutes=9)
            f = cmr_granules(sess, FIRE[r.sensor], t0, t1, box); g = cmr_granules(sess, GEO[r.sensor], t0, t1, box)
            rows.append(dict(pass_key=r.pass_key, n_mask=len(f), mb_mask=sum(x['size_mb'] for x in f), n_geo=len(g), mb_geo=sum(x['size_mb'] for x in g)))
        R = pd.DataFrame(rows); print(json.dumps(dict(passes=len(R), mask_granules=int(R.n_mask.sum()), mask_gb=round(R.mb_mask.sum() / 1024, 1),
              geo_granules=int(R.n_geo.sum()), geo_gb=round(R.mb_geo.sum() / 1024, 1), passes_without_granule=int((R.n_mask == 0).sum())), indent=1))
        return
    token = get_token()
    os.makedirs(f'{a.out}/crops', exist_ok=True); idx_fn = f'{a.out}/index.csv'
    done = pd.read_csv(idx_fn) if os.path.exists(idx_fn) else pd.DataFrame(columns=['pass_key', 'status'])
    skip = set(done[done.status == 'ok'].pass_key)
    if a.no_geo: G = G[G.flagged]
    tmp = tempfile.mkdtemp(prefix='granule_', dir=a.out)
    try:
        for i, r in enumerate(G.itertuples()):
            if r.pass_key in skip: continue
            used = sum(os.path.getsize(os.path.join(a.out, 'crops', f)) for f in os.listdir(f'{a.out}/crops'))
            if used > a.max_gb * 1024 ** 3: print(f'stopping: crops reached {used / 1024 ** 3:.2f} GB (cap {a.max_gb} GB)'); break
            try: row = crop_pass(sess, token, r.pass_key, r.sensor, r.t, (r.W, r.S, r.E, r.N), tmp, a.out, not a.no_geo)
            except SystemExit: raise
            except Exception as e: row = dict(pass_key=r.pass_key, status=f'error: {type(e).__name__}')   # message not printed (may echo a URL)
            done = pd.concat([done, pd.DataFrame([row])], ignore_index=True); done.to_csv(idx_fn, index=False)
            if i % 25 == 0: print(i, len(G), row.get('status'), flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)        # no granule is ever left on disk
    print('done;', (done.status == 'ok').sum(), 'crops in', a.out)


if __name__ == '__main__':
    main()
