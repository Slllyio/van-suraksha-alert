"""Per-fire land-cover make-up of the scar, for reading the fuel thread's per-class variants (README 4b).
Writes data/event_classes.parquet: event, scar_px, grass_share (canopy < 10% on WorldCover tree/shrub/grass, the
prep_grass.py mask), canopy_mean (%), teak_mean (teak probability), wc_mode."""
import numpy as np, pandas as pd, rasterio, glob
from rasterio.warp import reproject, Resampling
import sim, score

def layer(path, nodata, scale):
    a = np.full((sim.NY, sim.NX), np.nan, np.float32)
    with rasterio.open(path) as s:
        reproject(rasterio.band(s, 1), a, src_nodata=nodata, dst_transform=rasterio.transform.from_origin(sim.X0, sim.Y0, sim.RES, sim.RES), dst_crs='EPSG:32643', resampling=Resampling.average, dst_nodata=np.nan)
    return a * scale

can = layer('/mnt/project-files/fuel-map/ratapani/canopy_cover_10m.tif', 65535, 0.1)   # percent
try:
    with rasterio.open('/mnt/project-files/fuel-map/ratapani/teak_probability_10m.tif') as s:
        nd, dt = s.nodata, s.dtypes[0]
    teak = layer('/mnt/project-files/fuel-map/ratapani/teak_probability_10m.tif', nd, 1.0)
    if np.nanmax(teak) > 1.5:
        teak = teak / (1000.0 if np.nanmax(teak) > 100 else 100.0)
except Exception as e:
    print('no teak layer', e); teak = np.full_like(can, np.nan)
veg = np.isin(sim.WC, [10, 20, 30]); grass = (can < 10) & veg
# cache the burn layers once (sim.G decompresses on every access)
G = {k: sim.G[k] for k in sim.G.files if k.startswith('burn_')}
class GG(dict):
    def __missing__(self, k):
        return sim.G[k]
sim.G = GG(G)
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.t.dt.month >= 1]
res = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f'{sim.DATA}/res_loose_lfi_m2_[0-3].parquet'))]) if glob.glob(f'{sim.DATA}/res_loose_lfi_m2_[0-3].parquet') else pd.read_parquet(f'{sim.DATA}/res_loose_lfi_m2.parquet')
ids = set(res.loc[res.scar_px >= 25, 'event'])
rows = []
for e, ev in v.groupby('event'):
    if e not in ids:
        continue
    ev = ev.sort_values('t'); s = int(ev.season.iloc[0])
    pad = int(2600 / sim.RES); r, c = sim.rc(ev.x.values, ev.y.values)
    i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX)
    S, _ = score.scar_footprint(dict(win=(i0, i1, j0, j1), season=s), ev)
    if S.sum() == 0:
        continue
    wcw = sim.WC[i0:i1, j0:j1][S]; vals, cnt = np.unique(wcw, return_counts=True)
    rows.append(dict(event=e, season=s, scar_px=int(S.sum()), grass_share=float(grass[i0:i1, j0:j1][S].mean()),
                     canopy_mean=float(np.nanmean(can[i0:i1, j0:j1][S])), teak_mean=float(np.nanmean(teak[i0:i1, j0:j1][S])),
                     wc_mode=int(vals[cnt.argmax()])))
d = pd.DataFrame(rows); d.to_parquet(f'{sim.DATA}/event_classes.parquet'); print(len(d)); print(d.describe().T)
