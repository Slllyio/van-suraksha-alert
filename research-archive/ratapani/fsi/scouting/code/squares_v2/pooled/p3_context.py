"""Step 3: context for every fire pair (FIRMS type 0) and, identically, for every static pair (type 2, the null).
Around the mid-point M of the two looks (R = 2 km), using every VIIRS detection of the same type as its own timed point:
  E = centroid of detections 2-48 h before look A (the fire's earlier position)  -> outward direction u = M - E
  F = centroid of detections 2-48 h after look B (where the fire went later)      -> later-growth direction g = F - E
      (g uses neither look A nor look B, so its noise is independent of the pair's displacement)
  age = hours since the first detection within 2 km in the previous 7 days.
Terrain at M (MP DEM, ~140 m, smoothed 300 m): slope, upslope azimuth. Wind: ERA5-Land hourly (on disk for the
Ratapani area only, 33 points): mean 10 m wind over [tA, tB] at the nearest point if within 15 km.
Ratapani cover class (fuel-map cover_phenology_10m) at M where inside its extent.
Out (scratch): ctx.parquet (pairs2 + context)."""
import os, sys
import numpy as np, pandas as pd, rasterio, pyproj
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p_dem
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
R = pd.read_parquet(f'{SC}/pairs2.parquet')
A = pd.read_parquet(f'{SC}/pts.parquet', columns=['sensor', 't', 'x', 'y', 'type', 'latitude'])
A = A[A.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21']) & A.type.isin([0, 2])].reset_index(drop=True)
def tocart(lat, lon): return (lon - 78.0) * 111320.0 * np.cos(np.radians(23.5)), (lat - 23.5) * 110574.0
R['mx'], R['my'] = tocart((R.latA + R.latB) / 2, (R.lonA + R.lonB) / 2)
R['ax'], R['ay'] = tocart(R.latA, R.lonA)
loc_scale = np.cos(np.radians((R.latA + R.latB) / 2)) / np.cos(np.radians(23.5))   # pseudo-x metres -> true east metres
tA = R.tA.values.astype('datetime64[s]').astype(np.int64); tB = R.tB.values.astype('datetime64[s]').astype(np.int64)
out = {k: np.full(len(R), np.nan) for k in ['nE', 'Ex', 'Ey', 'nF', 'Fx', 'Fy', 'age_h', 'nE_near']}
day = (tA // 86400).astype(np.int64)
for typ in (0, 2):
    P = A[A.type == typ]
    px, py = P.x.values, P.y.values; pt = P.t.values.astype('datetime64[s]').astype(np.int64)
    o = np.argsort(pt); px, py, pt = px[o], py[o], pt[o]
    for dd in np.unique(day[R.typ.values == typ]):
        sel = np.where((R.typ.values == typ) & (day == dd))[0]
        lo, hi = np.searchsorted(pt, [dd * 86400 - 3 * 86400 - 7 * 86400, dd * 86400 + 4 * 86400])
        if hi <= lo: continue
        qx, qy, qt = px[lo:hi], py[lo:hi], pt[lo:hi]
        tree = cKDTree(np.c_[qx, qy])
        nb = tree.query_ball_point(np.c_[R.mx.values[sel], R.my.values[sel]], 2000.0)
        for ii, k in enumerate(sel):
            j = np.asarray(nb[ii], int)
            if not len(j): continue
            tt = qt[j]
            e = j[(tt >= tA[k] - 48 * 3600) & (tt <= tA[k] - 2 * 3600)]
            f = j[(tt >= tB[k] + 2 * 3600) & (tt <= tB[k] + 48 * 3600)]
            a = tt[(tt >= tA[k] - 7 * 86400) & (tt < tA[k] - 600)]
            out['nE'][k] = len(e); out['nF'][k] = len(f)
            if len(e): out['Ex'][k] = qx[e].mean(); out['Ey'][k] = qy[e].mean()
            if len(f): out['Fx'][k] = qx[f].mean(); out['Fy'][k] = qy[f].mean()
            out['age_h'][k] = (tA[k] - a.min()) / 3600 if len(a) else 0.0
    print('type', typ, 'done', flush=True)
for k, v in out.items(): R[k] = v
# directions in true east/north metres
R['uE'] = (R.mx - R.Ex) * loc_scale; R['uN'] = R.my - R.Ey          # outward: earlier centroid -> mid-point
R['gE'] = (R.Fx - R.Ex) * loc_scale; R['gN'] = R.Fy - R.Ey          # later growth: earlier -> later centroid
R['u_len'] = np.hypot(R.uE, R.uN); R['g_len'] = np.hypot(R.gE, R.gN)
# terrain
e, s, u = p_dem.sample((R.latA + R.latB).values / 2, (R.lonA + R.lonB).values / 2)
R['elev'], R['slope'], R['upaz'] = e, s, u
# ERA5-Land wind (Ratapani area only)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
R['wE'] = np.nan; R['wN'] = np.nan
for season in range(2018, 2027):
    fn = f'/mnt/project-files/ratapani/ee/era5/era5land_hourly_{season}.csv'
    if not os.path.exists(fn): continue
    k = np.where((R.season == season) & R.latA.between(22.5, 23.4) & R.lonA.between(77.0, 78.4))[0]
    if not len(k): continue
    d = pd.read_csv(fn, usecols=['longitude', 'latitude', 'u_component_of_wind_10m', 'v_component_of_wind_10m', 'datetime_utc', 'point_id'], parse_dates=['datetime_utc'])
    pts = d.groupby('point_id')[['longitude', 'latitude']].first()
    ptree = cKDTree(np.column_stack(tocart(pts.latitude.values, pts.longitude.values)))
    W = {pid: g.set_index('datetime_utc')[['u_component_of_wind_10m', 'v_component_of_wind_10m']].sort_index() for pid, g in d.groupby('point_id')}
    dd, ii = ptree.query(np.c_[R.mx.values[k], R.my.values[k]])
    for kk, di, pi in zip(k, dd, ii):
        if di > 15000: continue
        w = W[pts.index[pi]].loc[R.tA.iloc[kk].floor('h'): R.tB.iloc[kk].ceil('h')]
        if len(w): R.iloc[kk, R.columns.get_loc('wE')] = w.u_component_of_wind_10m.mean(); R.iloc[kk, R.columns.get_loc('wN')] = w.v_component_of_wind_10m.mean()
    print('wind', season, int(np.isfinite(R.wE.values[k]).sum()), flush=True)
# Ratapani cover class
with rasterio.open('/mnt/project-files/fuel-map/ratapani/cover_phenology_10m.tif') as r:
    ux, uy = tp(((R.lonA + R.lonB) / 2).values, ((R.latA + R.latB) / 2).values)
    b = r.bounds; ins = (ux > b.left) & (ux < b.right) & (uy > b.bottom) & (uy < b.top)
    cv = np.zeros(len(R), np.int16)
    if ins.any(): cv[ins] = [v[0] for v in r.sample(zip(ux[ins], uy[ins]))]
    R['cover'] = cv
R.to_parquet(f'{SC}/ctx.parquet'); print(len(R), R.groupby('typ')[['nE', 'nF']].apply(lambda g: (g > 0).mean()).to_string())
