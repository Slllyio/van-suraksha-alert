"""FSI strata map rebuilt on FSI's own inputs from the Van Agni portal WCS (FCM 2023 'fcm_9th_cycle', FTM 2021).
Portal serves rendered RGB, decoded by colour: FCM dark green=VDF, green=MDF, yellow=OF, red=scrub(inferred), blue=water.
FTM: 90% of Ratapani is one class (orange), read as tropical dry deciduous (inferred; portal legend is empty).
Stratum value = mean of the v2 continuous peak map within each FSI canopy x slope stratum."""
import numpy as np, rasterio, json
from rasterio.transform import Affine
D = '/tmp/claude-0/fuel/'; OUT = '/mnt/project-files/fuel-map/ratapani/'
S = np.load(D + 'static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); ins = S['inside'].astype(bool); slope = S['slope']
F = np.load(D + 'fsi_fcm_ftm10.npz'); fcm, ftm = F['fcm'], F['ftm']
with rasterio.open(OUT + 'fuel_continuous_peak_10m.tif') as s: p = s.read(1); peak = np.where(p == 65535, np.nan, p / 10.)
def w8(path, a, tags):
    with rasterio.open(path, 'w', driver='GTiff', width=W, height=H, count=1, dtype='uint8', crs='EPSG:32643', transform=TR, nodata=0, compress='deflate', tiled=True) as d:
        d.write(np.where(ins, a, 0).astype('uint8'), 1); d.update_tags(**tags)
w8(OUT + 'fsi_fcm_2023_10m.tif', fcm, dict(codes='1 VDF, 2 MDF, 3 OF, 4 scrub (inferred from red), 5 water, 0 non-forest', source='FSI Van Agni WCS fcm_9th_cycle, ~24 m, nearest'))
w8(OUT + 'fsi_ftm_2021_10m.tif', ftm, dict(codes='1 orange class (read as tropical dry deciduous, inferred), 2 grey, 3 purple, 5 water, 0 none', source='FSI Van Agni WCS FTM_2021'))
forest = ins & np.isin(fcm, [1, 2, 3, 4])
ccls = np.select([fcm == 1, fcm == 2, fcm == 3], [3, 2, 1], 0)          # 0 scrub,1 OF,2 MDF,3 VDF (same order as build_v2)
code = ccls * 4 + np.digitize(slope, [10, 20, 30]); tab = np.full(16, np.nan)
for c in range(16):
    k = forest & (code == c) & np.isfinite(peak)
    if k.sum() > 100: tab[c] = np.nanmean(peak[k])
fsi = np.where(forest, tab[code], np.nan)
q = np.where(np.isfinite(fsi), np.round(fsi * 10), 65535).astype('uint16')
with rasterio.open(OUT + 'fuel_fsi_strata_fsicanopy_10m.tif', 'w', driver='GTiff', width=W, height=H, count=1, dtype='uint16', crs='EPSG:32643', transform=TR, nodata=65535, compress='deflate', predictor=2, tiled=True) as d:
    d.write(q, 1); d.update_tags(scale_factor='0.1', units='g/ft2 (value x 0.1)', note='FSI strata on FSI FCM 2023 canopy classes x SRTM slope; value = stratum mean of v2 continuous map')
x = fsi[np.isfinite(fsi)]
rep = dict(table_gft2_rows_scrub_open_mdf_vdf_cols_slope=np.round(tab.reshape(4, 4), 1).tolist(), mean_gft2=round(float(x.mean()), 1),
           low_mod_high_vhigh=np.round(np.bincount(np.digitize(x, [20, 40, 60]), minlength=4) / len(x), 3).tolist(), forest_pixels=int(forest.sum()))
json.dump(rep, open(OUT + 'fsi_inputs_summary.json', 'w'), indent=1); print(rep)
