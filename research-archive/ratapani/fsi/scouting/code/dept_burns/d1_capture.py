"""Capture every January-February burn in MP forest, each season, and sort it into department-like (control) burning or not.
Two sources: (1) burn scars 2017-25 (60 m rasters, scratch r26, per-cell burn day) for every fire whose first detection falls in
Jan-Feb (IST): area, forest ha, shape (PCA length/width), share of cells on a beat boundary (within 90 m), VIIRS points matched
to the scar (day/night, max FRP, days); (2) VIIRS burn-day clusters 2014-26 (early_burns table: 750 m same-day clusters, with
the control-like flag) for burns too small or too early for a scar, and for 2014-16 and 2026.
Rules (plain): strip = scar length/width >= 4 and width <= 150 m, or >= 60% of scar cells within 90 m of a beat boundary;
pre-15 Feb: department-like unless night-burning or hot (max FRP > 10 MW) and multi-day; 15-28 Feb: department-like only if
strip, or control-like (day-only, single-day, <= 2 points, FRP <= 5 MW). Out: out/scar_fires_jan_feb.csv, out/viirs_clusters_jan_feb.csv"""
import os, sys, numpy as np, pandas as pd, geopandas as gpd
from rasterio import features; from rasterio.transform import from_origin; from scipy import ndimage as ndi
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'); import cb0 as B
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
BE = gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson')[['beat_uid', 'Division', 'geometry']].to_crs(32643)
BE['edge'] = BE.geometry.boundary
import pyarrow.parquet as pq
VT = pq.read_table(B.VIIRS, columns=['latitude', 'longitude', 'season', 'doy', 'Division', 'type', 'daynight', 'frp'], filters=[('type', '=', 0)]).to_pandas()
VT = VT[VT.doy <= 59]; VT['Division'] = VT.Division.replace({'Barghat Project': 'Barghat_Project', 'Kanha Tiger Reserve': 'Kanha_Tiger_Reserve', 'PTR MP': 'PTR_MP'})
VG = {k: g for k, g in VT.groupby(['Division', 'season'])}; print('viirs points Jan-Feb loaded', len(VT), flush=True)
rows = []
for key in B.KEYS:
    L, FOR = B.load_div(key); H, W = L['H'], L['W']; tr = from_origin(L['x0'], L['y1'], B.RES, B.RES)
    x1, y0 = L['x0'] + W * B.RES, L['y1'] - H * B.RES
    be = BE.cx[L['x0']:x1, y0:L['y1']]
    E = features.rasterize(((g, 1) for g in be.edge if g is not None and not g.is_empty), out_shape=(H, W), transform=tr, all_touched=True, dtype='uint8') if len(be) else np.zeros((H, W), 'uint8')
    DE = ndi.distance_transform_edt(E == 0) * B.RES                     # metres to nearest beat boundary
    pts = {y: VG.get((key, y), VT.iloc[0:0]) for y in B.YEARS}
    for y in B.YEARS:
        p = pts[y]; p = p[(p.doy <= 59)]
        if len(p): pr, pc = B.rc(L, p.latitude.values, p.longitude.values); p = p.assign(r=pr, c=pc)
        for f in L['fires']:
            if f['year'] != y: continue
            t0 = f['t0'] + pd.Timedelta(hours=5.5)
            if t0.month > 2: continue
            h, w = f['shape']; Mm = np.unpackbits(f['M'])[:h * w].astype(bool).reshape(h, w); rr, cc = np.nonzero(Mm); rr = rr + f['r0']; cc = cc + f['c0']
            n = len(rr); ok = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W); rr, cc = rr[ok], cc[ok]
            if len(rr) < 2: continue
            X = np.stack([cc * B.RES, -rr * B.RES], 1); X = X - X.mean(0); ev = np.linalg.eigvalsh(np.cov(X.T)); ev = np.clip(ev, 1e-6, None)
            length, width = 2 * np.sqrt(3 * ev[1]), 2 * np.sqrt(3 * ev[0])          # uniform-strip equivalents, metres
            edge_share = (DE[rr, cc] <= 90).mean(); ndays = int(f['day'].max()) + 1
            # VIIRS points on the scar (within one cell), from the day before first detection to the last burn day
            npts = night = frp = 0.0; vdays = 0
            if len(p):
                d0 = t0.dayofyear; q = p[(p.doy >= d0 - 1) & (p.doy <= d0 + ndays)]
                if len(q):
                    S = np.zeros((H, W), bool); S[rr, cc] = True; S = ndi.binary_dilation(S, iterations=1)
                    inr = (q.r.values >= 0) & (q.r.values < H) & (q.c.values >= 0) & (q.c.values < W); q = q[inr]; q = q[S[q.r.values, q.c.values]]
                    npts = len(q); night = (q.daynight == 'N').mean() if npts else 0; frp = q.frp.max() if npts else 0; vdays = q.doy.nunique()
            rows.append(dict(key=key, division=L['div'], fire=f['fire'], season=y, date=t0.date(), doy=t0.dayofyear, ha=f['ha'], forest_ha=f['forest_ha'], cells=len(rr), length_m=length, width_m=width,
                             elong=length / max(width, 1), edge_share=edge_share, burn_days=ndays, viirs_pts=npts, night_share=night, frp_max=frp, viirs_days=vdays,
                             x=L['x0'] + cc.mean() * B.RES, y=L['y1'] - rr.mean() * B.RES))
    print(key, len(rows), flush=True)
F = pd.DataFrame(rows)
from pyproj import Transformer; INV = Transformer.from_crs(32643, 4326, always_xy=True); F['lon'], F['lat'] = INV.transform(F.x.values, F.y.values)
F['strip'] = ((F.elong >= 4) & (F.width_m <= 150)) | (F.edge_share >= 0.6)
F['hot_or_night'] = (F.night_share > 0) | (F.frp_max > 10)
F['pre15'] = F.doy <= 45
F['cls'] = np.where(F.pre15 & F.strip, 'pre-15 Feb strip', np.where(F.pre15 & ~(F.hot_or_night & (F.burn_days > 1)), 'pre-15 Feb block', np.where(F.pre15, 'pre-15 Feb hot multi-day', np.where(F.strip, '15-28 Feb strip', np.where((F.night_share == 0) & (F.frp_max <= 5) & (F.viirs_pts <= 2) & (F.burn_days <= 1), '15-28 Feb control-like', '15-28 Feb wildfire-like')))))
F['dept_like'] = F.cls.isin(['pre-15 Feb strip', 'pre-15 Feb block', '15-28 Feb strip', '15-28 Feb control-like'])
F.to_csv(OUT + 'scar_fires_jan_feb.csv', index=False)
print(F.groupby(['season', 'cls']).size().unstack().fillna(0).astype(int)); print(F.groupby('cls')[['ha', 'forest_ha']].sum().round(0))
# VIIRS clusters Jan-Feb 2014-26
C = pd.read_parquet('/mnt/project-files/ratapani/fsi/scouting/code/early_burns/out/clusters_oct_to_15mar.parquet'); C['date'] = pd.to_datetime(C.date)
C = C[(C.date.dt.month <= 2)].copy(); C['doy'] = C.date.dt.dayofyear; C['pre15'] = C.doy <= 45
C['cls'] = np.where(C.pre15 & C.flag, 'pre-15 Feb control-like', np.where(C.pre15, 'pre-15 Feb other', np.where(C.flag, '15-28 Feb control-like', '15-28 Feb other')))
from pyproj import Transformer; T2 = Transformer.from_crs(7755, 4326, always_xy=True); C['lon'], C['lat'] = T2.transform(C.x.values, C.y.values)
C.to_csv(OUT + 'viirs_clusters_jan_feb.csv', index=False); print(C.groupby(['season', 'cls']).size().unstack().fillna(0).astype(int))
