"""Geostationary heat: Meteosat (MSG IODC, 45.5E) FRP every 15 minutes (Akkshay 17 Oct 08:07Z: "try it").

Data: LSA SAF MSG-IODC FRP-PIXEL list product, 2018-2026, 1 Feb-30 Jun, cut to the MP box by the fetcher
(seviri_*.csv, kept in scratch, not the shared folder; login needed, never stored).
Question: with a reading every 15 minutes instead of 2-4 a day, does fire energy / burnt area finally
(1) grow in step with burnt area (VIIRS: area^0.45) and (2) follow fuel (canopy / fuel map v3)?
Matching: a Meteosat fire pixel belongs to a Ratapani fire if its centre is within 4 km of the scar outline and its time
falls in [first VIIRS look - 6 h, last VIIRS look + 12 h]; nearest scar wins when several qualify.
Energy = sum of FRP x 15 min over the slots (no detection = 0, so a lower bound).
Out: results/seviri_det.csv, seviri_fire.csv, seviri_tests.json, figures/seviri.png
"""
import glob, json, os
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from pyproj import Transformer
from shapely.geometry import Point
from shapely.strtree import STRtree
from h0_lib import RES, HERE, K_FRE, scars

GEO = os.environ.get('GEO_DIR', '/tmp/claude-0/geo')
S = pd.concat([pd.read_csv(f, parse_dates=['slot']) for f in sorted(glob.glob(f'{GEO}/seviri_part_*.csv')) if os.path.getsize(f) > 10])
S['t'] = S.slot + pd.to_timedelta(S.acqtime.fillna(0) % 15, 'min') if False else S.slot   # slot start (acqtime is a line counter)
x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(S.lon.values, S.lat.values)
S['x'], S['y'] = x, y
SC = scars(); fids = np.array(list(SC)); polys = [SC[f] for f in fids]
xmin, ymin, xmax, ymax = np.array([p.bounds for p in polys]).T
S = S[(S.x > xmin.min() - 5000) & (S.x < xmax.max() + 5000) & (S.y > ymin.min() - 5000) & (S.y < ymax.max() + 5000)].copy()
print('Meteosat detections in Ratapani box', len(S), 'slots', S.slot.nunique())

FI = pd.read_csv(f'{HERE}/../big-fires/results/fires.csv', parse_dates=['date0', 'date1']).set_index('fire')
G = pd.read_csv(f'{RES}/viirs_det.csv', parse_dates=['t']).dropna(subset=['fire']); G['fire'] = G.fire.astype(int)
W = G.groupby('fire').t.agg(['min', 'max'])
W = W.reindex(FI.index)                                   # fires without VIIRS times: use their scar dates (IST days)
W['min'] = W['min'].fillna(FI.date0 - pd.Timedelta('5.5h')); W['max'] = W['max'].fillna(FI.date1 + pd.Timedelta('18.5h'))
W['a'] = W['min'] - pd.Timedelta('6h'); W['b'] = W['max'] + pd.Timedelta('12h')
tree = STRtree(polys); idx = {f: i for i, f in enumerate(fids)}
own = []
for r in S.itertuples():
    best, bd = -1, 4000.0
    for i in tree.query(Point(r.x, r.y).buffer(4000)):
        f = fids[i]
        if f not in W.index or not (W.at[f, 'a'] <= r.t <= W.at[f, 'b']): continue
        d = polys[i].distance(Point(r.x, r.y))
        if d <= bd: best, bd = f, d
    own.append(best)
S['fire'] = own; S['dist_m'] = np.nan
S.to_csv(f'{RES}/seviri_det.csv', index=False)
M = S[S.fire >= 0].copy()
print('matched detections', len(M), 'fires', M.fire.nunique())
out = {'detections_box': len(S), 'detections_matched': len(M), 'fires_seen': int(M.fire.nunique())}

# ---- 1. which fires does Meteosat see at all
A = pd.read_csv(f'{RES}/corrected_fire_fuel.csv')
area = pd.read_csv(f'{HERE}/../big-fires/results/fires.csv').set_index('fire').area_ha
A['area_ha'] = A.fire.map(area); A['seen'] = A.fire.isin(M.fire)
A = A[A.season >= 2018]
sz = pd.cut(A.area_ha, [0, 30, 60, 120, 240, 1e6], labels=['<30', '30-60', '60-120', '120-240', '>240'])
out['seen_by_size'] = (A.groupby(sz, observed=True).seen.mean() * 100).round(1).to_dict()
print('share of fires seen by Meteosat, by scar ha', out['seen_by_size'])

# ---- 2. per fire energy from the 15-min series
P = M.groupby(['fire', 'slot']).frp.sum().reset_index()
E = P.groupby('fire').agg(fre_mj=('frp', lambda v: v.sum() * 900), slots=('frp', 'size'), peak=('frp', 'max'),
                          first=('slot', 'min'), last=('slot', 'max')).reset_index()
E = E.merge(A, on='fire')
E['geo_tha'] = 10 * K_FRE * E.fre_mj / (E.area_ha * 1e4)
E['viirs_fre_mj'] = E.fuel_corr * E.area_ha * 1e4 / (10 * K_FRE)
E['geo_over_viirs'] = E.fre_mj / E.viirs_fre_mj
E.to_csv(f'{RES}/seviri_fire.csv', index=False)
out['n_fires_energy'] = len(E)
out['median_geo_tha'] = round(E.geo_tha.median(), 2); out['median_viirs_tha_same_fires'] = round(E.fuel_corr.median(), 2)
out['median_geo_over_viirs'] = round(E.geo_over_viirs.median(), 2)
out['median_slots'] = float(E.slots.median())
print(out)

# ---- 3. diurnal: when does Ratapani burn, seen every 15 min (fires with >= 4 slots)
M['ist'] = ((M.slot.dt.hour + M.slot.dt.minute / 60 + 5.5) % 24)
H = M.groupby(M.ist.astype(int)).frp.sum(); H = H / H.mean()
out['diurnal_frp_by_ist_hour'] = H.round(3).to_dict()
day = H.reindex([12, 13, 14]).fillna(0).mean(); night = H.reindex([0, 1, 2]).fillna(0).mean()
out['night_over_day_0030_0230_vs_1230_1430'] = round(night / day, 3)
print('night/day', out['night_over_day_0030_0230_vs_1230_1430'])

# ---- 4. scaling with area and fuel tests
def slope(D, ycol):
    ok = D[[ycol, 'area_ha']].dropna(); ok = ok[ok[ycol] > 0]
    b = np.polyfit(np.log(ok.area_ha), np.log(ok[ycol]), 1)[0]
    bs = [np.polyfit(*np.log(ok.sample(frac=1, replace=True, random_state=i)[['area_ha', ycol]].values.T), 1)[0] for i in range(300)]
    return [round(b, 3), [round(float(v), 3) for v in np.percentile(bs, [2.5, 97.5])]]
out['energy_vs_area_exponent'] = {'meteosat': slope(E, 'fre_mj'), 'viirs_same_fires': slope(E, 'viirs_fre_mj')}
print('exponent', out['energy_vs_area_exponent'])
for tag, D in [('all_seen', E), ('seen_4plus_slots', E[E.slots >= 4])]:
    o = {'n': len(D)}
    for c in ['canopy', 'litter', 'grass', 'mapfuel', 'area_ha', 'doy']:
        ok = D[[c, 'geo_tha']].dropna(); r = spearmanr(ok[c], ok.geo_tha)[0]
        b = [spearmanr(*ok.sample(frac=1, replace=True, random_state=i).values.T)[0] for i in range(300)]
        o[c] = [round(r, 3), [round(float(v), 3) for v in np.percentile(b, [2.5, 97.5])]]
    lm = np.log(D.mapfuel); lf = np.log(D.geo_tha); rng = np.random.default_rng(0)
    nz = np.sqrt(max(lf.var() - lm.var(), 1e-6))
    o['expected_if_map_right'] = round(float(np.mean([spearmanr(lm, lm + nz * rng.standard_normal(len(lm)))[0] for _ in range(200)])), 3)
    out[tag] = o; print(tag, o)
cb = pd.cut(E.canopy, [0, 20, 40, 60, 100])
out['by_canopy'] = E.groupby(cb, observed=True).agg(fires=('fire', 'size'), meteosat_tha=('geo_tha', 'median'),
                                                    viirs_tha=('fuel_corr', 'median'), map=('mapfuel', 'median')).round(2).reset_index().astype(str).to_dict('records')
szE = pd.cut(E.area_ha, [0, 60, 120, 240, 500, 1e6])
out['by_size'] = E.groupby(szE, observed=True).agg(fires=('fire', 'size'), meteosat_tha=('geo_tha', 'median'), viirs_tha=('fuel_corr', 'median'),
                                                   slots=('slots', 'median')).round(2).reset_index().astype(str).to_dict('records')
print(pd.DataFrame(out['by_canopy'])); print(pd.DataFrame(out['by_size']))
json.dump(out, open(f'{RES}/seviri_tests.json', 'w'), indent=1, default=str)
