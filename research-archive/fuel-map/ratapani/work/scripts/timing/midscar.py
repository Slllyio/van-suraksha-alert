"""Burned-so-far at the exact minute of every mid-fire Sentinel-2/Landsat scene (352 scenes, 334 fires).
Per scene: final scar S (same rule as passfront.py, S-NPP events), chip around S on the 20 m label grid,
pre = last clear look before the first detection day, post = first clear look after the last detection,
burned-by-T = pixel in S whose NBR drop pre->mid is >= max(0.10, half its drop pre->post), or a hot pixel."""
import sys, datetime as dt, numpy as np, pandas as pd, rasterio
from concurrent.futures import ThreadPoolExecutor
from scipy import ndimage
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/scripts')
import alert_scar as A
from pyproj import Transformer
B = '/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{}.tif'
with rasterio.open(B.format(2017)) as s: TR = s.transform
ms = pd.read_parquet('/mnt/project-files/ratapani/spread/results/midevent_scenes.parquet')
ms['T'] = pd.to_datetime(ms.date.dt.strftime('%Y-%m-%d') + ' ' + ms.t_scene)
ev = pd.read_parquet('/tmp/claude-0/fuel/inv/viirs_events_spread.parquet')
af = pd.read_csv('/mnt/project-files/fire-alert-scars/out/af/af_pixels_clean.csv')
to_ll = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True)
BURN = {}
def burn(yr):
    if yr not in BURN:
        with rasterio.open(B.format(yr)) as s: BURN[yr] = (s.read(1), s.read(2))
    return BURN[yr]

def scar(e, yr):
    g = ev[ev.event == e]; be, bs = burn(yr)
    r, c = rasterio.transform.rowcol(TR, g.x.values, g.y.values); r, c = np.array(r), np.array(c)
    i0, j0 = max(r.min() - 60, 0), max(c.min() - 60, 0); i1, j1 = r.max() + 60, c.max() + 60
    d0, d1 = g.t.min().dayofyear, g.t.max().dayofyear
    m = (be[i0:i1, j0:j1] > -999) & (be[i0:i1, j0:j1] >= d0 - 2) & (bs[i0:i1, j0:j1] <= d1 + 2)
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    near = np.zeros(m.shape, bool); near[r - i0, c - j0] = True; near = ndimage.binary_dilation(near, iterations=20)
    k = np.unique(lab[near & m]); k = k[k > 0]; S = np.isin(lab, k)
    if S.sum() < 10: return None
    ys, xs = np.where(S); y0, x0 = max(ys.min() - 25, 0), max(xs.min() - 25, 0)
    S = S[y0:ys.max() + 26, x0:xs.max() + 26]
    return S, i0 + y0, j0 + x0, g

def looks_for(tr, h, w, d0, d1, Smask):
    x0, y1 = tr.c, tr.f
    bbox = to_ll.transform_bounds(x0, y1 - h * 20, x0 + w * 20, y1)
    groups = {}
    for col, s in (('sentinel-2-l2a', 's2'), ('landsat-c2-l2', 'ls')):
        q = {'eo:cloud_cover': {'lt': 80}}
        if s == 'ls': q['platform'] = {'in': ['landsat-8', 'landsat-9']}
        for it in A.catalog().search(collections=[col], bbox=bbox, datetime=f'{d0}/{d1}', query=q).items():
            groups.setdefault((it.datetime.date(), s), []).append(it)
    return groups

def read_look(items, s, tr, h, w):
    n = max(h, w); nb, ni = A.look(items, s, tr, n); return nb[:h, :w]

def one(row):
    try:
        out = scar(row.event, row.season)
        if out is None: return None
        S, i0, j0, g = out; h, w = S.shape
        tr = rasterio.transform.from_origin(TR.c + j0 * 20, TR.f - i0 * 20, 20, 20)
        t_first, t_last = g.t.min(), g.t.max(); T = row['T']
        groups = looks_for(tr, h, w, (t_first - pd.Timedelta(days=30)).date(), (t_last + pd.Timedelta(days=40)).date(), S)
        keys = sorted(groups); cache = {}
        def get(k):
            if k not in cache: cache[k] = read_look(groups[k], k[1], tr, h, w)
            return cache[k]
        clear = lambda a: np.isfinite(a)[S].mean()
        pre = None
        for k in sorted([k for k in keys if k[0] < t_first.date()], reverse=True):
            if clear(get(k)) >= 0.7: pre = k; break
        post = None
        for k in [k for k in keys if k[0] > t_last.date()]:
            if clear(get(k)) >= 0.7: post = k; break
        mk = (T.date(), row.sensor)
        if pre is None or post is None or mk not in groups: return dict(event=row.event, scene=row.scene, status='no_pre_post' if mk in groups else 'no_mid')
        a0, a1, am = get(pre), get(post), get(mk)
        dpost, dmid = a0 - a1, a0 - am
        ok = S & np.isfinite(dpost) & np.isfinite(dmid)
        hot = np.zeros(S.shape, bool)
        hp = af[(af.scene == row.scene)]
        if len(hp):
            x, y = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform(hp.lon.values, hp.lat.values)
            rr, cc = rasterio.transform.rowcol(tr, x, y); rr, cc = np.array(rr), np.array(cc); k = (rr >= 0) & (cc >= 0) & (rr < h) & (cc < w)
            hot[rr[k], cc[k]] = True
        bym = ok & (dmid >= np.maximum(0.10, 0.5 * dpost)) | (hot & S)
        np.savez_compressed(f'chips/{row.event}_{row.scene[:40]}.npz', S=S, bym=bym, ok=ok, hot=hot, dmid=dmid.astype(np.float16), dpost=dpost.astype(np.float16), i0=i0, j0=j0)
        return dict(event=row.event, season=row.season, scene=row.scene, sensor=row.sensor, T=T, t_first=t_first, t_last=t_last, pre=str(pre[0]), post=str(post[0]),
                    scar_px=int(S.sum()), ok_frac=float(ok.sum() / S.sum()), burned_frac=float(bym[ok].mean()) if ok.any() else np.nan,
                    burned_ha=float(bym.sum() * 0.04), hot_in_scar=int((hot & S).sum()), dpost_med=float(np.nanmedian(dpost[S])), status='ok')
    except Exception as ex:
        return dict(event=row.event, scene=row.scene, status=f'err {ex}'[:120])

import os; os.makedirs('chips', exist_ok=True)
rows = [r for _, r in ms.iterrows()]
with ThreadPoolExecutor(6) as ex: res = [x for x in ex.map(one, rows) if x is not None]
d = pd.DataFrame(res); d.to_parquet('midscar.parquet'); print(d.status.str[:12].value_counts()); print(d[d.status == 'ok'][['ok_frac', 'burned_frac']].describe())
