"""Step 3b: what lies under each fire's final scar (all 3,557 fires, not only the 964 in fires_ml), on the 20 m grid.
canopy (%), litter / grass (fuel map v3 end-April potential, t/ha), teak (%), slope (deg), tree share (WorldCover),
burnt the season before (burn labels in grid20), and ERA5-Land sanctuary weather on the first day.
Also saves each fire's pixel list to scratch (fire_pix.pkl) for the pass-level step.
Out: results/fire_cov.csv
"""
import pickle
import numpy as np, pandas as pd
from rasterio.features import rasterize
from affine import Affine
from h0_lib import RES, BF, SCRATCH, ROOT, X0, Y0, NR, NC, G20, layers, scars

L = layers(); S = scars()
F = pd.read_csv(f'{BF}/fires.csv', parse_dates=['date0'])
T = Affine(20, 0, X0, 0, -20, Y0)
pix = {}; rows = []
for r in F.itertuples():
    g = S[r.fire]; x0, y0, x1, y1 = g.bounds
    c0, c1 = int((x0 - X0) // 20) - 1, int((x1 - X0) // 20) + 2; r0, r1 = int((Y0 - y1) // 20) - 1, int((Y0 - y0) // 20) + 2
    m = rasterize([g], out_shape=(r1 - r0, c1 - c0), transform=T * Affine.translation(c0, r0), all_touched=False).astype(bool)
    rr, cc = np.where(m); rr += r0; cc += c0
    ok = (rr >= 0) & (rr < NR) & (cc >= 0) & (cc < NC); rr, cc = rr[ok], cc[ok]
    pix[r.fire] = (rr, cc)
    rec = dict(fire=r.fire, season=r.season, doy=r.date0.dayofyear, month=r.date0.month, n_pix=len(rr))
    for k in ['canopy', 'litter', 'grass', 'teak', 'slope', 'tree']:
        rec[k] = np.nanmean(L[k][rr, cc]) if len(rr) else np.nan
    pk = f'burn_start_{r.season - 1}'
    rec['burnt_last_season'] = (G20[pk][rr, cc] > 0).mean() if pk in G20.files and len(rr) else np.nan
    rows.append(rec)
C = pd.DataFrame(rows)
W = pd.read_csv(f'{ROOT}/ratapani/ee/era5land_daily.csv', parse_dates=['time']).set_index('time')
td, tt = W.dewpoint_temperature_2m - 273.15, W.temperature_2m - 273.15
W['rh'] = 100 * np.exp(17.625 * td / (243.04 + td)) / np.exp(17.625 * tt / (243.04 + tt))
W['tmax'] = W.temperature_2m_max - 273.15; W['wind'] = np.hypot(W.u_component_of_wind_10m, W.v_component_of_wind_10m)
W['rain30'] = W.total_precipitation_sum.rolling(30).sum() * 1000; W['soilw'] = W.volumetric_soil_water_layer_1
d0 = F.date0.dt.normalize()
for k in ['tmax', 'rh', 'wind', 'rain30', 'soilw']:
    C[k] = W[k].reindex(d0).values
C.to_csv(f'{RES}/fire_cov.csv', index=False)
pickle.dump(pix, open(f'{SCRATCH}/fire_pix.pkl', 'wb'))
print(C.describe().T.round(2))
