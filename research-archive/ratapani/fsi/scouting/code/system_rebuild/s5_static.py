"""Layer 2 (GIS): static square features for the union cells U, plus the UTM 43N scale check.
- Scale: UTM point scale factor k and meridian convergence at every square centre (pyproj Factors).
- Terrain (public AWS terrarium tiles z10, ~140 m, from r19_pool/dem_mp.npz): mean elevation, mean slope, ruggedness
  (SD of elevation in the 3x3 block), TPI (elevation minus 5 km mean), southness (mean cos of upslope azimuth weighted by
  slope; >0 = slopes face south).
- Land cover (Roy et al. 2015 VTM, 60 m, same CRS): shares of tree forest, scrub, grass, farmland, settlement, water;
  forest-type groups sal/teak/dry/moist/bamboo/degraded; farmland share within 2.5 and 5 km; forest share within 5 km;
  distance to the forest edge (inside forest, km) and to forest (outside).
- Roads (Overture 2026-09 segments): road length per square (major = motorway..tertiary; minor = residential,
  unclassified, track, path...), distance to a major road and to any road/track.
- Settlements (Overture division points: locality/hamlet/neighbourhood): distance to nearest, count within 5 km;
  VTM settlement share within 5 km.
- Beat cover (mp_cells beat_frac) and its 5 km mean.
Output: scratch static.npz (one array per feature, aligned with U) and out/s5_scale_check.json."""
import json, numpy as np, pandas as pd
from scipy.ndimage import uniform_filter, distance_transform_edt
from pyproj import Transformer, Proj
import common as C, features as Fe

def bx(a, r): return uniform_filter(a.astype(np.float32), 2 * r + 1, mode='nearest')

if __name__ == '__main__':
    B = Fe.base(); U, ur, uc = B['U'], B['ur'], B['uc']
    x = C.X0 + (uc + .5) * C.S; y = C.Y1 - (ur + .5) * C.S
    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(x, y)
    fa = Proj('EPSG:32643').get_factors(lon, lat)
    k = np.asarray(fa.meridional_scale); conv = np.asarray(fa.meridian_convergence)
    sc = dict(k_min=float(k.min()), k_max=float(k.max()), k_median=float(np.median(k)), lon_range=(float(lon.min()), float(lon.max())),
              ground_side_m_at_kmax=float(500 / k.max()), ground_side_m_at_kmin=float(500 / k.min()), area_err_pct_max=float(100 * (k.max() ** 2 - 1)),
              area_err_pct_min=float(100 * (k.min() ** 2 - 1)), convergence_deg_range=(float(conv.min()), float(conv.max())))
    json.dump(sc, open(C.OUT + 's5_scale_check.json', 'w'), indent=1); print(sc, flush=True)
    F = {}
    # terrain
    D = np.load(C.SC + '../r19_pool/dem_mp.npz'); E = D['elev']; SL = D['slope']; UP = D['upaz']; n = 256 * 2 ** 10
    i, j = np.mgrid[0:E.shape[0], 0:E.shape[1]]
    plon = (j + .5 + 256 * int(D['x0'])) / n * 360 - 180
    plat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (i + .5 + 256 * int(D['y0'])) / n))))
    px, py = C.TF.transform(plon.ravel(), plat.ravel())
    pc_ = np.floor((px - C.X0) / C.S).astype(int); pr_ = np.floor((C.Y1 - py) / C.S).astype(int)
    ok = (pc_ >= 0) & (pc_ < C.W) & (pr_ >= 0) & (pr_ < C.H) & np.isfinite(E.ravel()); fl = pr_[ok] * C.W + pc_[ok]
    cnt = np.bincount(fl, minlength=C.H * C.W).astype(np.float32)
    def agg(a): return (np.bincount(fl, weights=a.ravel()[ok], minlength=C.H * C.W) / np.maximum(cnt, 1)).reshape(C.H, C.W)
    el = agg(E); el2 = agg(E.astype(np.float64) ** 2); sl = agg(SL)
    sw = agg(np.cos(np.radians(UP)) * np.sin(np.radians(SL)))
    el[cnt.reshape(C.H, C.W) == 0] = np.nan
    m3 = bx(np.nan_to_num(el), 1); m3s = bx(np.nan_to_num(el) ** 2, 1)
    F['elev'] = el[ur, uc]; F['slope'] = sl[ur, uc]; F['rugged'] = np.sqrt(np.maximum(m3s - m3 ** 2, 0))[ur, uc]
    F['rough_in'] = np.sqrt(np.maximum(el2 - el ** 2, 0))[ur, uc]
    F['tpi5'] = (el - bx(np.nan_to_num(el), 5))[ur, uc]; F['south'] = sw[ur, uc]
    del i, j, plon, plat, px, py, pc_, pr_
    print('terrain done', flush=True)
    # VTM land cover
    import rasterio
    from rasterio.windows import from_bounds
    r = rasterio.open(C.SC + '../r14_types_data/vtm.tif')
    win = from_bounds(C.X0, C.Y1 - C.H * C.S, C.X0 + C.W * C.S, C.Y1, r.transform).round_offsets().round_lengths()
    T = r.window_transform(win)
    grp = np.zeros(256, np.int8)  # 1 tree forest, 2 scrub, 3 grass, 4 farm, 5 settlement, 6 water, 7 barren, 0 none
    grp[11:116] = 1; grp[120:135] = 2; grp[135:149] = 3; grp[150:164] = 1; grp[170] = 4; grp[200] = 5; grp[190:192] = 6; grp[180:182] = 7
    typ = np.zeros(256, np.int8)  # 1 sal 2 teak 3 dry mixed 4 moist mixed 5 bamboo 6 degraded
    for c_, t_ in ((24, 1), (27, 1), (36, 1), (25, 2), (28, 2), (37, 2), (26, 3), (23, 4), (30, 5), (40, 5), (106, 6)): typ[c_] = t_
    LCN = (('forest', grp, 1), ('scrub', grp, 2), ('grass', grp, 3), ('farm', grp, 4), ('settle', grp, 5), ('water', grp, 6),
           ('sal', typ, 1), ('teak', typ, 2), ('drymix', typ, 3), ('moistmix', typ, 4), ('bamboo', typ, 5), ('degraded', typ, 6))
    acc = {nm: np.zeros(C.H * C.W, np.float32) for nm, _, _ in LCN}; tot = np.zeros(C.H * C.W, np.float32)
    cols = np.floor((T.c + (np.arange(int(win.width)) + .5) * T.a - C.X0) / C.S).astype(np.int32); okc = (cols >= 0) & (cols < C.W)
    for r0 in range(0, int(win.height), 800):
        hh = min(800, int(win.height) - r0)
        A = r.read(1, window=rasterio.windows.Window(win.col_off, win.row_off + r0, win.width, hh))
        rows = np.floor((C.Y1 - (T.f + (r0 + np.arange(hh) + .5) * T.e)) / C.S).astype(np.int32)
        m = ((rows >= 0) & (rows < C.H))[:, None] & okc[None, :] & (A > 0)
        fl = (rows[:, None] * C.W + cols[None, :])[m]; a = A[m]
        tot += np.bincount(fl, minlength=C.H * C.W)
        for nm, lut, g in LCN: acc[nm] += np.bincount(fl, weights=(lut[a] == g), minlength=C.H * C.W)
    sh = {nm: (acc[nm] / np.maximum(tot, 1)).reshape(C.H, C.W) for nm in acc}
    for nm, a in sh.items(): F['lc_' + nm] = a[ur, uc]
    F['farm_2k5'] = bx(sh['farm'], 2)[ur, uc]; F['farm_5k'] = bx(sh['farm'], 5)[ur, uc]; F['forest_5k'] = bx(sh['forest'], 5)[ur, uc]
    F['settle_5k'] = bx(sh['settle'], 5)[ur, uc]
    fm = (sh['forest'] + sh['scrub']) >= 0.5
    F['d_edge_in'] = (distance_transform_edt(fm) * 0.5)[ur, uc]; F['d_forest_out'] = (distance_transform_edt(~fm) * 0.5)[ur, uc]
    print('land cover done', flush=True)
    # roads
    import pyarrow.parquet as pq, shapely
    t = pq.read_table(C.SC + '../r15_firms_nd/roads_mp.parquet'); cl = t.column('class').to_numpy(zero_copy_only=False)
    geo = shapely.from_wkb(t.column('geometry').to_numpy(zero_copy_only=False))
    major = np.isin(cl, ['motorway', 'trunk', 'primary', 'secondary', 'tertiary'])
    Lmaj = np.zeros(C.H * C.W, np.float32); Lall = np.zeros(C.H * C.W, np.float32)
    for a0 in range(0, len(geo), 300000):
        g = geo[a0:a0 + 300000]; mj = major[a0:a0 + 300000]
        segs = shapely.segmentize(g, 0.0015)   # ~150 m vertices
        coords, idx = shapely.get_coordinates(segs, return_index=True)
        X_, Y_ = C.TF.transform(coords[:, 0], coords[:, 1])
        cc = np.floor((X_ - C.X0) / C.S).astype(int); rr = np.floor((C.Y1 - Y_) / C.S).astype(int)
        dl = np.r_[np.hypot(np.diff(X_), np.diff(Y_)), 0]; same = np.r_[idx[1:] == idx[:-1], False]; dl = np.where(same, dl, 0)
        ok = (cc >= 0) & (cc < C.W) & (rr >= 0) & (rr < C.H) & (dl < 1000)
        f = rr[ok] * C.W + cc[ok]
        np.add.at(Lall, f, dl[ok]); np.add.at(Lmaj, f, dl[ok] * mj[idx[ok]])
    Lall = Lall.reshape(C.H, C.W) / 1000; Lmaj = Lmaj.reshape(C.H, C.W) / 1000
    F['road_km'] = Lall[ur, uc]; F['major_km'] = Lmaj[ur, uc]; F['road_km_5k'] = bx(Lall, 5)[ur, uc]
    F['d_major'] = (distance_transform_edt(Lmaj < 0.05) * 0.5)[ur, uc]; F['d_road'] = (distance_transform_edt(Lall < 0.05) * 0.5)[ur, uc]
    print('roads done', flush=True)
    # settlements
    try:
        pl = pd.read_parquet(C.SC + 'ov/places_mp.parquet'); print(pl.subtype.value_counts().to_dict(), pl['class'].value_counts().to_dict())
        pl = pl[pl.subtype.isin(['locality', 'neighborhood', 'microhood', 'macrohood', 'localadmin'])]
        X_, Y_ = C.TF.transform(pl.lon.values, pl.lat.values); cc = np.floor((X_ - C.X0) / C.S).astype(int); rr = np.floor((C.Y1 - Y_) / C.S).astype(int)
        ok = (cc >= 0) & (cc < C.W) & (rr >= 0) & (rr < C.H)
        Pm = np.zeros((C.H, C.W), np.float32); np.add.at(Pm, (rr[ok], cc[ok]), 1)
        F['d_village'] = (distance_transform_edt(Pm == 0) * 0.5)[ur, uc]; F['villages_5k'] = (bx(Pm, 5) * 121)[ur, uc]
    except FileNotFoundError:
        print('no Overture places')
    cells = pd.read_parquet(C.P + 'ratapani/mp_grid/mp_cells.parquet'); bf = np.zeros((C.H, C.W), np.float32); bf[cells.row, cells.col] = cells.beat_frac
    F['beat_frac'] = bf[ur, uc]; F['beat_5k'] = bx(bf, 5)[ur, uc]
    np.savez(C.SC + 'static.npz', **{k_: np.asarray(v_, np.float32) for k_, v_ in F.items()})
    print(pd.DataFrame(F).describe().T.to_string())
