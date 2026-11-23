"""Per-division fire-regime metrics from all-MP VIIRS (points inside forest beats), plus VTM forest-type shares, plus flags
for where Ratapani-calibrated rules may fail.
Inputs: out/viirs_vtm.parquet (t2), out/beat_vtm.csv (t2), out/division_area.csv (t1).
Output: out/division_metrics.csv, out/division_weekly.csv, out/type_regime.csv."""
import numpy as np, pandas as pd
from sklearn.cluster import DBSCAN
p = pd.read_parquet('out/viirs_vtm.parquet')
area = pd.read_csv('out/division_area.csv', index_col=0)
bv = pd.read_csv('out/beat_vtm.csv')
GROUPS = {'sal': [24, 27, 36], 'teak': [25, 28, 37], 'dry_mixed': [26], 'moist_mixed': [23], 'degraded': [106],
          'bamboo': [30, 40], 'north_dry': [29, 46, 49, 53, 54, 55, 116, 120, 121, 123, 124, 132, 135],
          'agri_settl': [170, 200, 150, 180], 'water': [190, 191]}
code = {int(c.split(':')[0]): c for c in bv.columns[2:]}
gshare = pd.DataFrame(index=sorted(bv.Division.unique()))
dsum = bv.groupby('Division')[bv.columns[2:]].sum()
tot = dsum.sum(axis=1)
for g, cs in GROUPS.items():
    gshare[g] = dsum[[code[c] for c in cs if c in code]].sum(axis=1) / tot
gshare['vtm_mapped_km2'] = tot / 100
forest_groups = [g for g in GROUPS if g not in ('agri_settl', 'water')]
gshare['dominant'] = gshare[forest_groups].idxmax(axis=1)

# local point -> type group
c2g = {c: g for g, cs in GROUPS.items() for c in cs}
p['grp'] = p.vtm.map(c2g).fillna('other')
s = p[(p.sat == 'snpp')].copy()            # one sensor, 13 seasons 2014-2026, consistent
NY = s.season.nunique()
# 500 m-ish grid (0.005 deg) for repeat burns
s['cell'] = (np.floor(s.latitude / 0.005).astype(int) * 100000 + np.floor(s.longitude / 0.005).astype(int))
s['week'] = ((s.doy - 1) // 7 + 1).clip(upper=26)
rows = []
weekly = s.groupby(['Division', 'week']).size().unstack(fill_value=0) / NY
for d, x in s.groupby('Division'):
    r = {'Division': d, 'n_pts_snpp': len(x)}
    km2 = area.loc[d, 'forest_km2']; r['forest_km2'] = km2; r['n_beats'] = area.loc[d, 'n_beats']
    r['pts_per_100km2_yr'] = 100 * len(x) / km2 / NY
    wk = weekly.loc[d].reindex(range(1, 27), fill_value=0).rolling(3, center=True, min_periods=1).mean()
    r['peak_week'] = int(wk.idxmax())
    r['doy_p10'], r['doy_med'], r['doy_p90'] = np.percentile(x.doy, [10, 50, 90])
    r['share_before_15feb'] = (x.doy < 46).mean()
    r['share_after_15may'] = (x.doy > 135).mean()
    r['share_after_15jun'] = (x.doy > 166).mean()
    r['night_share'] = (x.daynight == 'N').mean()
    r['frp_med'] = x.frp.median()
    r['share_pts_in_agri_vtm'] = (x.grp == 'agri_settl').mean()
    # repeat burn: cells with fire in Y that also had fire in Y-1
    cy = x.groupby('cell').season.apply(set)
    rep, base = 0, 0
    for yrs in cy:
        for y in yrs:
            if y > 2014:
                base += 1; rep += (y - 1) in yrs
    r['repeat_burn_share'] = rep / base if base else np.nan
    ny = cy.apply(len)
    r['cells_burnt_ever'] = len(cy)
    r['mean_fire_years_per_burnt_cell'] = ny.mean()
    r['return_interval_yrs_burnt_cells'] = NY / ny.mean()
    r['share_burnt_cells_ge_half_years'] = (ny >= NY / 2).mean()
    # events: DBSCAN in (km, km, day*0.75) eps 0.8 -> joins points within ~0.8 km and ~1 day
    ev_pts, ev_days = [], []
    for y, xx in x.groupby('season'):
        X = np.c_[xx.latitude * 111.0, xx.longitude * 102.0, (xx.t_ist - pd.Timestamp('2000-01-01')).dt.total_seconds() / 86400 * 0.75]
        lab = DBSCAN(eps=0.8, min_samples=1).fit_predict(X)
        g = pd.DataFrame({'l': lab, 't': xx.date_ist.values}).groupby('l')
        ev_pts += list(g.size()); ev_days += list(g.t.nunique())
    ev_pts = np.array(ev_pts); ev_days = np.array(ev_days)
    r['events_per_yr'] = len(ev_pts) / NY
    r['pts_per_event_mean'] = ev_pts.mean(); r['share_events_1pt'] = (ev_pts == 1).mean()
    r['share_events_ge10pts'] = (ev_pts >= 10).mean(); r['days_per_event_mean'] = ev_days.mean()
    ann = x.groupby('season').size().reindex(range(2014, 2027), fill_value=0)
    r['annual_cv'] = ann.std() / ann.mean()
    r['_ann'] = ann
    rows.append(r)
m = pd.DataFrame(rows).set_index('Division')
ann = pd.DataFrame({d: m.loc[d, '_ann'] for d in m.index})
m = m.drop(columns='_ann')
ref = 'Obedullahganj'
m['corr_annual_with_obedullahganj'] = ann.corr()[ref]
m = m.join(gshare)
refpk = m.loc[ref, 'peak_week']
m['peak_shift_wk_vs_ratapani'] = m.peak_week - refpk
# flags
fl = []
for d, r in m.iterrows():
    f = []
    if r.share_before_15feb > 0.10: f.append('EARLY(>10% before 15Feb)')
    if r.share_after_15jun > 0.03: f.append('LATE(>3% after 15Jun)')
    if abs(r.peak_shift_wk_vs_ratapani) >= 3: f.append(f'PEAK_SHIFT({r.peak_shift_wk_vs_ratapani:+d}wk)')
    if r.sal >= 0.30: f.append('SAL(leaf-fall Mar-Apr; scar under semi-evergreen canopy)')
    if r.north_dry >= 0.25: f.append('THORN/SCRUB/GRASS(open fuels, low tree cover)')
    if r.bamboo >= 0.10: f.append('BAMBOO')
    if r.share_pts_in_agri_vtm > 0.35: f.append('FARM_CONTAMINATION(>35% pts on VTM agriculture)')
    if r.pts_per_100km2_yr < 5: f.append('SPARSE(<5 pts/100km2/yr: per-division model data-starved)')
    fl.append('; '.join(f))
m['flags'] = fl
m.sort_values('pts_per_100km2_yr', ascending=False).to_csv('out/division_metrics.csv', float_format='%.4g')
weekly.to_csv('out/division_weekly.csv', float_format='%.3g')
# regime by forest-type group (point-level class, not division)
t = []
for g, x in s.groupby('grp'):
    t.append({'grp': g, 'n': len(x), 'doy_p10': x.doy.quantile(.1), 'doy_med': x.doy.median(), 'doy_p90': x.doy.quantile(.9),
              'peak_week': int((x.groupby('week').size().reindex(range(1, 27), fill_value=0).rolling(3, center=True, min_periods=1).mean()).idxmax()),
              'before_15feb': (x.doy < 46).mean(), 'after_15may': (x.doy > 135).mean(), 'after_15jun': (x.doy > 166).mean(),
              'night': (x.daynight == 'N').mean(), 'frp_med': x.frp.median(), 'frp_p90': x.frp.quantile(.9)})
tg = pd.DataFrame(t).set_index('grp')
gk = {g: sum(dsum[code[c]].sum() for c in cs if c in code) / 100 for g, cs in GROUPS.items()}
tg['km2_in_beats'] = pd.Series(gk); tg['pts_per_100km2_yr'] = 100 * tg.n / tg.km2_in_beats / NY
# repeat by group
s2 = s.copy(); cyg = s2.groupby(['grp', 'cell']).season.apply(set)
rr = {}
for g in tg.index:
    rep = base = 0
    for yrs in cyg.loc[g]:
        for y in yrs:
            if y > 2014: base += 1; rep += (y - 1) in yrs
    rr[g] = rep / base if base else np.nan
tg['repeat_burn_share'] = pd.Series(rr)
tg.to_csv('out/type_regime.csv', float_format='%.4g')
print(tg.round(3).to_string())
pd.set_option('display.width', 250)
cols = ['forest_km2', 'pts_per_100km2_yr', 'peak_week', 'doy_med', 'share_before_15feb', 'share_after_15may', 'share_after_15jun', 'night_share',
        'repeat_burn_share', 'return_interval_yrs_burnt_cells', 'pts_per_event_mean', 'dominant', 'sal', 'teak', 'north_dry', 'flags']
print(m.sort_values('pts_per_100km2_yr', ascending=False)[cols].round(3).to_string())
