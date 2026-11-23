"""Step 4 (light version; the full per-pixel b4_blocks.py was too slow and was stopped): what do MODIS and the
Sentinel-2/Landsat hot pixels add over VIIRS alone, for the 146 big fires?
Per fire, VIIRS only vs all sensors: number of distinct look times (detections within 2 h = one look), median and longest
gap between looks, share of the scar covered by at least one real-size block, looks at hours VIIRS never looks.
Then growth-direction persistence (b3 method: new ground beyond everything seen before, bearing from the earlier centroid)
with all sensors as looks, against the same shuffled-order baseline.
Out: results/sensors_added.csv, results/sensors_added_summary.json
"""
import glob, json, pickle
import numpy as np, pandas as pd, pyproj
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.spatial import cKDTree
from shapely.geometry import Point
ROOT = '/mnt/project-files'; R = f'{ROOT}/research/big-fires/results'
F = pd.read_csv(f'{R}/fires.csv'); A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t']); S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
h = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_*.csv')], ignore_index=True)
h['t'] = pd.to_datetime(h.date + ' ' + h.time_utc); h['x'], h['y'] = tp(h.lon.values, h.lat.values)
RES = 30.0; rng = np.random.default_rng(2)

def cover(poly, b):
    x0, y0, x1, y1 = poly.bounds; tr = from_origin(x0, y1, RES, RES)
    shp = (int((y1 - y0) / RES) + 1, int((x1 - x0) / RES) + 1)
    m = rasterize([(poly, 1)], out_shape=shp, transform=tr).astype(bool); c = np.zeros(shp, bool)
    for r in b.itertuples():
        c0 = max(int((r.x - r.hw - x0) / RES), 0); c1 = min(int(np.ceil((r.x + r.hw - x0) / RES)), shp[1])
        r0 = max(int((y1 - r.y - r.hh) / RES), 0); r1 = min(int(np.ceil((y1 - r.y + r.hh) / RES)), shp[0])
        if c1 > c0 and r1 > r0: c[r0:r1, c0:c1] = True
    return (c & m).sum() / m.sum()

def growth_cos(b):
    b = b.sort_values('t'); lk = (b.t.diff() > pd.Timedelta(hours=2)).cumsum().values; b = b.assign(look=lk)
    order = list(b.groupby('look').t.min().sort_values().index)
    def run(order):
        out = []
        for k in range(1, len(order)):
            prev = b[b.look.isin(order[:k])][['x', 'y']].values; cur = b[b.look == order[k]][['x', 'y']].values
            new = cur[cKDTree(prev).query(cur)[0] > 400]
            if len(new): c0 = prev.mean(0); out.append(np.arctan2(*(new.mean(0) - c0)[::-1]))
        return [np.cos(out[i] - out[i - 1]) for i in range(1, len(out))]
    return run(order), [run(list(rng.permutation(order))) for _ in range(100)]

rows, obs, null = [], {'viirs': [], 'all': []}, {'viirs': [], 'all': []}
for _, f in F[F.big].iterrows():
    poly = S[f.fire]; a = A[A.fire == f.fire].copy()
    md = a.sat == 'modis'
    a['hw'] = a.scan.fillna(pd.Series(np.where(md, 1, .375), index=a.index)) * 500; a['hh'] = a.track.fillna(pd.Series(np.where(md, 1, .375), index=a.index)) * 500
    x0, y0, x1, y1 = poly.bounds; zb = poly.buffer(100)
    hh = h[(h.x > x0 - 100) & (h.x < x1 + 100) & (h.y > y0 - 100) & (h.y < y1 + 100) & (h.t >= a.t.min() - pd.Timedelta(days=1)) & (h.t <= a.t.max() + pd.Timedelta(days=1))]
    hh = hh[np.array([zb.contains(Point(p)) for p in zip(hh.x, hh.y)], dtype=bool)].assign(hw=15.0, hh=15.0, sat='hotpix')
    allb = pd.concat([a[['t', 'x', 'y', 'hw', 'hh', 'sat']], hh[['t', 'x', 'y', 'hw', 'hh', 'sat']]], ignore_index=True)
    rec = dict(fire=f.fire, area_ha=f.area_ha, n_viirs=int((~md).sum()), n_modis=int(md.sum()), n_hotpix=len(hh))
    for mode, b in [('viirs', allb[~allb.sat.isin(['modis', 'hotpix'])]), ('all', allb)]:
        b = b.sort_values('t'); lk = (b.t.diff() > pd.Timedelta(hours=2)).cumsum()
        lt = b.groupby(lk.values).t.min().sort_values()
        gaps = lt.diff().dt.total_seconds().dropna() / 3600
        hrs = ((lt + pd.Timedelta(hours=5, minutes=30)).dt.hour)
        rec.update({f'{mode}_looks': len(lt), f'{mode}_gap_med': gaps.median(), f'{mode}_gap_max': gaps.max(),
                    f'{mode}_cover': cover(poly, b), f'{mode}_looks_8to12IST': int(((hrs >= 8) & (hrs < 12)).sum()),
                    f'{mode}_looks_other_hours': int((~(((hrs >= 0) & (hrs < 4)) | ((hrs >= 12) & (hrs < 16)))).sum())})
        o, n = growth_cos(b); obs[mode] += o; null[mode].append(n)
    rows.append(rec)
D = pd.DataFrame(rows); D.to_csv(f'{R}/sensors_added.csv', index=False)
summ = dict(fires=len(D), median=D.drop(columns='fire').median().round(2).to_dict(),
            fires_gaining_a_look=int((D.all_looks > D.viirs_looks).sum()),
            fires_with_hotpix=int((D.n_hotpix > 0).sum()), fires_with_modis=int((D.n_modis > 0).sum()))
for mode in obs:
    o = np.array(obs[mode]); pn = [np.mean(sum([nn[i] for nn in null[mode]], [])) for i in range(100)]
    summ[f'persistence_{mode}'] = dict(n=len(o), mean_cos=round(o.mean(), 3), within90=round((o > 0).mean(), 3),
                                       within45=round((o > np.cos(np.pi / 4)).mean(), 3), shuffled_95=[round(np.quantile(pn, .025), 3), round(np.quantile(pn, .975), 3)])
print(json.dumps(summ, indent=1)); json.dump(summ, open(f'{R}/sensors_added_summary.json', 'w'), indent=1)
