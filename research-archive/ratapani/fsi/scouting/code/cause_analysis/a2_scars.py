"""Scar patch geometry (20 m burn rasters, 2017-2026): size, elongation, mean width; link to VIIRS and to 500 m cells."""
import sys, json, numpy as np, pandas as pd
from scipy import ndimage
sys.path.insert(0, '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an')
import tif
R = '/mnt/project-files/research/ratapani-burn-labels/rasters/'
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an/'
X0, Y1, RES = 739300.0, 2558500.0, 20.0
# cell index raster: grid cells x0,y0 (UTM, 500 m)
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
cx = {(int(f['properties']['x0']), int(f['properties']['y0'])): f['properties']['cell_id'] for f in G}
rows = []; links = []
for Y in range(2017, 2027):
    a, _ = tif.read(R + f'burn_{Y}.tif'); end, start, mag = a
    H, W = end.shape
    for d in np.unique(end[end > -999]):
        m = end == d
        lab, k = ndimage.label(m, structure=np.ones((3, 3)))
        if k == 0: continue
        idx = ndimage.find_objects(lab)
        for i, sl in enumerate(idx, 1):
            yy, xx = np.nonzero(lab[sl] == i); npx = len(yy)
            if npx < 5: continue
            yy = yy + sl[0].start; xx = xx + sl[1].start
            p = np.c_[xx, yy].astype(float); c = p.mean(0); q = p - c
            ev = np.linalg.eigvalsh(np.cov(q.T) + np.eye(2) * 1 / 12) if npx > 2 else np.array([1, 1])
            L = 4 * np.sqrt(ev[1]) * RES  # ~ length of major axis (m), uniform-line approx: sd*sqrt(12)=3.46
            elong = np.sqrt(ev[1] / ev[0])
            width = npx * RES * RES / max(L, RES)
            ux, uy = X0 + c[0] * RES + 10, Y1 - c[1] * RES - 10
            cell = cx.get((int(np.floor(ux / 500) * 500), int(np.floor(uy / 500) * 500)), -1)
            ux_ = X0 + xx * RES + 10; uy_ = Y1 - yy * RES - 10
            for cc_ in set(zip((np.floor(ux_ / 500) * 500).astype(int), (np.floor(uy_ / 500) * 500).astype(int))):
                if cc_ in cx: links.append((Y, int(d), len(rows), cx[cc_]))
            rows.append((Y, int(d), int(start[yy[0], xx[0]]), npx * 0.04, elong, L, width, float(mag[yy, xx].mean()), ux, uy, cell))
    print(Y, len(rows), flush=True)
P = pd.DataFrame(rows, columns=['season', 'end_doy', 'start_doy', 'ha', 'elong', 'len_m', 'width_m', 'mag', 'x', 'y', 'cell_id'])
P.to_parquet(OUT + 'patches.parquet'); pd.DataFrame(links, columns=['season', 'end_doy', 'pid', 'cell_id']).to_parquet(OUT + 'patch_cells.parquet')
P['month'] = pd.to_datetime(P.season.astype(str) + '-01-01') + pd.to_timedelta(P.end_doy - 1, 'D'); P['month'] = P.month.dt.month
P['linear'] = (P.elong >= 4) & (P.width_m <= 80) & (P.len_m >= 300)
print('\npatches', len(P), ' (>=5 px = 0.2 ha)')
print('area quantiles ha', P.ha.quantile([.25, .5, .75, .9, .99]).round(2).tolist())
print('elong quantiles', P.elong.quantile([.25, .5, .75, .9, .99]).round(2).tolist())
print('linear share (elong>=4, width<=80 m, len>=300 m): n', int(P.linear.sum()), 'share', round(P.linear.mean(), 3), ' area share', round(P.ha[P.linear].sum() / P.ha.sum(), 3))
print(P.groupby('month').agg(n=('ha', 'size'), ha_med=('ha', 'median'), ha_sum=('ha', 'sum'), elong_med=('elong', 'median'), linear=('linear', 'mean'), mag=('mag', 'median')).round(3).to_string())
print('\nby season:\n', P.groupby('season').agg(n=('ha', 'size'), linear=('linear', 'mean'), lin_ha=('ha', lambda s: s[P.loc[s.index, 'linear']].sum())).round(3).to_string())
