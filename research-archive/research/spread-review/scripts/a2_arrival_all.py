"""Dated truth: arrival time for every 40 m pixel of every multi-look fire's outline (scar outlines v1), with the
LOSO-chosen setting from a1 (v = 15 m/h beyond the VIIRS pixel footprints, lead 0).
Out: arrival/arrival_px.parquet (fire, x, y, t_arrival UTC, dated = within 24 h of the last detection), arrival/fires.parquet"""
import pandas as pd, numpy as np, geopandas as gpd, sys
from shapely.ops import unary_union
from rasterio.features import rasterize
from rasterio.transform import from_origin
S = sys.argv[1]; OUT = sys.argv[2]; V, RES = 15.0, 40.0
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-15') & (md <= '06-15')].copy()
A['scan'] = A.scan.fillna(0.375).clip(lower=0.3); A['track'] = A.track.fillna(0.375).clip(lower=0.3)
L = pd.read_csv(S + '/d/firms_alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time'])
key = lambda d: d.latitude.round(4).astype(str) + '_' + d.longitude.round(4).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.fillna(-1).astype(int).astype(str)
L['key'] = key(L); A['key'] = key(A)
M = A[['fire', 'key']].merge(L[['key', 'event_id']], on='key')
G = gpd.read_parquet(S + '/d/evgeom.parquet').to_crs(32643).set_index('event_id')
nl = A.groupby('fire').look.nunique()
px, fs = [], []
for f, eids in M.groupby('fire').event_id.apply(lambda s: [e for e in s.unique() if e in G.index]).items():
    if not eids or nl.get(f, 0) < 2: continue
    poly = unary_union(list(G.loc[eids].geometry)).buffer(0)
    if poly.is_empty: continue
    x0, y0, x1, y1 = poly.bounds; w, h = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    m = rasterize([poly], out_shape=(h, w), transform=from_origin(x0, y1, RES, RES)).astype(bool)
    r, c = np.where(m); X = x0 + (c + .5) * RES; Y = y1 - (r + .5) * RES
    d = A[A.fire == f]; t0 = d.t.min()
    th = ((d.t - t0).dt.total_seconds() / 3600).values
    dx = np.maximum(np.abs(X[:, None] - d.x.values[None]) - d.scan.values[None] * 500, 0)
    dy = np.maximum(np.abs(Y[:, None] - d.y.values[None]) - d.track.values[None] * 500, 0)
    T = (th[None] + np.hypot(dx, dy) / V).min(1)
    last = th.max()
    px.append(pd.DataFrame(dict(fire=f, x=X.astype(np.float32), y=Y.astype(np.float32), t_arrival=t0 + pd.to_timedelta(T, 'h'), dated=T <= last + 24)))
    fs.append(dict(fire=f, n_look=nl[f], area_ha=m.sum() * RES * RES / 1e4, share_dated=float((T <= last + 24).mean()),
                   share_by_first=float((T <= 0.01).mean()), t_first=t0, hours=last))
P = pd.concat(px, ignore_index=True); F = pd.DataFrame(fs)
P.to_parquet(OUT + '/arrival_px.parquet'); F.to_parquet(OUT + '/fires.parquet')
print(len(F), 'fires', len(P), 'pixels; share of outline dated (<= last detection + 24 h):', round(F.share_dated.median(), 3),
      '; share already inside first-look footprints:', round(F.share_by_first.median(), 3))
