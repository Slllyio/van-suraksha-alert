"""Do open-grass pixels (cover class 4) burn earlier in the season than tree pixels in Ratapani?
Uses cover_phenology_10m.tif (resampled to 20 m by mode) and scar outlines v2 (2026-10-16), FIRMS events.
Also: monthly NDVI/NDMI/NDTI by class (greenness/curing proxy), grazing proxy (distance to buildings),
and a scar-detection-bias check by grass share around alert points. Read-only on /mnt/project-files."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio, sys
from rasterio.features import rasterize
from rasterio.enums import Resampling
from pyproj import Transformer
R = '/mnt/project-files/fuel-map/ratapani/'
V2 = '/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/'
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
src = rasterio.open(R + 'cover_phenology_10m.tif'); H, W = src.height // 2, src.width // 2
T = src.transform * src.transform.scale(2, 2)
cls = src.read(1, out_shape=(H, W), resampling=Resampling.mode)
NAMES = {1: 'deciduous tree', 2: 'green tree', 4: 'open grass/low', 5: 'sparse/bare'}
forest = np.isin(cls, [1, 2, 4, 5])
print('class shares of forest mask at 20 m:', {NAMES[k]: round(100 * (cls[forest] == k).mean(), 1) for k in NAMES})

g = gpd.read_file(V2 + 'firms_event_scars.geojson', columns=['event_id', 'date', 'scar_ha', 'status']).to_crs(src.crs)
g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
g['date'] = pd.to_datetime(g.date)
g['season'] = np.where(g.date.dt.month >= 8, g.date.dt.year + 1, g.date.dt.year)
g['dos'] = (g.date - pd.to_datetime((g.season - 1).astype(str) + '-11-01')).dt.days  # day of season from 1 Nov
print('events', len(g), 'seasons', sorted(g.season.unique()))
# first-burn day-of-season per pixel per season
FB = {}
for s, gs in g.groupby('season'):
    gs = gs.sort_values('dos', ascending=False)  # earliest last -> wins
    FB[s] = rasterize(((geom, int(d)) for geom, d in zip(gs.geometry, gs.dos)), out_shape=(H, W), transform=T, fill=-1, dtype='int16')
seasons = [s for s in sorted(FB) if 2017 <= s <= 2026]
# windows in day-of-season (1 Nov = 0): Nov-Dec, Jan, 1-14 Feb, 15-28 Feb, Mar, Apr, May-Jun
WIN = [('Nov-Dec', 0, 61), ('Jan', 61, 92), ('1-14 Feb', 92, 106), ('15 Feb-end', 106, 120), ('Mar', 120, 151), ('Apr', 151, 181), ('May-Jun', 181, 243)]
rows = []
for s in seasons:
    fb = FB[s]
    for k in NAMES:
        m = forest & (cls == k); n = m.sum(); d = fb[m]
        for lab, a, b in WIN:
            at_risk = ((d < 0) | (d >= a)).sum()
            burned = ((d >= a) & (d < b)).sum()
            rows.append(dict(season=s, cls=k, win=lab, n=n, at_risk=at_risk, burned=burned))
D = pd.DataFrame(rows)
P = D.groupby(['cls', 'win'], sort=False)[['n', 'at_risk', 'burned']].sum().reset_index()
P['share_of_class_burned_%'] = 100 * P.burned / P.n
P['hazard_%_of_unburned'] = 100 * P.burned / P.at_risk
tot = D.groupby('cls')[['burned']].sum().rename(columns={'burned': 'tot'})
P = P.merge(tot, on='cls'); P['share_of_class_burns_in_window_%'] = 100 * P.burned / P.tot
P['cls'] = P.cls.map(NAMES)
print('\nPooled 2017-2026, by class and window'); print(P.drop(columns=['n', 'at_risk', 'tot']).round(2).to_string(index=False))
P.to_csv(f'{OUT}/grass_timing_windows.csv', index=False)
# season burned share per class and median first-burn date
rows = []
for s in seasons:
    fb = FB[s]
    for k in NAMES:
        d = fb[forest & (cls == k)]; b = d[d >= 0]
        rows.append(dict(season=s, cls=NAMES[k], burned_pct=100 * (d >= 0).mean(), med_dos=np.median(b) if len(b) else np.nan,
                         p25=np.percentile(b, 25) if len(b) else np.nan, before15feb_pct_of_burns=100 * (b < 106).mean() if len(b) else np.nan))
S = pd.DataFrame(rows); S.to_csv(f'{OUT}/grass_timing_by_season.csv', index=False)
print('\nBy season'); print(S.round(1).to_string(index=False))
allb = {k: np.concatenate([FB[s][forest & (cls == k)] for s in seasons]) for k in NAMES}
for k, d in allb.items():
    b = d[d >= 0]; dt = lambda x: (pd.Timestamp('2020-11-01') + pd.Timedelta(days=float(x))).strftime('%d %b')
    print(f'{NAMES[k]:16s} burned pixel-seasons {100*(d>=0).mean():.2f}%  first-burn date p10 {dt(np.percentile(b,10))} p25 {dt(np.percentile(b,25))} median {dt(np.median(b))} p75 {dt(np.percentile(b,75))}')

# paired within 500 m cells: cells with burned class-1 and burned class-4 pixels in the same season
grid = gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(src.crs)
cid = rasterize(((geom, int(c)) for geom, c in zip(grid.geometry, grid.cell_id)), out_shape=(H, W), transform=T, fill=0, dtype='int32')
pr = []
for s in seasons:
    fb = FB[s]
    m = forest & (fb >= 0) & np.isin(cls, [1, 4]) & (cid > 0)
    df = pd.DataFrame(dict(c=cid[m], k=cls[m], d=fb[m]))
    agg = df.groupby(['c', 'k']).d.agg(['median', 'size']).unstack()
    agg = agg.dropna(); agg = agg[(agg[('size', 1)] >= 5) & (agg[('size', 4)] >= 5)]
    for c, r in agg.iterrows(): pr.append(dict(season=s, cell=c, d_dec=r[('median', 1)], d_grass=r[('median', 4)]))
PR = pd.DataFrame(pr); PR['diff'] = PR.d_grass - PR.d_dec
rng = np.random.default_rng(0)
bs = [PR.groupby('cell')['diff'].mean().sample(frac=1, replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(500)]
print(f"\nPaired cell-seasons {len(PR)} (cells {PR.cell.nunique()}): grass minus deciduous median first-burn day: mean {PR['diff'].mean():.1f} d, median {PR['diff'].median():.1f} d, "
      f"share grass earlier {100*(PR['diff']<0).mean():.1f}%, later {100*(PR['diff']>0).mean():.1f}%, same {100*(PR['diff']==0).mean():.1f}%; cell-bootstrap 95% CI of mean {np.percentile(bs,2.5):.1f} to {np.percentile(bs,97.5):.1f}")
# cell-season level: of burned area in mixed cells (both classes >=20% of forest), unburned share by class
st = []
for s in seasons:
    fb = FB[s]
    df = pd.DataFrame(dict(c=cid[forest & (cid > 0)], k=cls[forest & (cid > 0)], b=fb[forest & (cid > 0)] >= 0, e=(fb[forest & (cid > 0)] >= 0) & (fb[forest & (cid > 0)] < 106)))
    a = df.groupby(['c', 'k']).agg(n=('b', 'size'), b=('b', 'mean'), e=('e', 'mean')).unstack()
    n = a['n'].fillna(0); share = n.div(n.sum(1), axis=0)
    mix = (share.get(1, 0) >= 0.2) & (share.get(4, 0) >= 0.2)
    st.append(pd.DataFrame(dict(season=s, b_dec=a['b'][1][mix], b_grass=a['b'][4][mix], e_dec=a['e'][1][mix], e_grass=a['e'][4][mix])))
ST = pd.concat(st).dropna()
print(f"Mixed cells (>=20% each of deciduous and grass), {len(ST)} cell-seasons: mean burned share deciduous {100*ST.b_dec.mean():.1f}% vs grass {100*ST.b_grass.mean():.1f}%; "
      f"burned before 15 Feb: deciduous {100*ST.e_dec.mean():.2f}% vs grass {100*ST.e_grass.mean():.2f}%")

# grazing proxy: distance to buildings (Open Buildings) per cell
ob = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')[['cell_id', 'd_ob']]
dob = np.full(cid.max() + 1, np.nan); dob[ob.cell_id.values] = ob.d_ob.values
dpx = np.where(cid > 0, dob[cid], np.nan)
bins = [0, 1000, 2000, 3000, 1e9]; labs = ['<1 km', '1-2 km', '2-3 km', '>3 km']
rows = []
for k in [1, 4]:
    for i, lab in enumerate(labs):
        m = forest & (cls == k) & (dpx >= bins[i]) & (dpx < bins[i + 1])
        d = np.concatenate([FB[s][m] for s in seasons]); b = d[d >= 0]
        rows.append(dict(cls=NAMES[k], dist=lab, px=m.sum(), burned_pct=100 * (d >= 0).mean(), early_pct=100 * ((d >= 0) & (d < 106)).mean(),
                         med_date=(pd.Timestamp('2020-11-01') + pd.Timedelta(days=float(np.median(b)))).strftime('%d %b') if len(b) else ''))
G = pd.DataFrame(rows); print('\nBy distance to nearest building (cell level), pooled seasons'); print(G.round(2).to_string(index=False))

# greenness by month: NDVI / NDMI (monthly composites Sep 2023-May 2025), pixels unburned in seasons 2024 and 2025
unb = (FB[2024] < 0) & (FB[2025] < 0)
WK = R + 'work/'
rows = []
for mo in [9, 10, 11, 12, 1, 2, 3, 4, 5]:
    z = np.load(f'{WK}monthly/m{mo:02d}.npz')
    nd = z['ndvi'][::2, ::2].astype('float32'); nm = z['ndmi'][::2, ::2].astype('float32')
    re = None
    try:
        q = np.load(f'{WK}monthly_re/m{mo:02d}.npz'); b11 = q['B11'][::2, ::2].astype('float32'); b12 = q['B12'][::2, ::2].astype('float32')
        re = (b11 - b12) / (b11 + b12)
    except FileNotFoundError: pass
    for k in NAMES:
        m = forest & (cls == k) & unb
        rows.append(dict(month=mo, cls=NAMES[k], ndvi=np.nanmedian(nd[m]), ndvi_p25=np.nanpercentile(nd[m], 25), ndvi_p75=np.nanpercentile(nd[m], 75), ndmi=np.nanmedian(nm[m]),
                         ndti=np.nanmedian(re[m]) if re is not None else np.nan, pct_ndvi_lt_0p25=100 * np.nanmean(nd[m] < 0.25)))
N = pd.DataFrame(rows); N.to_csv(f'{OUT}/grass_greenness_by_month.csv', index=False)
print('\nMedian index by month, pixels unburned in 2024 and 2025 seasons'); print(N.round(3).to_string(index=False))
# relative-greenness curing proxy for class 4: (peak - now) / (peak - min) using Oct peak and min over Jan-May
z = {mo: np.load(f'{WK}monthly/m{mo:02d}.npz')['ndvi'][::2, ::2].astype('float32') for mo in [9, 10, 11, 12, 1, 2, 3, 4, 5]}
peak = np.nanmax(np.stack([z[9], z[10]]), 0); mn = np.nanmin(np.stack([z[m] for m in [1, 2, 3, 4, 5]]), 0)
for k in [1, 4]:
    m = forest & (cls == k) & unb & ((peak - mn) > 0.05)
    out = []
    for mo in [11, 12, 1, 2, 3, 4, 5]:
        cur = (peak[m] - z[mo][m]) / (peak[m] - mn[m]); out.append(f'{mo}:{100*np.nanmedian(np.clip(cur,0,1)):.0f}%')
    print(f'Relative-greenness "curing" (median, % of seasonal drop done) {NAMES[k]}: ' + ' '.join(out))
# NDVI by month for class 4 split near/far from buildings (grazing proxy)
for lab, sel in [('<1 km', dpx < 1000), ('>2 km', dpx >= 2000)]:
    m = forest & (cls == 4) & unb & sel
    print(f'class 4 {lab}: NDVI by month ' + ' '.join(f'{mo}:{np.nanmedian(z[mo][m]):.3f}' for mo in [9, 10, 11, 12, 1, 2, 3, 4, 5]), 'px', m.sum())

# detection bias: scar_found rate for FIRMS alerts by grass share within 200 m
L = pd.read_csv(V2 + 'firms_alert_scar_lookup.csv', usecols=['alert_id', 'latitude', 'longitude', 'acq_date', 'scar_found', 'sensor'])
tr = Transformer.from_crs('EPSG:4326', src.crs, always_xy=True)
x, y = tr.transform(L.longitude.values, L.latitude.values)
cc, rr = ~T * (x, y); rr = rr.astype(int); cc = cc.astype(int)
gs = np.full(len(L), np.nan); ds = np.full(len(L), np.nan)
for i, (r0, c0) in enumerate(zip(rr, cc)):
    if 10 <= r0 < H - 10 and 10 <= c0 < W - 10:
        w = cls[r0 - 10:r0 + 11, c0 - 10:c0 + 11]; f = np.isin(w, [1, 2, 4, 5])
        if f.sum() > 100: gs[i] = (w[f] == 4).mean(); ds[i] = (w[f] == 1).mean()
L['grass_share'] = gs; L['dec_share'] = ds; L = L.dropna(subset=['grass_share'])
L['found'] = L.scar_found.astype(str).str.lower().eq('yes')
L['mon'] = pd.to_datetime(L.acq_date).dt.month
L['q'] = pd.cut(L.grass_share, [-0.01, 0.1, 0.25, 0.4, 0.6, 1.0])
print('\nScar found rate for FIRMS alerts by share of open grass within ~200 m (forest pixels)')
print(L.groupby('q', observed=True).found.agg(['size', 'mean']).round(3).to_string())
print(L[L.mon.isin([2, 3, 4])].groupby('q', observed=True).found.agg(['size', 'mean']).round(3).rename(columns={'mean': 'found_FebApr'}).to_string())
