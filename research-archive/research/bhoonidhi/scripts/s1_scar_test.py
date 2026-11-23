"""Bhoonidhi thread: does C-band radar (EOS-04's band) see MP forest-fire scars? Tested with Sentinel-1 RTC (Planetary Computer,
same C-band, free) on MP burn-scar outlines (fire-alert-scars/mp history, status scar, 2022-25, 20-2000 ha).
Per scar: post = first S1 scene 1-30 d after the fire date; pre = latest scene of the same relative orbit 1-40 d before.
Change (dB, post - pre, linear mean) inside the scar vs a 300-1500 m ring outside it; pixel AUC (inside drop vs ring).
python3 s1_scar_test.py N"""
import os, sys, json, warnings, numpy as np, pandas as pd, rasterio, pystac_client, planetary_computer as pc
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio import features
from scipy import ndimage
from shapely import wkt
from shapely.geometry import mapping
from shapely.ops import transform as stransform
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings('ignore')
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='2')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300; RES = 20.0
MO = '/mnt/project-files/fire-alert-scars/mp/out'
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom
S = pd.read_csv(f'{MO}/scars_mp_hist.csv'); S = S[(S.status == 'scar') & S.scar_ha.between(20, 2000)].copy()
S['fdate'] = pd.to_datetime(S.event_id.str[1:9], format='%Y%m%d'); S = S[S.fdate.dt.year >= 2022]
ev = pd.read_csv(f'{MO}/mp_events.csv', usecols=['event_id', 'forest']); S = S[S.event_id.isin(ev[ev.forest].event_id)]
S = S.sample(min(N, len(S)), random_state=0)
G = read_hist_geom(); G = G[G.event_id.isin(S.event_id)].set_index('event_id').geometry
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1', modifier=pc.sign_inplace)
def auc(a, b):
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 20 or len(b) < 20: return np.nan
    r = pd.Series(np.r_[a, b]).rank().values; return (r[:len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))
def read(it, tr, W, H):
    o = {}
    for b in ('vv', 'vh'):
        with rasterio.open(it.assets[b].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=tr, width=W, height=H, resampling=Resampling.average, nodata=0) as v:
            x = v.read(1).astype(np.float32)
        o[b] = np.where(x > 0, x, np.nan)
    return o
def one(r):
    try:
        from shapely.affinity import translate
        poly = stransform(lambda x, y, z=None: to43(x, y), wkt.loads(G[r.event_id])); dec = translate(poly, 3000, 0)
        x0, y0, x1, y1 = poly.union(dec).bounds; x0 -= 1600; y0 -= 1600; x1 += 1600; y1 += 1600
        W, H = int((x1 - x0) / RES), int((y1 - y0) / RES); tr = from_origin(x0, y1, RES, RES)
        ins = features.rasterize([(mapping(poly), 1)], out_shape=(H, W), transform=tr).astype(bool)
        d = ndimage.distance_transform_edt(~ins) * RES; ring = (d > 300) & (d < 1500)
        dins = features.rasterize([(mapping(dec), 1)], out_shape=(H, W), transform=tr).astype(bool) & (d > 300)
        dd2 = ndimage.distance_transform_edt(~dins) * RES; dring = (dd2 > 300) & (dd2 < 1500) & (d > 300)
        ll = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform((x0 + x1) / 2, (y0 + y1) / 2)
        pt = {'type': 'Point', 'coordinates': list(ll)}; f = r.fdate
        post = sorted(cat.search(collections=['sentinel-1-rtc'], intersects=pt, datetime=f'{f + pd.Timedelta(days=1):%Y-%m-%d}/{f + pd.Timedelta(days=30):%Y-%m-%d}').items(), key=lambda i: i.datetime)
        if not post: return dict(event_id=r.event_id, skip='no post')
        po = post[0]; orb = po.properties.get('sat:relative_orbit')
        pre = [i for i in cat.search(collections=['sentinel-1-rtc'], intersects=pt, datetime=f'{f - pd.Timedelta(days=40):%Y-%m-%d}/{f - pd.Timedelta(days=1):%Y-%m-%d}').items() if i.properties.get('sat:relative_orbit') == orb]
        if not pre: return dict(event_id=r.event_id, skip='no pre same orbit')
        pr = max(pre, key=lambda i: i.datetime)
        A, B = read(pr, tr, W, H), read(po, tr, W, H); o = dict(event_id=r.event_id, year=f.year, scar_ha=r.scar_ha, rdnbr=r.rdnbr_median, severity=r.severity,
                                                               pre=str(pr.datetime.date()), post=str(po.datetime.date()), days_after=(po.datetime.replace(tzinfo=None) - f).days)
        for b in ('vv', 'vh'):
            ch = 10 * np.log10(ndimage.uniform_filter(np.nan_to_num(B[b]), 3) / ndimage.uniform_filter(np.nan_to_num(A[b]), 3))
            ch[~(np.isfinite(A[b]) & np.isfinite(B[b]))] = np.nan
            ci, cr = ch[ins], ch[ring]
            o[f'{b}_in'] = float(np.nanmedian(ci)); o[f'{b}_ring'] = float(np.nanmedian(cr)); o[f'{b}_delta'] = o[f'{b}_in'] - o[f'{b}_ring']
            o[f'{b}_auc_drop'] = float(auc(-ci, -cr)); o[f'{b}_auc_rise'] = float(auc(ci, cr))
            di, dr = ch[dins], ch[dring]
            o[f'{b}_dec_delta'] = float(np.nanmedian(di) - np.nanmedian(dr)) if dins.sum() > 20 else np.nan
            o[f'{b}_dec_auc_drop'] = float(auc(-di, -dr))
        return o
    except Exception as e:
        return dict(event_id=r.event_id, skip='error ' + str(e)[:80])
rows = []
with ThreadPoolExecutor(12) as ex:
    for i, o in enumerate(ex.map(one, list(S.itertuples()))):
        rows.append(o)
        if i % 50 == 0: print(i, flush=True)
R = pd.DataFrame(rows); R.to_csv('/tmp/claude-0/s1/s1_scar_rows.csv', index=False)
U = R[R.skip.isna()] if 'skip' in R else R
res = dict(tried=len(R), used=len(U), skipped=R.skip.value_counts().to_dict() if 'skip' in R else {})
for b in ('vv', 'vh'):
    res[b] = dict(delta_median_db=round(float(U[f'{b}_delta'].median()), 2), delta_q25_q75=[round(float(U[f'{b}_delta'].quantile(q)), 2) for q in (.25, .75)],
                  share_drop_gt_1db=round(float((U[f'{b}_delta'] < -1).mean()), 3), share_rise_gt_1db=round(float((U[f'{b}_delta'] > 1).mean()), 3),
                  pixel_auc_drop_median=round(float(U[f'{b}_auc_drop'].median()), 3), share_auc_drop_ge_0p7=round(float((U[f'{b}_auc_drop'] >= .7).mean()), 3),
                  share_auc_any_dir_ge_0p7=round(float(((U[f'{b}_auc_drop'] >= .7) | (U[f'{b}_auc_rise'] >= .7)).mean()), 3))
for b in ('vv', 'vh'):
    v = U[[f'{b}_delta', f'{b}_dec_delta']].dropna(); y = np.r_[np.ones(len(v)), np.zeros(len(v))]
    res[b]['decoy_delta_median_db'] = round(float(v[f'{b}_dec_delta'].median()), 2)
    res[b]['decoy_share_drop_gt_1db'] = round(float((v[f'{b}_dec_delta'] < -1).mean()), 3)
    res[b]['decoy_share_auc_drop_ge_0p7'] = round(float((U[f'{b}_dec_auc_drop'] >= .7).mean()), 3)
    res[b]['scar_vs_decoy_auc'] = round(float(auc(-v[f'{b}_delta'].values, -v[f'{b}_dec_delta'].values)), 3)
res['by_size'] = {str(k): dict(n=len(v), vh_delta=round(float(v.vh_delta.median()), 2), vh_auc_any07=round(float(((v.vh_auc_drop >= .7) | (v.vh_auc_rise >= .7)).mean()), 3))
                  for k, v in U.groupby(pd.cut(U.scar_ha, [20, 50, 150, 2000]), observed=True)}
res['by_severity'] = {str(k): dict(n=len(v), vh_delta=round(float(v.vh_delta.median()), 2)) for k, v in U.groupby('severity')}
json.dump(res, open('/tmp/claude-0/s1/s1_scar.json', 'w'), indent=1); print(json.dumps(res, indent=1))
