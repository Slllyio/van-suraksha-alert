"""Machine-learning tables of fire spread rate and direction (Akkshay 16 Oct 19:49Z / 19:50Z: "each fire in a row, rate and
direction of spread, terrain and fuel, and every field we have: FRP, brightness, number of detections").

Fires: every fire from b1 with >= 2 VIIRS looks (the 146 big fires carry big = 1). All bearings are compass degrees
(0 = north, 90 = east), measured from where the fire was to where the new burning appeared.

Three tables (results/ml/):
  fires_ml.csv     one row per fire: size, detections and every alert field summarised, spread rate, spread direction,
                   terrain, fuel, canopy, burn history, land cover, people, weather, and terrain/fuel ahead vs behind
  steps_ml.csv     one row per growth step (look k -> new burning at look k+1): rate, bearing, the look's alert fields,
                   local terrain/fuel/weather, alignment with wind and upslope
  sectors_ml.csv   one row per step x 8 compass sectors: what lies in each sector 300-1500 m out, and whether the new
                   burning went there (target). This is the honest set-up for "does terrain or fuel decide direction".
Column guide: results/ml/COLUMNS.md (written by this script).
"""
import json, os, pickle
import numpy as np, pandas as pd, rasterio
from scipy.spatial import cKDTree
from rasterio.features import rasterize
from rasterio.transform import from_origin
ROOT = '/mnt/project-files'; R = f'{ROOT}/research/big-fires/results'; OUT = f'{R}/ml'; os.makedirs(OUT, exist_ok=True)
F = pd.read_csv(f'{R}/fires.csv'); A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t']); S = pickle.load(open(f'{R}/fire_scars.pkl' if os.path.exists(f'{R}/fire_scars.pkl') else '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/fire_scars.pkl', 'rb'))
F['big'] = ((F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge).astype(int)
Sh = pd.read_csv(f'{R}/fire_shape.csv').set_index('fire')
IST = pd.Timedelta(hours=5, minutes=30)

# ---- every alert field (VIIRS from b6c alert_fields.csv incl. two-channel split; MODIS from raw files)
AF = pd.read_csv(f'{R}/alert_fields.csv' if os.path.exists(f'{R}/alert_fields.csv') else '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/alert_fields.csv', parse_dates=['t'])
key = lambda d: d.latitude.round(5).astype(str) + '_' + d.longitude.round(5).astype(str) + '_' + d.t.astype(str) + '_' + d.sat
AF['k'] = key(AF); A['k'] = key(A)
A = A.merge(AF.drop(columns=['latitude', 'longitude', 't', 'sat', 'frp', 'scan', 'track', 'daynight']).drop_duplicates('k'), on='k', how='left')
import glob
M = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/alerts/modis_*.csv')], ignore_index=True).dropna(subset=['acq_time'])
M['t'] = pd.to_datetime(M.acq_date) + pd.to_timedelta(M.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(M.acq_time.astype(int) % 100, 'min')
M['sat'] = 'modis'; M['k'] = key(M)
A = A.merge(M[['k', 'brightness', 'bright_t31', 'satellite']].rename(columns={'satellite': 'modis_sat', 'confidence': 'modis_conf'}).drop_duplicates('k'), on='k', how='left')
A = A.merge(M[['k', 'confidence']].rename(columns={'confidence': 'modis_conf'}).drop_duplicates('k'), on='k', how='left')
A['confidence'] = A.confidence.astype(object)
V = A[A.sat != 'modis'].copy()

# ---- rasters
G = np.load(f'{ROOT}/ratapani/spread/data_shared/grid20.npz'); TR20 = G['transform']
def s20(arr, x, y):
    c = ((np.asarray(x) - TR20[2]) / TR20[0]).astype(int); r = ((np.asarray(y) - TR20[5]) / TR20[4]).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1]); o = np.full(len(c), np.nan, np.float32); o[ok] = arr[r[ok], c[ok]]; return o
ELEV, SLOPE, UPAZ, WC = G['elev'].astype(np.float32), G['slope'].astype(np.float32), G['upslope_az'].astype(np.float32), G['wc']
BURN = {y: G[f'burn_start_{y}'] for y in range(2017, 2027)}
R10 = {}
for name, f in [('canopy', 'canopy_cover_10m.tif'), ('teak', 'teak_probability_10m.tif'), ('litter_v3', 'v3/litter_potential_central_10m.tif'),
                ('grass_v3', 'v3/grass_potential_central_10m.tif'), ('fuel_total_v3', 'v3/fuel_total_potential_central_10m.tif'),
                ('burn_count', 'v3/burn_count_10m.tif')]:
    with rasterio.open(f'{ROOT}/fuel-map/ratapani/{f}') as r:
        a = r.read(1).astype(np.float32)
        if r.nodata is not None: a[a == r.nodata] = np.nan
        a *= {'canopy': 0.1, 'litter_v3': 0.01, 'grass_v3': 0.01, 'fuel_total_v3': 0.01}.get(name, 1.0)   # canopy %, fuel t/ha
        R10[name] = (a, r.transform)
def s10(name, x, y):
    a, tr = R10[name]; c = ((np.asarray(x) - tr[2]) / tr[0]).astype(int); r = ((np.asarray(y) - tr[5]) / tr[4]).astype(int)
    ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1]); o = np.full(len(c), np.nan, np.float32); o[ok] = a[r[ok], c[ok]]; return o
grid = json.load(open(f'{ROOT}/ratapani/grid_500m.geojson'))
gc = pd.DataFrame([dict(cell_id=g['properties']['cell_id'], x=g['properties']['x0'] + 250, y=g['properties']['y0'] + 250) for g in grid['features']])
gc = gc.merge(pd.read_csv(f'{ROOT}/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')[['cell_id', 'd_ob', 'nham4']], on='cell_id', how='left') \
       .merge(pd.read_csv(f'{ROOT}/ratapani/ee/proximity.csv'), on='cell_id', how='left')
gtree = cKDTree(gc[['x', 'y']].values)
def cell(x, y, col):
    d, i = gtree.query(np.c_[np.atleast_1d(x), np.atleast_1d(y)]); v = gc[col].values[i].astype(float); v[d > 400] = np.nan; return v
E5 = pd.read_csv(f'{ROOT}/ratapani/ee/era5land_daily.csv', parse_dates=['time']).set_index('time')
E5['rh'] = 100 * np.exp(17.625 * (E5.dewpoint_temperature_2m - 273.15) / (E5.dewpoint_temperature_2m - 30.11)) / \
           np.exp(17.625 * (E5.temperature_2m - 273.15) / (E5.temperature_2m - 30.11))
E5['rain7'] = E5.total_precipitation_sum.rolling(7).sum() * 1000; E5['rain30'] = E5.total_precipitation_sum.rolling(30).sum() * 1000
def wx(t):
    d = pd.Timestamp(t).normalize()
    if d not in E5.index: return {}
    e = E5.loc[d]; u, v = e.u_component_of_wind_10m, e.v_component_of_wind_10m
    return dict(wx_tmax_c=e.temperature_2m_max - 273.15, wx_tmean_c=e.temperature_2m - 273.15, wx_rh=e.rh, wx_wind_ms=np.hypot(u, v),
                wx_wind_to_deg=np.degrees(np.arctan2(u, v)) % 360, wx_soil_water=e.volumetric_soil_water_layer_1, wx_rain7_mm=e.rain7, wx_rain30_mm=e.rain30)

def comp(dx, dy): return np.degrees(np.arctan2(dx, dy)) % 360
def ang(a, b): return np.cos(np.radians(a - b))

def ring_pts(cx, cy, bearing, r0=300, r1=1500, half=22.5):
    rr = np.linspace(r0, r1, 6); aa = np.radians(bearing + np.linspace(-half, half, 5))
    R_, A_ = np.meshgrid(rr, aa); return cx + R_.ravel() * np.sin(A_.ravel()), cy + R_.ravel() * np.cos(A_.ravel())

def sector_feats(cx, cy, b, year, doy, burned_pts):
    x, y = ring_pts(cx, cy, b)
    e0 = s20(ELEV, [cx], [cy])[0]
    bs = s20(BURN[year].astype(np.float32), x, y) if year in BURN else np.full(len(x), np.nan)
    f = dict(elev_diff=np.nanmean(s20(ELEV, x, y)) - e0, slope=np.nanmean(s20(SLOPE, x, y)),
             canopy=np.nanmean(s10('canopy', x, y)), teak=np.nanmean(s10('teak', x, y)), litter_v3=np.nanmean(s10('litter_v3', x, y)),
             grass_v3=np.nanmean(s10('grass_v3', x, y)), fuel_total_v3=np.nanmean(s10('fuel_total_v3', x, y)),
             burn_count=np.nanmean(s10('burn_count', x, y)),
             burn_prior=np.nanmean(np.sum([s20((BURN[y_] > 0).astype(np.float32), x, y) for y_ in range(2017, year)], axis=0)) if year > 2017 else 0.0, wc_tree=np.nanmean(s20(WC, x, y) == 10), wc_open=np.nanmean(np.isin(s20(WC, x, y), [20, 30])),
             wc_nonfuel=np.nanmean(np.isin(s20(WC, x, y), [40, 50, 60, 80])),
             burned_this_season_before=np.nanmean((bs > 0) & (bs < doy - 1)),
             own_fire_already=np.mean(cKDTree(burned_pts).query(np.c_[x, y])[0] < 400) if len(burned_pts) else 0.0,
             d_building=np.nanmean(cell(x, y, 'd_ob')), d_road=np.nanmean(cell(x, y, 'dist_road')))
    return f

def look_stats(g, pre):
    vi = g[g.sat != 'modis']
    o = {f'{pre}n_det': len(g), f'{pre}n_viirs': len(vi), f'{pre}n_modis': int((g.sat == 'modis').sum()),
         f'{pre}frp_sum': g.frp.sum(), f'{pre}frp_mean': g.frp.mean(), f'{pre}frp_max': g.frp.max(),
         f'{pre}ti4_mean': vi.bright_ti4.mean(), f'{pre}ti4_max': vi.bright_ti4.max(), f'{pre}ti5_mean': vi.bright_ti5.mean(),
         f'{pre}ti4_minus_ti5': (vi.bright_ti4 - vi.bright_ti5).mean(), f'{pre}conf_high_share': (vi.confidence == 'h').mean() if len(vi) else np.nan,
         f'{pre}conf_low_share': (vi.confidence == 'l').mean() if len(vi) else np.nan, f'{pre}pix_km2_mean': (g.scan * g.track).mean(),
         f'{pre}dozier_p_median': vi.dz_p.median(), f'{pre}dozier_Tf_median': vi.dz_Tf.median(), f'{pre}frp_area_m2_sum': vi.frp_area_m2.sum()}
    return o

fires, steps, sectors = [], [], []
SEL = F[F.n_looks >= 2]
for _, f in SEL.iterrows():
    a = A[A.fire == f.fire].sort_values('t'); v = a[a.sat != 'modis']
    order = list(v.groupby('look').t.median().sort_values().index)
    if len(order) < 2: continue
    poly = S[f.fire]; year = int(pd.Timestamp(f.date0).year)
    first = v[v.look == order[0]]; fx, fy = first.x.mean(), first.y.mean()
    # growth steps
    st = []
    for k in range(1, len(order)):
        prev = v[v.look.isin(order[:k])]; cur = v[v.look == order[k]]
        dn = cKDTree(prev[['x', 'y']].values).query(cur[['x', 'y']].values)[0]; new = cur[dn > 400]
        tprev, tcur = prev.t.max(), cur.t.min(); dt = (tcur - tprev).total_seconds() / 3600
        rec = dict(fire=f.fire, big=f.big, season=year, k=k, t_utc=tcur, t_ist=tcur + IST, hour_ist=(tcur + IST).hour, night=int(cur.daynight.iloc[0] == 'N'),
                   gap_h=dt, n_new_det=len(new), new_ground=int(len(new) > 0))
        if len(new):
            c0 = prev[['x', 'y']].values.mean(0); lastp = prev[prev.look == order[k - 1]][['x', 'y']].values.mean(0)
            dx, dy = new.x.mean() - c0[0], new.y.mean() - c0[1]
            dist_edge = dn[dn > 400].mean()
            rec.update(bearing_deg=comp(dx, dy), move_m=np.hypot(dx, dy), advance_beyond_m=dist_edge, rate_m_per_h=dist_edge / dt if dt > 0 else np.nan,
                       x0=c0[0], y0=c0[1])
        rec.update(look_stats(cur, 'look_')); rec.update(look_stats(prev[prev.look == order[k - 1]], 'prevlook_'))
        rec.update(wx(tcur))
        st.append(rec)
    St = pd.DataFrame(st)
    St['prev_bearing_deg'] = St.bearing_deg.shift().ffill() if 'bearing_deg' in St else np.nan
    for i, r in St.iterrows():
        if 'bearing_deg' not in St or not np.isfinite(r.get('bearing_deg', np.nan)): continue
        x0, y0 = r.x0, r.y0; doy = pd.Timestamp(r.t_utc).dayofyear
        up = s20(UPAZ, [x0], [y0])[0]
        St.loc[i, 'slope_here'] = s20(SLOPE, [x0], [y0])[0]; St.loc[i, 'elev_here'] = s20(ELEV, [x0], [y0])[0]
        St.loc[i, 'upslope_az_here'] = up; St.loc[i, 'cos_upslope'] = ang(r.bearing_deg, up)
        St.loc[i, 'cos_wind'] = ang(r.bearing_deg, r.wx_wind_to_deg) if 'wx_wind_to_deg' in r and np.isfinite(r.wx_wind_to_deg) else np.nan
        St.loc[i, 'cos_prev'] = ang(r.bearing_deg, r.prev_bearing_deg) if np.isfinite(r.prev_bearing_deg) else np.nan
        burned = v[v.t < r.t_utc][['x', 'y']].values
        fa = sector_feats(x0, y0, r.bearing_deg, year, doy, burned); fb = sector_feats(x0, y0, (r.bearing_deg + 180) % 360, year, doy, burned)
        for kk in fa: St.loc[i, f'ahead_minus_behind_{kk}'] = fa[kk] - fb[kk]
        # 8 sectors
        cur = v[v.look == order[int(r.k)]]; prevxy = v[v.look.isin(order[:int(r.k)])][['x', 'y']].values
        dn = cKDTree(prevxy).query(cur[['x', 'y']].values)[0]; new = cur[dn > 400]
        nb = comp(new.x.values - x0, new.y.values - y0); nsec = ((nb + 22.5) // 45 % 8).astype(int)
        for s in range(8):
            b = s * 45.0; sf = sector_feats(x0, y0, b, year, doy, burned)
            sectors.append(dict(fire=f.fire, big=f.big, season=year, k=int(r.k), sector=s, sector_bearing=b, gap_h=r.gap_h, night=r.night,
                                target_new_burning=int((nsec == s).any()), target_share=float((nsec == s).mean()),
                                target_main=int(s == int(((r.bearing_deg + 22.5) // 45) % 8)),
                                cos_prev=ang(b, r.prev_bearing_deg) if np.isfinite(r.prev_bearing_deg) else np.nan,
                                cos_from_first=ang(b, comp(x0 - fx, y0 - fy)) if np.hypot(x0 - fx, y0 - fy) > 300 else np.nan,
                                cos_upslope=ang(b, up), cos_wind=ang(b, r.wx_wind_to_deg) if np.isfinite(r.get('wx_wind_to_deg', np.nan)) else np.nan,
                                wind_ms=r.get('wx_wind_ms', np.nan), **sf))
    steps.append(St)
    # fire row
    gs = St.dropna(subset=['bearing_deg']) if 'bearing_deg' in St else St.iloc[:0]
    b = np.radians(gs.bearing_deg.values) if len(gs) else np.array([])
    w = gs.advance_beyond_m.values if len(gs) else np.array([])
    mb = comp((np.sin(b) * w).sum(), (np.cos(b) * w).sum()) if len(b) else np.nan
    Rc = np.hypot(np.sin(b).mean(), np.cos(b).mean()) if len(b) else np.nan
    X, Y = None, None
    x0b, y0b, x1b, y1b = poly.bounds; res = 30; tr = from_origin(x0b, y1b, res, res)
    m = rasterize([(poly, 1)], out_shape=(int((y1b - y0b) / res) + 1, int((x1b - x0b) / res) + 1), transform=tr).astype(bool)
    rr_, cc_ = np.where(m); X = tr[2] + (cc_ + .5) * res; Y = tr[5] - (rr_ + .5) * res
    if len(X) > 4000: kk_ = np.random.default_rng(0).choice(len(X), 4000, replace=False); X, Y = X[kk_], Y[kk_]
    el = s20(ELEV, X, Y); wc = s20(WC, X, Y); sl = s20(SLOPE, X, Y)
    row = dict(fire=f.fire, big=f.big, season=year, date_start=f.date0, date_end=f.date1, doy_start=pd.Timestamp(f.date0).dayofyear,
               first_look_ist=(v.t.min() + IST), first_look_hour_ist=(v.t.min() + IST).hour, first_look_night=int(first.daynight.iloc[0] == 'N'),
               x_utm43n=np.round(f.cx, 1), y_utm43n=np.round(f.cy, 1), scar_area_ha=f.area_ha, n_events=f.n_events, still_at_edge=int(f.still_at_edge),
               duration_h=(v.t.max() - v.t.min()).total_seconds() / 3600, n_looks=len(order), n_det_viirs=len(v), n_det_modis=int((a.sat == 'modis').sum()),
               n_snpp=int((a.sat == 'viirs-snpp').sum()), n_noaa20=int((a.sat == 'viirs-jpss1').sum()), n_noaa21=int((a.sat == 'viirs-noaa21').sum()),
               night_det_share=(v.daynight == 'N').mean(), modis_brightness_mean=a.brightness.mean(), modis_t31_mean=a.bright_t31.mean())
    row.update(look_stats(a, 'all_')); row.update(look_stats(first, 'first_'))
    row.update(dict(frp_per_ha=a.frp.sum() / f.area_ha,
                    rate_median_m_per_h=gs.rate_m_per_h.median() if len(gs) else np.nan, rate_max_m_per_h=gs.rate_m_per_h.max() if len(gs) else np.nan,
                    advance_median_m=gs.advance_beyond_m.median() if len(gs) else np.nan, n_growth_steps=len(gs),
                    growth_ha_per_h=f.area_ha / max((v.t.max() - v.t.min()).total_seconds() / 3600, 1) if len(order) > 1 else np.nan,
                    spread_dir_deg=mb, spread_dir_consistency=Rc,
                    dir_first_to_scar_centre_deg=comp(f.cx - fx, f.cy - fy), dist_first_to_scar_centre_m=np.hypot(f.cx - fx, f.cy - fy),
                    max_reach_from_first_m=np.hypot(v.x - fx, v.y - fy).max()))
    if f.fire in Sh.index:
        s_ = Sh.loc[f.fire]; row.update(scar_length_m=s_.length_m, scar_elongation=s_.elong, scar_axis_deg=s_.ax_az, first_pos_along_axis=s_.pos_first,
                                        scar_share_behind_first=s_.behind_first)
    row.update(dict(elev_mean=np.nanmean(el), elev_relief=np.nanpercentile(el, 95) - np.nanpercentile(el, 5), slope_mean=np.nanmean(sl),
                    slope_share_gt5=np.nanmean(sl > 5), canopy_mean=np.nanmean(s10('canopy', X, Y)), teak_mean=np.nanmean(s10('teak', X, Y)),
                    litter_v3_mean=np.nanmean(s10('litter_v3', X, Y)), grass_v3_mean=np.nanmean(s10('grass_v3', X, Y)),
                    fuel_total_v3_mean=np.nanmean(s10('fuel_total_v3', X, Y)), burn_count_mean=np.nanmean(s10('burn_count', X, Y)), burn_prior_mean=np.nanmean(np.sum([s20((BURN[y_] > 0).astype(np.float32), X, Y) for y_ in range(2017, year)], axis=0)) if year > 2017 else 0.0,
                    wc_tree=np.nanmean(wc == 10), wc_shrub=np.nanmean(wc == 20), wc_grass=np.nanmean(wc == 30), wc_crop=np.nanmean(wc == 40),
                    upslope_az_first=s20(UPAZ, [fx], [fy])[0], slope_first=s20(SLOPE, [fx], [fy])[0],
                    d_building_first_m=cell(fx, fy, 'd_ob')[0], hamlets_4km_first=cell(fx, fy, 'nham4')[0], d_road_first_m=cell(fx, fy, 'dist_road')[0],
                    d_village_first_m=cell(fx, fy, 'dist_village')[0], depth_in_forest_first_m=cell(fx, fy, 'depth_in_forest')[0]))
    row.update(wx(v.t.min()))
    if np.isfinite(mb):
        row['cos_dir_upslope'] = ang(mb, row['upslope_az_first'])
        row['cos_dir_wind'] = ang(mb, row['wx_wind_to_deg']) if 'wx_wind_to_deg' in row else np.nan
        burned = first[['x', 'y']].values; doy = pd.Timestamp(f.date0).dayofyear
        fa = sector_feats(fx, fy, mb, year, doy, burned); fb = sector_feats(fx, fy, (mb + 180) % 360, year, doy, burned)
        for kk in fa: row[f'ahead_minus_behind_{kk}'] = fa[kk] - fb[kk]
    fires.append(row)
FR = pd.DataFrame(fires)
import pyproj
FR['lon'], FR['lat'] = pyproj.Transformer.from_crs(32643, 4326, always_xy=True).transform(FR.x_utm43n.values, FR.y_utm43n.values)
FR['lon'], FR['lat'] = FR.lon.round(5), FR.lat.round(5); STs = pd.concat(steps, ignore_index=True); SE = pd.DataFrame(sectors)
STs = STs.drop(columns=[c for c in ['x0', 'y0'] if c in STs])
FR.to_csv(f'{OUT}/fires_ml.csv', index=False); STs.to_csv(f'{OUT}/steps_ml.csv', index=False); SE.to_csv(f'{OUT}/sectors_ml.csv', index=False)
print('fires', FR.shape, 'big', FR.big.sum(), '| steps', STs.shape, 'with new ground', STs.new_ground.sum(), '| sector rows', SE.shape)
