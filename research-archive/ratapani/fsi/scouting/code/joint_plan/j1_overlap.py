"""Round r30, step 1. Lines and control burns on the same ground: which practical fire line lies in which repeat patch,
what each patch is worth under each tool, and the combined programme at a few sizes.
Inputs: control_burn/out/control_burn_patches_mp.geojson (tr3 patches, held-out 2022-25 burn benefit, cb8),
        fire_lines_v2/out/proposed_fire_lines_mp_practical.geojson (all5 practical lines, in-sample all nine seasons, m7/m6).
Rules (see joint_plan.md): a patch that is burnt every year in 15-28 Feb gets its practical lines as burn-block boundaries
(no extra wildfire saving that season); a patch that is not burnt gets them as cuts, worth the held-out saving.
Held-out factor for the in-sample line saving, by statewide km tier (fire_lines_v2.md sec 9): 500 km 0.49, 1,000 0.57, 2,000 0.60, 5,000 0.68.
Costs: line Rs 1,356 per km per year (CAMPA rate); block burn Rs 120 per ha (crew at watcher wages, inference); a burnt patch
needs a boundary on the part of its edge with no natural barrier, taken as 60% of the simplified perimeter (inference).
Out: out/j1_patches.csv, j1_lines.csv, j1_programmes.csv, j1_by_division.csv, j1_patches.geojson, j1_lines.geojson"""
import os, json
import numpy as np, pandas as pd, geopandas as gpd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
SC = '/mnt/project-files/ratapani/fsi/scouting/code/'
HO = {500: 0.49, 1000: 0.57, 2000: 0.60, 5000: 0.68}
RS_KM, RS_HA, BOUND_SHARE = 1356.0, 120.0, 0.60
MP_BURNT = 718704.0

P = gpd.read_file(SC + 'control_burn/out/control_burn_patches_mp.geojson').to_crs(32643)
Ln = gpd.read_file(SC + 'fire_lines_v2/out/proposed_fire_lines_mp_practical.geojson').to_crs(32643)
P['pid'] = np.arange(len(P)); P['perim_km'] = P.geometry.simplify(120).length / 1000
Ln['lid'] = np.arange(len(Ln)); Ln['ho_factor'] = Ln.budget_tier_km.map(HO); Ln['saved_ho'] = Ln.forest_ha_per_yr_in_sample * Ln.ho_factor
# each line -> the tr3 patch it mostly runs through (within 150 m)
J = gpd.sjoin(Ln[['lid', 'geometry']], P[['pid', 'geometry']].assign(geometry=P.buffer(150)), how='inner', predicate='intersects')
J = J.merge(P[['pid', 'geometry']].rename(columns={'geometry': 'pg'}), on='pid')
J['ol'] = [l.intersection(g.buffer(150)).length for l, g in zip(J.geometry, J.pg)]
best = J.sort_values('ol', ascending=False).drop_duplicates('lid')[['lid', 'pid', 'ol']]
Ln = Ln.merge(best, on='lid', how='left'); Ln['in_tr3'] = Ln.pid.notna()
print('lines', len(Ln), 'km', round(Ln.km.sum()), 'in a tr3 patch', int(Ln.in_tr3.sum()), 'km', round(Ln.km[Ln.in_tr3].sum()))
# per patch line totals
g = Ln[Ln.in_tr3].groupby('pid').agg(lines=('lid', 'size'), line_km=('km', 'sum'), line_saved_is=('forest_ha_per_yr_in_sample', 'sum'),
                                    line_saved_ho=('saved_ho', 'sum'), km_nala=('km_on_nala', 'sum'), km_ridge=('km_on_ridge', 'sum'),
                                    km_road=('km_on_road', 'sum'), km_edge=('km_on_forest_edge', 'sum'), km_steep=('km_steep_over_15pct', 'sum'))
P = P.merge(g, left_on='pid', right_index=True, how='left').fillna({c: 0 for c in g.columns})
P['boundary_km'] = BOUND_SHARE * P.perim_km
# value of each tool per patch, per year
P['burn_saved'] = P.outside_ha_yr; P['burn_converted'] = P.converted_ha_yr
P['burn_cost'] = P.forest_ha * RS_HA + (P.boundary_km + P.line_km) * RS_KM          # boundary + internal block lines kept every year
P['lines_saved'] = P.line_saved_ho; P['lines_cost'] = P.line_km * RS_KM
P['burn_rs_per_ha_saved'] = P.burn_cost / P.burn_saved.replace(0, np.nan)
P['burn_rs_per_ha_benefit'] = P.burn_cost / (P.burn_saved + P.burn_converted).replace(0, np.nan)
P['lines_rs_per_ha_saved'] = P.lines_cost / P.lines_saved.replace(0, np.nan)
# combined programme sizes: burn the first N ha by cb8 rank, lines as cuts everywhere else
SIZES = [('S1', 25000, 'first 25k ha'), ('S2', 50000, 'first 50k ha'), ('S3', 100000, 'first 100k ha'), ('S4', 200000, 'first 200k ha'), ('S5', 10**9, 'all 419k ha')]
rows = []; P = P.sort_values('rank')
out_tr3_lines = Ln[~Ln.in_tr3]
for code, N, lab in SIZES:
    B = P[P.cum_ha <= N]; R = P[P.cum_ha > N]
    r = dict(programme=code, burn_set=lab, patches_burnt=len(B), divisions_burnt=B.division.nunique(), ha_burnt=B.forest_ha.sum(),
             boundary_km=B.boundary_km.sum(), block_lines_km=B.line_km.sum(), block_lines=int(B.lines.sum()),
             cut_lines=int(R.lines.sum() + len(out_tr3_lines)), cut_km=R.line_km.sum() + out_tr3_lines.km.sum(),
             patches_lined=int((R.lines > 0).sum()), divisions_lined=R[R.lines > 0].division.nunique(),
             saved_outside=B.burn_saved.sum(), converted=B.burn_converted.sum(), saved_lines=R.lines_saved.sum() + out_tr3_lines.saved_ho.sum(),
             forgone_line_saving_in_burnt=B.line_saved_ho.sum())
    r['saved_total'] = r['saved_outside'] + r['saved_lines']; r['benefit_total'] = r['saved_total'] + r['converted']
    r['pct_mp_burnt_saved'] = 100 * r['saved_total'] / MP_BURNT; r['pct_mp_burnt_benefit'] = 100 * r['benefit_total'] / MP_BURNT
    r['cost_burn_rs'] = B.forest_ha.sum() * RS_HA; r['cost_lines_rs'] = (B.boundary_km.sum() + B.line_km.sum() + r['cut_km']) * RS_KM
    r['cost_total_rs'] = r['cost_burn_rs'] + r['cost_lines_rs']; r['cost_crore'] = r['cost_total_rs'] / 1e7
    r['rs_per_ha_saved'] = r['cost_total_rs'] / r['saved_total']; r['rs_per_ha_benefit'] = r['cost_total_rs'] / r['benefit_total']
    rows.append(r)
# the two single-tool programmes for comparison
L5 = Ln; rows.append(dict(programme='L', burn_set='lines only, all 4,986 km', patches_burnt=0, ha_burnt=0, boundary_km=0, block_lines_km=0, block_lines=0,
                          cut_lines=len(L5), cut_km=L5.km.sum(), patches_lined=int(Ln.in_tr3.sum() and P[P.lines > 0].shape[0]), divisions_lined=L5.division.nunique(),
                          saved_outside=0, converted=0, saved_lines=L5.saved_ho.sum(), forgone_line_saving_in_burnt=0,
                          saved_total=L5.saved_ho.sum(), benefit_total=L5.saved_ho.sum(), pct_mp_burnt_saved=100 * L5.saved_ho.sum() / MP_BURNT,
                          pct_mp_burnt_benefit=100 * L5.saved_ho.sum() / MP_BURNT, cost_burn_rs=0, cost_lines_rs=L5.km.sum() * RS_KM,
                          cost_total_rs=L5.km.sum() * RS_KM, cost_crore=L5.km.sum() * RS_KM / 1e7, rs_per_ha_saved=RS_KM * L5.km.sum() / L5.saved_ho.sum(),
                          rs_per_ha_benefit=RS_KM * L5.km.sum() / L5.saved_ho.sum()))
PR = pd.DataFrame(rows); PR.to_csv(OUT + 'j1_programmes.csv', index=False)
pd.set_option('display.width', 250); print(PR.round(0).to_string(index=False))
# per division, for every programme size
dv = []
for code, N, lab in SIZES:
    B = P[P.cum_ha <= N]; R = P[P.cum_ha > N]
    a = B.groupby('division').agg(patches_burnt=('pid', 'size'), ha_burnt=('forest_ha', 'sum'), boundary_km=('boundary_km', 'sum'), block_lines_km=('line_km', 'sum'),
                                  saved_outside=('burn_saved', 'sum'), converted=('burn_converted', 'sum'))
    b = R.groupby('division').agg(patches_lined=('lines', lambda s: int((s > 0).sum())), cut_km=('line_km', 'sum'), saved_lines=('lines_saved', 'sum'))
    c = out_tr3_lines.groupby('division').agg(cut_km_out=('km', 'sum'), saved_lines_out=('saved_ho', 'sum'))
    d = a.join(b, how='outer').join(c, how='outer').fillna(0); d['cut_km'] += d.cut_km_out; d['saved_lines'] += d.saved_lines_out
    d = d.drop(columns=['cut_km_out', 'saved_lines_out']); d['programme'] = code; dv.append(d.reset_index())
DV = pd.concat(dv); DV['saved_total'] = DV.saved_outside + DV.saved_lines; DV['benefit_total'] = DV.saved_total + DV.converted
DV['cost_rs'] = DV.ha_burnt * RS_HA + (DV.boundary_km + DV.block_lines_km + DV.cut_km) * RS_KM
DV.to_csv(OUT + 'j1_by_division.csv', index=False)
# per-patch and per-line outputs (role under S3 = first 100k ha, the recommended first programme; see joint_plan.md)
P['role_S3'] = np.where(P.cum_ha <= 100000, 'burn', np.where(P.lines > 0, 'lines', 'none'))
P['role_S5'] = np.where(P.lines > 0, 'burn + block lines', 'burn')
Ln = Ln.merge(P[['pid', 'rank', 'tier', 'cum_ha']].rename(columns={'rank': 'patch_rank', 'tier': 'patch_tier', 'cum_ha': 'patch_cum_ha'}), on='pid', how='left')
Ln['role_S3'] = np.where(Ln.in_tr3 & (Ln.patch_cum_ha <= 100000), 'burn-block boundary', 'cut')
Ln['role_S5'] = np.where(Ln.in_tr3, 'burn-block boundary', 'cut')
cols = [c for c in P.columns if c not in ('geometry',)]
P[cols].round(2).to_csv(OUT + 'j1_patches.csv', index=False)
lc = [c for c in Ln.columns if c not in ('geometry', 'ol')]
Ln[lc].round(3).to_csv(OUT + 'j1_lines.csv', index=False)
P.to_crs(4326).to_file(OUT + 'j1_patches.geojson', driver='GeoJSON')
Ln.drop(columns=['ol']).to_crs(4326).to_file(OUT + 'j1_lines.geojson', driver='GeoJSON')
print('patches with lines', int((P.lines > 0).sum()), 'of', len(P), '; line km inside tr3', round(P.line_km.sum()), 'outside', round(out_tr3_lines.km.sum()))
print('held-out line saving total', round(Ln.saved_ho.sum()), 'in-sample', round(Ln.forest_ha_per_yr_in_sample.sum()))
