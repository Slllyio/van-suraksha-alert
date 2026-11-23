"""Parallel version of pull_fire_masks.py (same crops, same index.csv format), written 17 Oct 2026 when the Earthdata
secret arrived as an agent-proxy header (no EARTHDATA_TOKEN variable; the proxy signs every *.nasa.gov request).

Differences from pull_fire_masks.py:
- N worker processes in parallel (--workers, default 12; threads serialise on fsspec's single IO loop).
- The 03IMG geolocation file (~185 MB) is NOT downloaded. It is read in place over HTTP ranges (fsspec + h5py) from its
  signed link. The box's granule row is first estimated from the granule's own fire pixels (FP_line against FP_lat/lon,
  30 nearest), then lat/lon are read for +-64 rows around it (grown 128 rows at a time if the window touches the band
  edge); without fire pixels nearby, a coarse scan (one row per 256) finds the band. Zenith/azimuth for the window only.
- The fire-mask file (~2.5 MB) is downloaded first, whole, to a per-worker temp folder and deleted at once.
- Several plans can be given (--plan-csv, repeatable). Crops go to <out>/crops/<pass_key>.npz as before.
No Authorization header is sent by this script unless EARTHDATA_TOKEN is set (then only to the NASA hosts in TOKEN_HOSTS).
"""
import argparse, os, sys, time, tempfile, shutil, threading
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pull_fire_masks as P

HERE = os.path.dirname(os.path.abspath(__file__))
TOK = os.environ.get('EARTHDATA_TOKEN', '').strip()
_tl = threading.local()


def sess():
    if not hasattr(_tl, 's'): _tl.s = requests.Session()
    return _tl.s


def signed(url):
    """Follow redirects by hand to the final (signed) link; header only to NASA hosts and only if a token var exists."""
    s = sess()
    for _ in range(8):
        host = requests.utils.urlparse(url).hostname or ''
        hdr = {'Authorization': f'Bearer {TOK}'} if TOK and host in P.TOKEN_HOSTS else {}
        r = s.get(url, headers=hdr, allow_redirects=False, stream=True, timeout=60)
        if r.status_code in (301, 302, 303, 307, 308): url = requests.compat.urljoin(url, r.headers['Location']); r.close(); continue
        code = r.status_code; r.close()
        if code in (401, 403): raise PermissionError(f'refused {code} by {host}')
        if code >= 400: raise RuntimeError(f'http {code}')
        return url
    raise RuntimeError('too many redirects')


def download(url, dest):
    u = signed(url)
    with sess().get(u, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for ch in r.iter_content(1 << 20): f.write(ch)


def row_hint(fpall, box):
    """Granule row of the box centre from this granule's own fire pixels (affine line ~ lat/lon on the nearest ones)."""
    L, La, Lo = fpall.get('FP_line'), fpall.get('FP_latitude'), fpall.get('FP_longitude')
    if L is None or len(L) < 3: return None
    W, S, E, N = box; cy, cx = (S + N) / 2, (W + E) / 2
    d = np.hypot(La - cy, (Lo - cx) * np.cos(np.radians(cy)))
    k = np.argsort(d)[:30]
    if d[k[0]] > 4.0: return None
    A = np.c_[np.ones(len(k)), La[k], Lo[k]]
    if np.linalg.matrix_rank(A) < 3: return int(L[k[0]])
    c = np.linalg.lstsq(A, L[k].astype(float), rcond=None)[0]
    return int(round(c[0] + c[1] * cy + c[2] * cx))


def geo_window(url, box, hint=None):
    import fsspec, h5py
    fs = fsspec.filesystem('https', block_size=1 << 21, skip_instance_cache=True, client_kwargs={'trust_env': True})
    with fs.open(signed(url), 'rb', cache_type='blockcache') as f, h5py.File(f, 'r') as h:
        la, lo = P.h5find(h, 'latitude'), P.h5find(h, 'longitude')
        nr = la.shape[0]; W, S, E, N = box; cy, cx = (S + N) / 2, (W + E) / 2
        if hint is None:      # coarse scan: one row per 256
            rows = list(range(16, nr, 256))
            cl = np.stack([la[r, :] for r in rows]); co = np.stack([lo[r, :] for r in rows])
            d = (cl - cy) ** 2 + ((co - cx) * np.cos(np.radians(cy))) ** 2
            d[~np.isfinite(d) | (cl < -90)] = np.inf
            if not np.isfinite(d).any() or np.sqrt(d.min()) > 3.0: return None
            hint = rows[int(np.unravel_index(np.argmin(d), d.shape)[0])]; half = 320
        else: half = 64
        r0, r1 = max((hint - half) // 32 * 32, 0), min(((hint + half) // 32 + 1) * 32, nr)
        LA, LO = la[r0:r1, :], lo[r0:r1, :]
        for _ in range(8):          # grow the band until the window sits inside it
            win = P.window_from_geo(LA, LO, box)
            if win is None:
                dd = (LA - cy) ** 2 + ((LO - cx) * np.cos(np.radians(cy))) ** 2; dd[~np.isfinite(dd) | (LA < -90)] = np.inf
                if not np.isfinite(dd).any(): return None
                ib = np.unravel_index(np.argmin(dd), dd.shape)[0]
                if np.sqrt(dd.min()) > 3.0 and 0 < ib < LA.shape[0] - 1: return None
                lo_edge, hi_edge = ib == 0, ib == LA.shape[0] - 1
            else:
                lo_edge, hi_edge = win[0] == 0 and r0 > 0, win[1] == LA.shape[0] and r1 < nr
                if not (lo_edge or hi_edge): break
            if lo_edge and r0 > 0:
                n0 = max(r0 - 128, 0); LA = np.vstack([la[n0:r0, :], LA]); LO = np.vstack([lo[n0:r0, :], LO]); r0 = n0
            elif hi_edge and r1 < nr:
                n1 = min(r1 + 128, nr); LA = np.vstack([LA, la[r1:n1, :]]); LO = np.vstack([LO, lo[r1:n1, :]]); r1 = n1
            else: break
        if win is None: return None
        win = (win[0] + r0, win[1] + r0, win[2], win[3]); sl = np.s_[win[0]:win[1], win[2]:win[3]]
        geo = dict(lat=P.scaled(la, sl), lon=P.scaled(lo, sl), sensor_zenith=P.scaled(P.h5find(h, 'sensor_zenith'), sl),
                   sensor_azimuth=P.scaled(P.h5find(h, 'sensor_azimuth'), sl))
    return win, sl, geo


def crop_pass(pk, sensor, t, box, out):
    import h5py
    s = sess(); fg = P.cmr_granules(s, P.FIRE[sensor], t - pd.Timedelta(minutes=9), t + pd.Timedelta(minutes=9), box)
    if not fg: return dict(pass_key=pk, status='no_granule')
    tmp = tempfile.mkdtemp(prefix='g_', dir=out); parts = []
    try:
        for g in fg:
            gg = [x for x in P.cmr_granules(s, P.GEO[sensor], g['start'] - pd.Timedelta(seconds=30), g['start'] + pd.Timedelta(seconds=30), box)
                  if abs((x['start'] - g['start']).total_seconds()) < 30]
            if not gg: continue
            fpath = os.path.join(tmp, 'mask.nc'); download(g['url'], fpath)
            with h5py.File(fpath, 'r') as h:
                fm = P.h5find(h, 'fire mask'); qa = P.h5find(h, 'algorithm QA'); fpall = {}
                h.visititems(lambda n, o: fpall.__setitem__(n.split('/')[-1], o[()]) if hasattr(o, 'shape') and n.split('/')[-1].startswith('FP_') else None)
                gw = geo_window(gg[0]['url'], box, row_hint(fpall, box))
                if gw is None: continue
                win, sl, geo = gw; geo['geo_granule'] = gg[0]['name']
                m = fpall.get('FP_line')
                inw = ((m >= win[0]) & (m < win[1]) & (fpall['FP_sample'] >= win[2]) & (fpall['FP_sample'] < win[3])) if m is not None and len(m) else np.zeros(0, bool)
                fpw = {k: np.asarray(v)[inw] for k, v in fpall.items() if np.ndim(v) == 1 and len(v) == len(inw)}
                parts.append(dict(fire_mask=fm[sl].astype(np.uint8), algorithm_qa=qa[sl].astype(np.uint32) if qa is not None else np.zeros(0),
                                  row0=win[0], col0=win[2], granule=g['name'], granule_start=str(g['start']), **geo, **fpw))
            os.remove(fpath)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not parts: return dict(pass_key=pk, status='outside_window')
    fn = f"{out}/crops/{pk.replace('|', '_').replace(' ', '')}.npz"
    flat = {f'{k}_{i}': np.asarray(v) for i, p in enumerate(parts) for k, v in p.items()}
    np.savez_compressed(fn, n_parts=len(parts), sensor=sensor, pass_key=pk, **flat)
    return dict(pass_key=pk, file=os.path.basename(fn), sensor=sensor, granule_start=parts[0]['granule_start'], n_parts=len(parts),
                shape=str(parts[0]['fire_mask'].shape), n_fire_px=int(sum((p['fire_mask'] >= 7).sum() for p in parts)),
                bytes=os.path.getsize(fn), status='ok')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=P.DEF_OUT); ap.add_argument('--plan-csv', action='append')
    ap.add_argument('--workers', type=int, default=12); ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--max-gb', type=float, default=6.0)
    a = ap.parse_args()
    plans = a.plan_csv or [P.PLAN]
    X = pd.concat([pd.read_csv(p, parse_dates=['t_utc']) for p in plans], ignore_index=True)
    G = X.groupby('pass_key').agg(sensor=('sensor', 'first'), t=('t_utc', 'median'), W=('lon0', 'min'), S=('lat0', 'min'),
                                  E=('lon1', 'max'), N=('lat1', 'max')).reset_index().sort_values('t')
    if a.limit: G = G.head(a.limit)
    os.makedirs(f'{a.out}/crops', exist_ok=True); idx_fn = f'{a.out}/index.csv'
    done = pd.read_csv(idx_fn) if os.path.exists(idx_fn) else pd.DataFrame(columns=['pass_key', 'status'])
    skip = set(done[done.status.isin(['ok', 'no_granule', 'outside_window'])].pass_key)
    todo = [r for r in G.itertuples() if r.pass_key not in skip]
    print(f'{len(G)} passes, {len(todo)} to do, {a.workers} workers', flush=True)
    rows, t0, used = [], time.time(), 0
    with ProcessPoolExecutor(a.workers) as ex:   # processes: fsspec runs one shared IO loop per process
        fut = {ex.submit(crop_pass, r.pass_key, r.sensor, r.t, (r.W, r.S, r.E, r.N), a.out): r.pass_key for r in todo}
        for i, f in enumerate(as_completed(fut)):
            try: row = f.result()
            except PermissionError as e: row = dict(pass_key=fut[f], status=f'refused: {e}')
            except Exception as e: row = dict(pass_key=fut[f], status=f'error: {type(e).__name__}')
            rows.append(row); used += row.get('bytes', 0) or 0
            if i % 50 == 0 or i == len(todo) - 1:
                done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True); rows = []; done.to_csv(idx_fn, index=False)
                st = done.status.astype(str).str.split(':').str[0].value_counts().to_dict()
                print(f'{i + 1}/{len(todo)} {time.time() - t0:.0f}s {st}', flush=True)
            if used > a.max_gb * 1024 ** 3:
                print('crop cap reached; stopping'); ex.shutdown(cancel_futures=True); break
    if rows: done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True); done.to_csv(idx_fn, index=False)
    print('done;', (done.status == 'ok').sum(), 'crops in', a.out)


if __name__ == '__main__':
    main()
