"""Merge per-division metrics (t3), checks (t6), leaf-fall curve (t4b) and scar detection (all-MP sample, 15 Oct run) into one table
with 'Ratapani rule may fail' flags. Output: out/division_types_final.csv; prints correlations used in the note."""
import pandas as pd, numpy as np
m = pd.read_csv('out/division_metrics.csv', index_col=0)
c = pd.read_csv('out/division_checks.csv', index_col=0)
lf = pd.read_csv('out/leaf_curve_division.csv', index_col=0).add_prefix('leaf_')
ev = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/eval_sample_by_division.csv', index_col=0).rename(columns={'mean_fire': 'scar_found_fire', 'mean_control': 'scar_found_control'})
p = pd.read_parquet('out/viirs_vtm.parquet'); s = p[p.sat == 'snpp']
# management-style early burning: share of points before 15 Feb in 2023-2026 minus 2014-2022
e1 = s[s.season >= 2023].groupby('Division').doy.apply(lambda v: (v < 46).mean())
e0 = s[s.season <= 2022].groupby('Division').doy.apply(lambda v: (v < 46).mean())
T = m.join(c, rsuffix='_c').join(lf).join(ev[['scar_found_fire', 'scar_found_control']])
T['early_share_2023_26'] = e1; T['early_share_2014_22'] = e0; T['early_jump'] = e1 - e0
R = 'Obedullahganj'
T['leaf_d50_shift_days_vs_ratapani'] = T.leaf_d50 - T.loc[R, 'leaf_d50']
T['doy_med_shift_days_vs_ratapani'] = T.doy_med - T.loc[R, 'doy_med']
flags = []
for d, r in T.iterrows():
    f = []
    if r.share_type2_static > 0.05 or r.share_pts_in_cells_burnt_ge9of13yrs > 0.05: f.append('STATIC/INDUSTRIAL heat (mask first)')
    if r.share_before_15feb > 0.10 or r.n20_share_before_15feb > 0.12: f.append('EARLY fires outside 15Feb window')
    if r.early_jump > 0.10: f.append(f'EARLY-BURN REGIME CHANGE 2023-26 (+{100*r.early_jump:.0f} pts %)')
    if r.share_after_15may > 0.08: f.append('LATE season (>8% after 15 May)')
    if r.doy_med_shift_days_vs_ratapani >= 14: f.append(f'LATER median fire date (+{r.doy_med_shift_days_vs_ratapani:.0f} d)')
    if r.leaf_d50_shift_days_vs_ratapani >= 14: f.append(f'LATER leaf fall (+{r.leaf_d50_shift_days_vs_ratapani:.0f} d)')
    if r.leaf_d50_shift_days_vs_ratapani <= -28: f.append(f'EARLIER leaf fall ({r.leaf_d50_shift_days_vs_ratapani:.0f} d)')
    if r.sal >= 0.30: f.append('SAL-dominated')
    if r.north_dry >= 0.25: f.append('THORN/SCRUB/GRASS')
    if r.leaf_ndvi_dry >= 0.38: f.append('Dry-season canopy stays green (NDVI>=0.38): scars under canopy')
    if r.scar_found_fire < 0.75: f.append(f'Scar found only {100*r.scar_found_fire:.0f}%')
    if r.share_pts_in_agri_vtm > 0.35: f.append('FARM points >35%')
    if r.pts_per_100km2_yr < 5: f.append('SPARSE (<5 pts/100 km2/yr)')
    flags.append('; '.join(f))
T['flags'] = flags; T['n_flags'] = [len(x.split('; ')) if x else 0 for x in flags]
keep = ['forest_km2', 'n_beats', 'dominant', 'sal', 'teak', 'dry_mixed', 'moist_mixed', 'degraded', 'bamboo', 'north_dry', 'pts_per_100km2_yr',
        'peak_week', 'doy_p10', 'doy_med', 'doy_p90', 'share_before_15feb', 'share_after_15may', 'share_after_15jun', 'share_jan', 'n20_share_before_15feb',
        'early_share_2014_22', 'early_share_2023_26', 'night_share', 'frp_med', 'repeat_burn_share', 'return_interval_yrs_burnt_cells', 'pts_per_event_mean',
        'share_events_ge10pts', 'annual_cv', 'corr_annual_with_obedullahganj', 'median_doy_sd_across_years', 'share_type2_static',
        'share_pts_in_cells_burnt_ge9of13yrs', 'share_pts_in_agri_vtm', 'leaf_ndvi_wet', 'leaf_ndvi_dry', 'leaf_d50', 'leaf_d80', 'leaf_f_15feb',
        'leaf_d50_shift_days_vs_ratapani', 'doy_med_shift_days_vs_ratapani', 'scar_found_fire', 'scar_found_control', 'n_flags', 'flags']
T[keep].sort_values('pts_per_100km2_yr', ascending=False).to_csv('out/division_types_final.csv', float_format='%.4g')
w = T[T.n_pts_snpp >= 300]
print('n divisions with >=300 pts', len(w))
for a, b in [('leaf_d50', 'doy_med'), ('leaf_d50', 'peak_week'), ('sal', 'doy_med'), ('pts_per_100km2_yr', 'repeat_burn_share'), ('leaf_ndvi_dry', 'scar_found_fire'),
             ('sal', 'scar_found_fire'), ('north_dry', 'pts_per_100km2_yr'), ('teak', 'pts_per_100km2_yr'), ('corr_annual_with_obedullahganj', 'pts_per_100km2_yr'), ('leaf_d50', 'share_before_15feb')]:
    print(a, b, 'spearman', round(w[a].corr(w[b], method='spearman'), 2))
print(T.n_flags.value_counts().sort_index().to_dict())
print(T.sort_values('n_flags', ascending=False)[['n_flags', 'flags']].head(30).to_string())
