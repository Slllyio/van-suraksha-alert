"""Round r30, step 4. The report: HTML built from the j1-j3 outputs and the earlier round-28/29 results, printed to PDF with Chromium.
Out: /mnt/project-files/ratapani/fsi/scouting/report/joint_plan_mp.pdf (+ .html)"""
import os, subprocess, datetime as dt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
SC = '/mnt/project-files/ratapani/fsi/scouting/'; REP = SC + 'report/'; os.makedirs(REP, exist_ok=True)
F28, F29, F30 = SC + 'figs_r28/', SC + 'figs_r29/', SC + 'figs_r30/'
MP_BURNT = 718704.0
PR = pd.read_csv(OUT + 'j1_programmes.csv'); DV = pd.read_csv(OUT + 'j1_by_division.csv'); P = pd.read_csv(OUT + 'j1_patches.csv'); Ln = pd.read_csv(OUT + 'j1_lines.csv')
BF = pd.read_csv(OUT + 'j2_bigfires.csv'); FI = pd.read_csv(OUT + 'j2_fires.csv')
Q = pd.read_parquet(SC + 'code/control_burn/out/cb3_squares.parquet')
A = pd.read_csv(SC + 'code/control_burn/out/cb2_age.csv'); C6 = pd.read_csv(SC + 'code/control_burn/out/cb6_design.csv')
W9 = pd.read_csv(SC + 'code/control_burn/out/cb9_windows.csv'); B9 = pd.read_csv(SC + 'code/control_burn/out/cb9_budget.csv')
SZ = pd.read_csv(SC + 'code/control_burn/out/cb3_sizes.csv')
key2div = dict(zip(P.key, P.division))
def nm(k): return key2div.get(k, k).replace('_', ' ')

def tbl(df, fmt=None, cls=''):
    df = df.copy()
    for c in df.columns:
        if fmt and c in fmt: df[c] = df[c].map(fmt[c])
        elif df[c].dtype.kind == 'f': df[c] = df[c].map(lambda v: '' if pd.isna(v) else f'{v:,.0f}')
        elif df[c].dtype.kind == 'i': df[c] = df[c].map(lambda v: f'{v:,}')
    return df.to_html(index=False, classes='t ' + cls, border=0, escape=False)
def img(path, cap, w=100): return f'<figure><img src="file://{path}" style="width:{w}%"><figcaption>{cap}</figcaption></figure>'
def pct(v): return f'{v:.1f}%'
I = lambda s: f'<span class="inf">[inference]</span> {s}'

# ---------- numbers ----------
S = PR.set_index('programme'); s1, s3, s5, L = S.loc['S1'], S.loc['S3'], S.loc['S5'], S.loc['L']
T = FI[FI.year >= 2022]; big = T[T.forest_ha >= 200]
share_big_in_tr3 = (big.start_patch > 0).mean(); share_big_ha_in_tr3 = big.forest_ha[big.start_patch > 0].sum() / big.forest_ha.sum()
share_ha_on_patch = T.in_patch_forest_ha.sum() / T.forest_ha.sum()
km_in = Ln.km[Ln.in_tr3].sum(); km_all = Ln.km.sum()
# per-division base table
Qd = Q.groupby(['key', 'year']).agg(ha=('ha_late', 'sum'), p1=('ha_p1', 'sum'), p2=('ha_p2', 'sum'), forest=('forest_ha', 'sum')).reset_index()
Qd['burnt'] = Qd.ha + Qd.p1 + Qd.p2
base = Qd.groupby('key').agg(forest_ha=('forest', 'max'), burnt_ha_yr=('burnt', 'mean')).reset_index(); base['division'] = base.key.map(nm)
pt = P.groupby('division').agg(patches=('pid', 'size'), patch_ha=('forest_ha', 'sum'), line_km=('line_km', 'sum')).reset_index(); pt['division'] = pt.division.str.replace('_', ' ')
base = base.merge(pt, on='division', how='left').fillna({'patches': 0, 'patch_ha': 0, 'line_km': 0})
base['burnt_pct_of_forest'] = 100 * base.burnt_ha_yr / base.forest_ha

def divtab(code):
    d = DV[DV.programme == code].copy(); d['division'] = d.division.str.replace('_', ' ')
    d = d.merge(base[['division', 'forest_ha', 'burnt_ha_yr']], on='division', how='left')
    d['pct_of_division_burnt'] = 100 * d.benefit_total / d.burnt_ha_yr
    d['cost_lakh'] = d.cost_rs / 1e5
    d = d.sort_values('benefit_total', ascending=False)
    cols = ['division', 'burnt_ha_yr', 'patches_burnt', 'ha_burnt', 'boundary_km', 'block_lines_km', 'patches_lined', 'cut_km', 'saved_outside', 'saved_lines', 'converted', 'benefit_total', 'pct_of_division_burnt', 'cost_lakh']
    hdr = {'division': 'division', 'burnt_ha_yr': 'forest burnt now, ha/yr', 'patches_burnt': 'patches to burn', 'ha_burnt': 'ha to burn', 'boundary_km': 'edge boundary km (inferred)',
           'block_lines_km': 'block lines km', 'patches_lined': 'patches with breaks only', 'cut_km': 'break km', 'saved_outside': 'ha/yr stopped outside', 'saved_lines': 'ha/yr saved by breaks',
           'converted': 'ha/yr cool-burnt instead', 'benefit_total': 'total ha/yr', 'pct_of_division_burnt': '% of division burning', 'cost_lakh': 'Rs lakh/yr'}
    return tbl(d[cols].rename(columns=hdr), fmt={'% of division burning': lambda v: f'{v:.0f}%', 'Rs lakh/yr': lambda v: f'{v:.1f}', 'edge boundary km (inferred)': lambda v: f'{v:.0f}', 'block lines km': lambda v: f'{v:.0f}', 'break km': lambda v: f'{v:.0f}'}, cls='small')

# programme table
pr = PR.copy(); pr['burn_set'] = pr.burn_set.str.replace('first ', 'burn the first ').replace({'all 419k ha': 'burn all 419k ha', 'lines only, all 4,986 km': 'lines only (no burning), all 4,986 km'})
pcols = {'burn_set': 'programme', 'patches_burnt': 'patches burnt', 'ha_burnt': 'ha burnt each Feb', 'boundary_km': 'edge boundary km (inferred)', 'block_lines_km': 'block line km inside burnt patches',
         'cut_km': 'fire-break km elsewhere', 'saved_outside': 'ha/yr stopped outside the burnt patches', 'saved_lines': 'ha/yr saved by the breaks', 'saved_total': 'forest ha/yr not burnt at all',
         'pct_mp_burnt_saved': '% of MP burnt forest', 'converted': 'patch ha/yr turned into Feb cool burns', 'benefit_total': 'total ha/yr touched', 'pct_mp_burnt_benefit': '% of MP burnt forest ',
         'cost_crore': 'Rs crore/yr', 'rs_per_ha_saved': 'Rs per ha not burnt', 'rs_per_ha_benefit': 'Rs per ha touched'}
ptab = tbl(pr[list(pcols)].rename(columns=pcols), fmt={'% of MP burnt forest': pct, '% of MP burnt forest ': pct, 'Rs crore/yr': lambda v: f'{v:.1f}', 'edge boundary km (inferred)': lambda v: f'{v:,.0f}'}, cls='small')

# big fires by start
pv = BF.pivot(index='size', columns='start', values='forest_ha_per_yr').reindex(['<10', '10-50', '50-200', '200-500', '500-1000', '1000+'])
order = ['burn set 25k', '25-50k', '50-100k', '100-200k', 'rest of tr3', 'outside patches']; pv = pv[order].fillna(0); pv['all'] = pv.sum(1)
pv.index = [f'{s} ha' for s in pv.index]; pv.loc['all sizes'] = pv.sum(); pv = pv.reset_index().rename(columns={'index': 'fire size (forest ha)'})
pvn = BF.pivot(index='size', columns='start', values='fires_per_yr').reindex(['<10', '10-50', '50-200', '200-500', '500-1000', '1000+'])[order].fillna(0); pvn['all'] = pvn.sum(1)
pvn.index = [f'{s} ha' for s in pvn.index]; pvn.loc['all sizes'] = pvn.sum(); pvn = pvn.reset_index().rename(columns={'index': 'fire size (forest ha)'})

# clock table
ag = None
# burn-date table
c6 = C6[np.isclose(C6.treated_ha, 99660.96, atol=5)][['burn_date', 'outside_ha_stopped_per_100ha', 'outside_ha_stopped', 'inside_ha_prevented']]
c6.columns = ['burn date (100k ha treated)', 'outside ha stopped per 100 ha', 'outside ha/yr stopped', 'inside ha/yr converted']
# sizes by fortnight
SZ['period'] = pd.cut(SZ.doy, [45, 59, 74, 90, 105, 121, 170], labels=['15-28 Feb', '1-15 Mar', '16-31 Mar', '1-15 Apr', '16-30 Apr', 'May-Jun'])
sz = SZ.groupby('period', observed=True).agg(fires=('ha', 'size'), median_ha=('ha', 'median'), over50=('ha', lambda s: 100 * (s >= 50).mean()), over200=('ha', lambda s: 100 * (s >= 200).mean())).reset_index()
sz.columns = ['fire started in', 'fires 2017-25', 'median ha', '% reaching 50 ha', '% reaching 200 ha']
# scar dataset by year
E = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/mp_events.csv', usecols=['event_id', 'acq_date', 'forest'])
Hs = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/scars_mp_hist.csv', usecols=['event_id', 'status'])
E['year'] = E.acq_date.str[:4].astype(int); Mx = E[E.forest].merge(Hs, on='event_id', how='left')
yr = Mx.groupby('year').agg(fires=('event_id', 'size'), checked=('status', lambda s: 100 * s.notna().mean()), scar=('status', lambda s: 100 * s.isin(['scar', 'scar_faint']).mean())).reset_index()
yr = yr.merge(Qd.groupby('year').burnt.sum().rename('burnt_forest_ha').reset_index(), on='year')
yr.columns = ['season', 'forest fire events (VIIRS/MODIS, scar-dated)', '% checked for a scar', '% with a scar', 'burnt forest ha (scars)']
# top patches list
top = P[P.cum_ha <= 25000].sort_values('rank')[['rank', 'division', 'patch', 'forest_ha', 'burnt_share_per_season_2022_25', 'core_all5', 'converted_ha_yr', 'outside_ha_yr', 'lines', 'line_km', 'boundary_km', 'lat', 'lon']]
top['division'] = top.division.str.replace('_', ' '); top['burnt_share_per_season_2022_25'] = (100 * top.burnt_share_per_season_2022_25).round(0)
top.columns = ['rank', 'division', 'patch no.', 'forest ha', '% burnt per season', 'all5 core', 'ha/yr cool-burnt', 'ha/yr stopped outside', 'lines', 'line km', 'edge km (inf.)', 'lat', 'lon']
# appendix base table (all divisions)
ap = base.sort_values('burnt_ha_yr', ascending=False)[['division', 'forest_ha', 'burnt_ha_yr', 'burnt_pct_of_forest', 'patches', 'patch_ha', 'line_km']]
ap.columns = ['division', 'forest ha', 'burnt forest ha/yr 2017-25', '% of forest per year', 'repeat patches', 'patch forest ha', 'practical line km']
# checks after the plan (control_burning.md sections 10-14)
D12 = pd.read_csv(SC + 'code/control_burn/out/cb12_displace.csv'); AU = pd.read_csv(SC + 'code/control_burn/out/cb14_audit.csv'); ES = pd.read_csv(SC + 'code/control_burn/out/cb14_escape_summary.csv'); RF = pd.read_csv(SC + 'code/control_burn/out/cb16_refresh.csv')
au = AU[(AU.split == 'all') & AU.period.isin(['15-28 Feb', '1-15 Mar', '16-31 Mar', '1-15 Apr', '16-30 Apr'])][['period', 'fires', 'scar_seen', 'faint', 'median_scar_ha']]
aus = AU[(AU.split == 'sal_div') & AU.period.isin(['15-28 Feb', '1-15 Mar', '16-31 Mar'])].pivot(index='period', columns='sal_div', values='scar_seen').reindex(['15-28 Feb', '1-15 Mar', '16-31 Mar']).reset_index()
au.columns = ['fire started', 'fires 2017-25', 'scar seen', 'of which faint', 'median scar ha']
es = ES[ES.per.isin(['15-28 Feb', '1-15 Mar', '16-31 Mar'])][['per', 'fires', 'median_ha', 'left_patch_over_10ha', 'over_50_out', 'over_200_out', 'mean_out_ha']]
es.columns = ['fire started in a patch', 'fires 2017-25', 'median forest ha', 'left the patch (10+ ha outside)', '50+ ha outside', '200+ ha outside', 'mean ha outside']
rf = RF[['rule', 'forest_ha', 'burnt_ha_per_100ha_selected', 'share_of_2024_25_burnt_forest_on_set']].copy(); rf.columns = ['repeat rule (tested on 2024-25)', 'forest ha selected', 'burnt ha per 100 ha selected per year', 'share of 2024-25 burnt forest on the set']
d12 = D12[D12.early.str.contains('gap') & D12.term.isin(['own square', 'displaced to rings per early ha', 'net per early ha (own + 8 x ring 1 + 16 x ring 2)'])][['term', 'slope', 'lo', 'hi']]; d12.columns = ['15-28 Feb burning, two-week gap', 'later ha per early ha', 'low', 'high']
# crews
crew_days_S3 = s3.ha_burnt / 15; crews_S3 = crew_days_S3 / 12; crew_days_S5 = s5.ha_burnt / 15; crews_S5 = crew_days_S5 / 12

css = """
@page { size: A4; margin: 16mm 14mm 16mm 14mm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10.2pt; line-height: 1.38; color: #111; }
h1 { font-size: 22pt; margin: 0 0 6pt 0; } h2 { font-size: 15pt; margin-top: 18pt; border-bottom: 1.5px solid #7f0000; padding-bottom: 2pt; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 12pt; page-break-after: avoid; }
table.t { border-collapse: collapse; margin: 6pt 0 10pt 0; font-size: 8.6pt; page-break-inside: auto; }
table.t th { background: #f1e3dc; text-align: left; padding: 3pt 5pt; border-bottom: 1px solid #999; vertical-align: bottom; }
table.t td { padding: 2.5pt 5pt; border-bottom: 1px solid #ddd; white-space: nowrap; }
table.small { font-size: 7.6pt; } table.wrap td { white-space: normal; vertical-align: top; } table.small td, table.small th { padding: 2pt 3.5pt; }
figure { margin: 8pt 0 10pt 0; page-break-inside: avoid; text-align: center; } figcaption { font-size: 8.5pt; color: #444; margin-top: 3pt; text-align: left; }
.box { background: #faf4ef; border-left: 4px solid #7f0000; padding: 6pt 10pt; margin: 8pt 0; }
.inf { color: #8a4b00; font-size: 8pt; font-weight: bold; } .pb { page-break-before: always; }
.cover { height: 240mm; display: flex; flex-direction: column; justify-content: center; }
.cover h1 { font-size: 30pt; } .cover p { font-size: 12pt; color: #333; }
ul, ol { margin-top: 2pt; } li { margin-bottom: 2pt; }
.two { column-count: 2; column-gap: 18pt; }
"""
today = dt.date.today().strftime('%d %B %Y')
H = [f"<html><head><meta charset='utf-8'><title>Fire lines and control burning together, Madhya Pradesh</title><style>{css}</style></head><body>"]
H.append(f"""<div class='cover'><h1>Fire lines and control burning, together</h1>
<p style='font-size:16pt'>A plan for the forests of Madhya Pradesh, built from nine seasons of satellite burn scars</p>
<p>Terrain-following fire lines on nalas, crests, tracks and forest edges; late-February block burning of the ground that burns every year;
how the two fit, where to do each, in which order, and how much forest it keeps out of the fire.</p>
<p>All MP, 82 forest divisions with scar data, seasons 2017-2025 (153,817 forest fires, 30 m burn outlines). Every saving quoted is measured on the held-out seasons 2022-25 unless marked otherwise.</p>
<p>{today}. Research thread, FSI scouting. Source note: <code>ratapani/fsi/scouting/joint_plan.md</code>; data and code <code>code/joint_plan/</code>.</p></div>""")

# ---------- summary ----------
H.append(f"""<h2 class='pb'>Summary</h2>
<div class='box'>
<p><b>The two tools sit on the same ground.</b> Of the 4,986 km of practical fire lines, {100 * km_in / km_all:.0f}% ({km_in:,.0f} km) run inside the 3,867 repeat-burn patches that are also the places to control-burn. They are not two programmes to add up; they are one programme with two uses for the same cleared lines: as the boundaries of the February burn blocks where a patch is burnt, and as fire breaks where it is not.</p>
<p><b>The rule.</b> Burn every repeat patch that can be burnt, between 15 and 28 February, every year, block by block inside its practical lines. Where a patch cannot be burnt (steep ground, mahua and tendu collection, wildlife, no crew), keep the same lines as fire breaks. Put fire watchers on the ranked squares from 8 March. Lines are cleared in December-January, before the burns.</p>
<p><b>What it saves.</b> Forest that is not burnt at all tops out at about <b>{s5.saved_total / 1000:.0f} thousand ha a year (6% of MP's {MP_BURNT / 1000:.0f} thousand ha of burnt forest)</b>, and most of that is reached by the first programme: burn the first 100 thousand ha of patches (465 patches in 55 divisions) and keep breaks through the rest, for <b>{s3.saved_total / 1000:.0f} thousand ha not burnt</b> plus <b>{s3.converted / 1000:.0f} thousand ha</b> of April wildfire turned into cool February burns: <b>{s3.benefit_total / 1000:.0f} thousand ha a year, {s3.pct_mp_burnt_benefit:.0f}% of MP's burnt forest, for about Rs {s3.cost_crore:.1f} crore a year</b> (lines at the CAMPA rate, burning at crew wages). Burning all 419 thousand ha of patches touches {s5.benefit_total / 1000:.0f} thousand ha a year ({s5.pct_mp_burnt_benefit:.0f}%) for Rs {s5.cost_crore:.0f} crore.</p>
<p><b>Checked since.</b> Displacement to neighbouring ground is small and uncertain; the burnt blocks can be audited from the next satellite pass outside the sal belt; every patch carries an escape flag from its own record; the patch map must be rebuilt yearly (section 7).</p>
<p><b>Why the ceiling.</b> The repeat patches carry {100 * share_ha_on_patch:.0f}% of MP's burnt forest and start {100 * share_big_in_tr3:.0f}% of its fires over 200 ha; the other {100 - 100 * share_ha_on_patch:.0f}% burns on ground that burns once in 28 years, where neither a line nor a burn can be placed in advance. That ground is the live-alert and watcher job, not a prevention job.</p>
</div>
<h3>The programme sizes</h3>{ptab}
<p>Columns: "stopped outside" are forest ha outside a burnt patch that fires starting inside it would have burnt (x 0.70 protection); "saved by the breaks" is the held-out saving of the practical lines in patches that are not burnt; "cool-burnt instead" is the patch's own wildfire hectares (a floor: only fires starting inside are counted) moved to a planned February burn. Cost: lines Rs 1,356 per km (CAMPA); block burning Rs 120 per ha {I('crew of five at Rs 320 a day burning 10-20 ha of litter a day')}; the edge of a burnt patch needs a boundary where there is no natural barrier, {I('taken as 60% of the patch perimeter')}.</p>
{img(F30 + 'r30_fig4_frontier.png', 'Figure 1. What each programme size buys per year on the held-out seasons, against its yearly cost. Forest not burnt at all (blue) flattens at about 45 thousand ha; the hectares turned into cool burns (red) keep growing with the area burnt.', 78)}
""")

# ---------- 1 what the scars say ----------
H.append(f"""<h2 class='pb'>1. What the burn scars say about MP's fires</h2>
<p>Every VIIRS and MODIS fire detection in MP forest from 2017 to 2025 was checked against 30 m Sentinel-2 and Landsat imagery before and after it, and the burnt outline drawn (the burn-scar thread; <code>fire-alert-scars/mp/README.md</code>). The outlines, not the heat points, are the ground truth for everything below: how much forest burns, where, when, how big the fires get, and which ground burns year after year.</p>
{tbl(yr, fmt={'% checked for a scar': lambda v: f'{v:.0f}%', '% with a scar': lambda v: f'{v:.0f}%'})}
<p>Burnt forest is counted once per cell per season on a 60 m lattice (WorldCover tree and shrub cover), so overlapping fires are not double-counted; the mean over the nine seasons is {MP_BURNT / 1000:.0f} thousand ha a year, of 8.4 million forest ha (3.6% a season).</p>
<h3>1.1 Size: a few big fires are most of the burning</h3>
<p>Fires of 200 ha and more are 8% of fires and 57% of burnt forest. The share grows through the season: a fire starting in late February reaches 200 ha 7% of the time, one starting in late March 15%.</p>
{tbl(sz, fmt={'median ha': lambda v: f'{v:.0f}', '% reaching 50 ha': lambda v: f'{v:.0f}%', '% reaching 200 ha': lambda v: f'{v:.0f}%'})}
<h3>1.2 Timing: half the burning is in a fortnight</h3>
<p>46% of the season's burnt forest burns between 22 March and 4 April; 85% is burnt by mid-April. Teak litter is nearly all down by mid-March, and the fires follow it (control_burning.md, section 3).</p>
{img(F29 + 'r29_fig2_calendar.png', 'Figure 2. Burnt forest by week of the season, all MP, mean 2017-25, with the litter calendar. The planned-burn window (15-28 Feb) is before the litter peak and before the fires.', 80)}
<h3>1.3 Place: the ground that burns every year</h3>
<p>Cells burnt in three or more of the five seasons 2017-21, grouped into patches of at least 10 forest ha, give 3,867 repeat patches with 419 thousand forest ha in 74 divisions (the "tr3" patches). Over the nine seasons they burn 53% a season (the stricter "all5" cores, burnt 5 of 9 seasons, 63%), against 3.6% for forest in general; on the held-out seasons 2022-25 alone, after the selection on 2017-21, 37% (section 6 of the plan: the map goes stale and must be rebuilt every year). They carry {100 * share_ha_on_patch:.0f}% of MP's burnt forest and start {100 * share_big_in_tr3:.0f}% of its fires over 200 ha ({100 * share_big_ha_in_tr3:.0f}% of the big-fire hectares). Both tools in this plan live on these patches, because they are the only ground where a fire can be predicted a year ahead.</p>
{img(F30 + 'r30_fig7_bigfires.png', 'Figure 3. Burnt forest per year (2022-25) by fire size and by where the fire started: inside a repeat patch (coloured by the burn tier the patch falls in) or outside. Fires that start outside the patches are the large grey bars; prevention on the patches cannot reach them.', 80)}
{tbl(pv.rename(columns={'burn set 25k': 'started in: first 25k ha', '25-50k': '25-50k ha', '50-100k': '50-100k ha', '100-200k': '100-200k ha', 'rest of tr3': 'rest of patches', 'outside patches': 'outside the patches', 'all': 'all fires'}), cls='small')}
<p>Table: burnt forest ha per year (2022-25). The same by number of fires per year:</p>
{tbl(pvn.rename(columns={'burn set 25k': 'started in: first 25k ha', '25-50k': '25-50k ha', '50-100k': '50-100k ha', '100-200k': '100-200k ha', 'rest of tr3': 'rest of patches', 'outside patches': 'outside the patches', 'all': 'all fires'}), fmt={c: (lambda v: f'{v:,.1f}') for c in pvn.columns if c != 'fire size (forest ha)'}, cls='small')}
""")

# ---------- 2 lines ----------
H.append(f"""<h2 class='pb'>2. Tool one: practical fire lines along the terrain</h2>
<p>A fire line is a cleared strip a fire cannot cross without help. From MP's own fires (research/fire-continuity), a fire's chance of stopping at a road is 3.3x, at the forest edge 2.1x, at cropland 1.8x the chance in open forest; a built line in the compartment record holds 70% of the time (fire_lines_v2.md, 2022-25). The lines here are drawn for the repeat patches only, as cuts that split a patch into compartments so that a fire starting in one does not take the whole patch, and each cut is the cheapest path across the compartment on a cost surface that prefers existing roads and tracks, nala lines, the forest edge and ridge crests, and doubles the cost of running up a 20% grade. Of the 4,986 km, 21% lies on nala lines, 15% on ridge crests, 3% on the forest edge, 1% on roads or tracks; 59% still crosses forest interior, along contours, because inside these patches that is all there is (the DEM is 150 m; crews should snap each stretch to the nearest nala or crest it cannot see). 10% of the length is steeper than 15%.</p>
<h3>2.1 Held out: what a kilometre saves</h3>
<p>Cuts chosen on 2017-21 and scored on 2022-25 with a 70% hold per crossing (the measured value for built lines):</p>
<table class='t'><tr><th>take the first</th><th>forest ha saved per km per year, held out</th><th>% of MP burnt forest</th><th>patches that paid held out</th></tr>
<tr><td>250 km</td><td>12.5</td><td>0.4%</td><td>88%</td></tr><tr><td>500 km</td><td>10.4</td><td>0.7%</td><td>83%</td></tr><tr><td>1,000 km</td><td>9.9</td><td>1.4%</td><td>87%</td></tr>
<tr><td>2,000 km</td><td>8.1</td><td>2.3%</td><td>89%</td></tr><tr><td>5,000 km</td><td>5.8</td><td>4.0%</td><td>78%</td></tr></table>
<p>Lines saturate: the first 500 km are worth twice the next 4,500 per kilometre. Following the terrain costs about 17% of the saving at 500 km and nothing from 1,000 km up, against straight cuts. The final statewide set (7,704 lines, 4,986 km, 753 patches, 56 divisions) was drawn on all nine seasons; in this plan its in-sample saving is scaled to the held-out level by tier (0.49 at the first 500 km, 0.57, 0.60, 0.68 at 5,000 km).</p>
{img(F28 + 'r28_fig1_curves.png', 'Figure 4. Held-out forest ha saved per km per year against the line budget, by patch set, objective and hold chance (fire_lines_v2.md).', 75)}
{img(F28 + 'r28_fig2_map_practical.png', 'Figure 5. The practical line set, all MP, coloured by statewide km tier.', 95)}
{img(F28 + 'r28_fig3_divisions_practical.png', 'Figure 6. The eight divisions with the most line km: each line in its patch.', 95)}
""")

# ---------- 3 burning ----------
H.append(f"""<h2 class='pb'>3. Tool two: control burning the repeat patches in late February</h2>
<p>Burnt ground cannot burn again until the litter is back. Measured from the VIIRS heat points over 82 divisions (a second burn leaves no second scar, so heat is the only way to see it), ground burnt two to four weeks earlier gets 0.42x the fire of unburnt forest in the same 5 km square and week, four to six weeks 0.22x, and about 0.20x from then to the end of the season; deep inside a block (180 m from any unburnt cell) protection is near total after four weeks. A February, March or April burn protects alike. The protection is one season: ground burnt last season gets 1.8x more fire this season, not less, because one monsoon puts the litter back. At the landscape scale, each forest ha burnt between 15 February and 15 March takes 0.19 ha (0.12-0.26) off the rest of the season in the same square, after square and division-season fixed effects; without them the sign flips, which is why plain before/after comparisons mislead.</p>
{img(F29 + 'r29_fig1_clock.png', 'Figure 7. The fuel clock: fire on burnt ground relative to unburnt forest nearby, by weeks since the burn and by month of the burn (control_burning.md, section 2).', 80)}
<h3>3.1 Only ground that burns anyway is worth burning</h3>
<p>A control burn on ordinary forest (3.6% chance of burning) prevents 0.03 ha of wildfire per ha burnt and the fuel is back next year. On a repeat patch (37% a season held out, 53-63% over nine seasons) it prevents or converts 0.3-0.6 ha per ha burnt, plus 10-13 forest ha outside the patch per 100 ha burnt, because the fires that start on these patches spread out of them. <b>The programme is the patches, nothing else.</b> Burning strips of ordinary forest "to reduce fuel load" is not supported by the record.</p>
<h3>3.2 Burn date</h3>
{tbl(c6, fmt={'outside ha stopped per 100 ha': lambda v: f'{v:.1f}'})}
<p>Burning on 15 February prevents 70% of the later burning of the block, 1 March 68%, 15 March 55%, 1 April 34%. Fires lit in 15-28 February are also cooler (VIIRS fire power 4.6 MW against 6.1-7.3 MW later) and stay smaller (7% reach 200 ha against 15% in late March), so a planned burn that escapes in February does less harm than the wildfire the same ground gets in late March.</p>
{img(F29 + 'r29_fig3_map.png', 'Figure 8. Every repeat patch, coloured by the burn tier it falls in when ranked on benefit per 100 ha treated (held out 2022-25).', 95)}
{img(F29 + 'r29_fig4_divisions.png', 'Figure 9. The eight divisions with the most repeat-patch area.', 95)}
""")

# ---------- 4 together ----------
ex = P[(P.division == 'Obedullahganj (Ratapani)') & (P.cum_ha <= 100000)].sort_values('line_km', ascending=False).iloc[0]
H.append(f"""<h2 class='pb'>4. Putting the two together</h2>
<h3>4.1 They compete for the same ground</h3>
<p>Joining the two maps: {int(Ln.in_tr3.sum()):,} of the 7,703 practical lines ({km_in:,.0f} of {km_all:,.0f} km, {100 * km_in / km_all:.0f}%) run inside a repeat patch, and {int((P.lines > 0).sum())} of the 3,867 patches carry lines. A patch that is burnt in February does not need its lines as fire breaks that season: the patch cannot carry a March fire. So the saving of a line and the saving of a burn on the same patch cannot be added. Under the full burning programme the lines' own held-out saving inside burnt patches ({s5.forgone_line_saving_in_burnt / 1000:.0f} thousand ha a year) is forgone, and only {s5.cut_km:,.0f} km of lines remain as breaks.</p>
<h3>4.2 But a burn needs the lines</h3>
<p>A block burn is only safe inside a boundary. The practical lines are exactly that: they already follow the nalas, crests, tracks and edges inside the patch, they split it into blocks of a size a crew can burn in a day, and they are cleared in December-January, before the litter peak. So in the combined plan every line inside a patch to be burnt becomes a <b>burn-block boundary</b>, and the patch edge gets a boundary where it has no natural barrier ({I('60% of the perimeter')}; the rest is a nala, road, crop or forest edge). The line programme and the burn programme share one set of cleared lines.</p>
<div class='box'><b>The coordination rule, patch by patch</b>
<ol>
<li><b>Can the patch be burnt?</b> (crew available 15-28 Feb; not too steep for a crew to hold; no mahua or tendu collection in the window; no wildlife objection.) The record cannot tell this; the range officer can.</li>
<li><b>If yes: burn it, every year, 15-28 February</b>, one block a day, from the downwind block inward, inside its practical lines; clear the lines and the edge boundary first. Count: the patch's own hectares turned into a cool burn, plus 10-13 forest ha stopped outside per 100 ha, every year.</li>
<li><b>If no: keep the practical lines as fire breaks</b> (re-cleared every January). Count: the held-out line saving, 6-12 forest ha per km per year.</li>
<li><b>Never burn ground outside the patches</b>, and never put a line where no patch is: both are worth 0.03 ha per ha and nothing next year.</li>
<li><b>From 8 March, fire watchers on the ranked squares</b> (section 5.3): the burnt patches no longer need them; the once-in-28-years ground does.</li>
</ol></div>
{img(F30 + 'r30_fig3_example.png', f'Figure 10. A worked example in Ratapani: patch {int(ex.patch)} ({ex.forest_ha:,.0f} forest ha, burns {100 * ex.burnt_share_per_season_2022_25:.0f}% of itself a season) with its practical lines coloured by the ground they follow. The lines are the burn-block boundaries; the patch edge needs about {ex.boundary_km:.0f} km of boundary where no natural barrier runs.', 85)}
<h3>4.3 The season plan</h3>
{img(F30 + 'r30_fig6_calendar.png', 'Figure 11. The work plan against the burning calendar: lines first (December-January), burns in the fortnight before the fires (15-28 February), escape patrol, watchers through the peak (8 March to 25 April, 84% of burning), live alerts all season.', 88)}
<table class='t wrap'><tr><th>when</th><th>what</th><th>who</th><th>why then</th></tr>
<tr><td>December-January</td><td>clear the practical lines (block boundaries and breaks) and the edge boundaries of the patches to be burnt</td><td>line gangs, by range</td><td>after the rains, before litter fall; a line cleared in January is clean for the February burn</td></tr>
<tr><td>1-14 February</td><td>re-clear lines where early litter has fallen; brief burn crews; fix block order per patch (downwind first)</td><td>range officer, crews</td><td>the burn window opens 15 Feb</td></tr>
<tr><td>15-28 February</td><td>burn the patches block by block, afternoon lighting against the wind, one block per crew per day</td><td>burn crews of five, one per 10-20 ha a day</td><td>litter is 60% down, fires are cooler and smaller than in March; 70% of the block's later burning is prevented</td></tr>
<tr><td>1-20 March</td><td>patrol burnt patches for re-lights and escapes; mop up unburnt pockets</td><td>same crews</td><td>the 2-4 week ratio is 0.42, not zero: edges and unburnt pockets can still carry fire</td></tr>
<tr><td>8 March-25 April</td><td>fire watchers on the ranked 5 km squares</td><td>4,730 watchers (one per square-week)</td><td>84% of burning falls in this window; the ranked squares cover 76% of it</td></tr>
<tr><td>whole season</td><td>live alerts and the 2-day list; satellite check of each burnt block (scar seen in the next clear pass)</td><td>control room</td><td>the fires outside the patches ({100 - 100 * share_ha_on_patch:.0f}% of burning) can only be caught, not prevented</td></tr></table>
""")

# ---------- 5 how much ----------
d3t = divtab('S3'); d5t = divtab('S5')
H.append(f"""<h2 class='pb'>5. How much forest it saves</h2>
<h3>5.1 Two kinds of saving</h3>
<p>The honest answer has two parts, and they should be kept apart.</p>
<ul><li><b>Forest not burnt at all</b>: the hectares outside a burnt patch that fires starting inside it would have reached, and the hectares a fire break holds back. This is what "area saved" usually means. It tops out at about <b>{s5.saved_total / 1000:.0f} thousand ha a year (6% of MP's burnt forest)</b> whichever mix of the two tools is used, because both act on the same {int(P.forest_ha.sum() / 1000)} thousand ha of patches and the fires that leave them.</li>
<li><b>Forest burnt cool in February instead of hot in late March</b>: the patch's own hectares. This is not forest saved from fire; it is the same ground burnt on purpose, six weeks earlier, 30% cooler, in fires a third the size, with crews standing at the line. Whether that is worth having depends on what a February burn does to regeneration and wildlife compared with the April wildfire the ground gets now; the satellite record cannot say. Up to <b>{s5.converted / 1000:.0f} thousand ha a year</b> (15% of MP's burnt forest) can be moved this way.</li></ul>
<p>Together, the full programme touches <b>{s5.benefit_total / 1000:.0f} thousand ha a year, {s5.pct_mp_burnt_benefit:.0f}% of MP's burnt forest</b>; the first programme (100 thousand ha burnt plus breaks elsewhere) touches {s3.benefit_total / 1000:.0f} thousand ha ({s3.pct_mp_burnt_benefit:.0f}%), of which {s3.saved_total / 1000:.0f} thousand ha is forest that does not burn.</p>
<h3>5.2 Cost per hectare</h3>
<p>Lines alone are the cheapest way to keep a hectare out of the fire: Rs {L.rs_per_ha_saved:.0f} per ha not burnt at the full 4,986 km (Rs {L.cost_crore:.2f} crore a year, {L.saved_total / 1000:.0f} thousand ha). Adding the burning of the first 25 thousand ha raises the forest not burnt to {s1.saved_total / 1000:.0f} thousand ha at Rs {s1.rs_per_ha_saved:.0f} per ha; the first 100 thousand ha, {s3.saved_total / 1000:.0f} thousand ha at Rs {s3.rs_per_ha_saved:.0f} per ha not burnt, or Rs {s3.rs_per_ha_benefit:.0f} per ha touched; the full programme Rs {s5.rs_per_ha_saved:,.0f} per ha not burnt, Rs {s5.rs_per_ha_benefit:.0f} per ha touched. Burning is the expensive way to keep forest out of the fire and the only way to change what happens to the patches themselves.</p>
<p>{I(f'Crews: at 15 ha per crew-day, the first programme is {crew_days_S3:,.0f} crew-days in a 12-working-day window, about {crews_S3:,.0f} crews of five ({5 * crews_S3:,.0f} people) statewide for the fortnight; the full programme {crew_days_S5:,.0f} crew-days, {crews_S5:,.0f} crews ({5 * crews_S5:,.0f} people). MP already fields about 4,730 fire watchers for the season, so the first programme is within the existing seasonal workforce if the watchers start after the burns.')}</p>
<h3>5.3 Where: the first programme by division</h3>
<p>The first programme burns the 465 patches with the highest benefit per 100 ha (the first 100 thousand ha by that rank; 55 divisions) and keeps the practical lines as breaks in the 477 other patches that have them. Divisions ordered by hectares touched per year:</p>
{img(F30 + 'r30_fig5_divisions_bar.png', 'Figure 12. The first programme, 25 divisions with the most to gain per year: forest stopped outside burnt patches, forest saved by breaks, and patch hectares turned into February cool burns.', 80)}
{d3t}
{img(F30 + 'r30_fig1_map_mp.png', 'Figure 13. The first programme on the map: patches to burn every year by tier (reds), patches kept as fire-break ground (blue), the other repeat patches for later years (grey), and every practical line in its role.', 100)}
{img(F30 + 'r30_fig2_divisions.png', 'Figure 14. The twelve divisions with the most to gain under the first programme, each with its patches and lines.', 100)}
<h3 class='pb'>5.4 The full programme by division (all 419 thousand ha of patches burnt)</h3>
{d5t}
<h3>5.5 The watcher layer</h3>
<p>The burnt patches free the watchers for the ground that cannot be treated. Ranking 5 km forest squares by week on 2017-21 burning and placing one watcher per square-week, the top 30,000 square-weeks cover 76% of 2022-25 burning, against 43% if the same 4,730 watchers are spread evenly over every forest square for two weeks (<code>code/control_burn/out/cb9_squares.csv</code> has the ranked list with the peak weeks per square).</p>
{tbl(W9.rename(columns={'window_start': '49-day window from', 'window_end': 'to', 'share_of_burnt_forest': 'share of burnt forest'}), fmt={'share of burnt forest': lambda v: f'{100 * v:.0f}%'})}
{tbl(B9.rename(columns={'plan': 'watcher plan', 'watcher_weeks': 'watcher-weeks', 'share_2022_25': 'share of 2022-25 burning covered'}), fmt={'share of 2022-25 burning covered': lambda v: f'{100 * v:.0f}%'})}
""")

# ---------- 6 sequence ----------
H.append(f"""<h2 class='pb'>6. Order of work: a three-year build-up</h2>
<table class='t wrap'><tr><th>year</th><th>burn</th><th>lines</th><th>what to measure</th></tr>
<tr><td>Year 1</td><td>the first 25 thousand ha (160 patches, 42 divisions; the all5 cores first), 15-28 Feb</td><td>clear the lines in those patches as block boundaries ({s1.block_lines_km:,.0f} km) and their edges (~{s1.boundary_km:,.0f} km); clear the first 1,000 km of breaks elsewhere by statewide rank</td><td>for every burnt block: the scar in the next clear pass (did it burn, how completely), any re-light or escape; for every break: fires that reached it and stopped</td></tr>
<tr><td>Year 2</td><td>the first 100 thousand ha (465 patches, 55 divisions), if year 1's blocks show the 0.2x re-burn ratio and escapes stayed under the February wildfire sizes</td><td>all lines in burnt patches ({s3.block_lines_km:,.0f} km) and edges (~{s3.boundary_km:,.0f} km); breaks in the rest ({s3.cut_km:,.0f} km)</td><td>division-level burnt forest against 2017-25 with the square fixed-effects test (control_burning.md, section 4), not a plain before/after</td></tr>
<tr><td>Year 3 on</td><td>every patch a crew can hold, up to all 419 thousand ha; re-rank the patches each year on the latest five seasons (a patch that stops burning drops out, new repeat ground comes in; worth about 13% more per hectare, section 7.5)</td><td>re-clear every January; lines in patches that cannot be burnt stay as breaks</td><td>the ceiling: forest not burnt should approach 45 thousand ha a year; if it does not, the leakage is in escapes or in ignitions moving to the next block</td></tr></table>
<h3>6.1 Inside one patch</h3>
<ol><li>Walk the practical lines with the map (GeoJSON in the files below); snap each stretch to the nearest nala, crest or track the 150 m DEM did not see; clear the edge boundary where the patch has no natural barrier.</li>
<li>Number the blocks; the day's block is the one downwind; light in the afternoon from the downwind line back into the wind, the crew on the line.</li>
<li>Do not leave unburnt pockets: the clock's 2-4 week ratio of 0.42 (not 0.05) is partly pockets and edges that carry a later fire.</li>
<li>Check the block in the next clear satellite pass (the live-alert system draws the scar); re-burn pockets before 15 March.</li></ol>
<h3>6.2 What makes a patch a "cannot burn"</h3>
<p>Steep ground (the line table gives the km steeper than 15% per line), a village or mahua and tendu collection inside the window, a tiger reserve's own rules, or simply no crew that fortnight. These patches keep their lines as breaks and move to the watcher list. The plan does not lose much: a lined patch saves 6-12 ha per km, a burnt one 10-13 outside ha per 100 ha plus its own conversion, so the forest-not-burnt total barely moves (section 5.1) when a patch switches from burn to lines.</p>
""")

# ---------- 7 checks ----------
H.append(f"""<h2 class='pb'>7. Five checks run on the plan (20 October)</h2>
<p>After the plan was drawn, five questions it raised were tested on the same record (control_burning.md, sections 10-14).</p>
<h3>7.1 Does an early burn push the fire to the next block?</h3>
<p>Later burning (16 Mar on) in every 5 km square against early burning in the square, its 8 neighbours (5-10 km) and the 16 beyond (10-15 km), with square and division x season fixed effects, fires counted whole by their start date. For burns in the programme window the leak to the neighbours is small and uncertain; it is not the large effect that would make the programme pointless. (Burning in early March does go with more late-March fire next door, +0.5 ha per ha, but that is a shared hot fortnight, not fires moving.)</p>
{tbl(d12, fmt={'later ha per early ha': lambda v: f'{v:+.2f}', 'low': lambda v: f'{v:+.2f}', 'high': lambda v: f'{v:+.2f}'})}
<h3>7.2 Why does burnt ground protect 0.05x in some divisions and 0.7x in others?</h3>
<p>It tracks nothing in the record: forest type, sal share, leaf-fall date, fire density, fire size, scar detection, every correlation under 0.22 across 46 divisions. Pooled by dominant type the ratio is 0.25-0.37 everywhere. Use the statewide clock in every division; the sal-belt worry (late litter re-fuelling a February burn) cannot be tested because sal has almost no February fire.</p>
<h3>7.3 Can the burnt blocks be audited from orbit?</h3>
{tbl(au, fmt={'scar seen': lambda v: f'{100 * v:.0f}%', 'of which faint': lambda v: f'{100 * v:.0f}%', 'median scar ha': lambda v: f'{v:.0f}'})}
<p>A late-February burn is seen as a scar in the next clear pass 89% of the time, a late-March fire 93%. The exception is the sal belt: in divisions with 30%+ sal, February burns show {100 * float(aus.loc[aus.period == '15-28 Feb', 'sal >= 30%'].iloc[0]):.0f}% of the time (March {100 * float(aus.loc[aus.period == '16-31 Mar', 'sal >= 30%'].iloc[0]):.0f}%), because sal still holds its canopy in February; there the burn-day heat point is the check. Everywhere else the department's hectares can be audited block by block from the next pass.</p>
<h3>7.4 Escape risk</h3>
{tbl(es, fmt={'left the patch (10+ ha outside)': lambda v: f'{100 * v:.0f}%', '50+ ha outside': lambda v: f'{100 * v:.0f}%', '200+ ha outside': lambda v: f'{100 * v:.0f}%', 'mean ha outside': lambda v: f'{v:.0f}', 'median forest ha': lambda v: f'{v:.0f}'})}
<p>These are unplanned fires with nobody at the line, the worst case for a planned burn. Every patch now carries a flag from its own nine-season record (in <code>j1_patches.csv</code> and the GeoJSON): of the 465 first-programme patches, 182 have had a fire run 200+ ha outside them, 130 a 50-200 ha run, 153 never over 50 ha. The high-flag patches get a real edge boundary and the first week of the window.</p>
{img(F30 + 'r30_fig8_escape.png', 'Figure 15. First-programme patches by escape record: where the edge boundary must be real before the burn.', 100)}
<h3>7.5 How fast the patch map goes stale</h3>
{tbl(rf, fmt={'burnt ha per 100 ha selected per year': lambda v: f'{v:.1f}', 'share of 2024-25 burnt forest on the set': lambda v: f'{100 * v:.0f}%'})}
<p>The patches burnt 66% of seasons in the years they were picked on and 37% in 2022-25; 85 thousand ha of new repeat ground appeared outside them (20% of their area), and some divisions cooled almost completely (Noradehi, South Betul, Barwah, Dindori, Indore, West Chhindwara) while Ratapani, Sehore, Umaria and Chhatarpur held. A map rebuilt on the latest five seasons burns 13% more per selected hectare than one five seasons old and picks a third less ground; last season alone is a poor rule. Rebuild the patch set every year on the latest five seasons (for 2027: 2022-26); every programme figure in this report already uses the held-out 37%, not the 66%.</p>
""")

# ---------- 8 limits ----------
H.append(f"""<h2>8. What this plan cannot promise</h2>
<ul>
<li><b>The 6% ceiling is real.</b> {100 - 100 * share_ha_on_patch:.0f}% of MP's burnt forest is on ground that does not burn every year. No line or planned burn can be placed on it in advance. That burning is reduced only by catching fires early (live alerts, 2-day list, watchers), which this plan funds by freeing the watchers from the burnt patches.</li>
<li><b>The conversion is not a saving.</b> The {s5.converted / 1000:.0f} thousand ha turned into February burns are still burnt. The record shows those burns are 30% cooler and a third the size; it shows nothing about teak regeneration, mahua, tendu or ground-nesting wildlife. That is a field question, outside this analysis.</li>
<li><b>Displacement.</b> Tested to 15 km (section 7.1): small and uncertain for February burns, between zero and the full own-square saving. Beyond 15 km, and for the first year of a real programme, unmeasured; the first-year scar checks settle it.</li>
<li><b>Costs are partly inferred.</b> The line rate is the CAMPA rate; the burning rate and the edge-boundary share are inferences marked as such. The per-hectare figures change with them, the ranking of patches and divisions does not.</li>
<li><b>Lines are held out, the set is not.</b> The held-out saving per km comes from lines chosen on 2017-21 and scored on 2022-25; the final line set was drawn on all nine seasons and scaled to the held-out level. Patches are ranked on 2017-21 and scored on 2022-25 throughout.</li>
<li><b>Per-division protection varies</b> (re-burn ratios 0.05-0.71 across divisions; the sal belt sheds litter late). The first-year scar checks will show where the clock runs differently.</li>
</ul>
""")

# ---------- appendices ----------
H.append(f"""<h2 class='pb'>Appendix A. Every division: forest, burning, patches and lines</h2>
<p>Burnt forest per year is the 2017-25 mean on the 60 m lattice; patches are the tr3 repeat patches; line km are the practical lines in the division.</p>
{tbl(ap, fmt={'% of forest per year': lambda v: f'{v:.1f}%', 'practical line km': lambda v: f'{v:,.0f}'}, cls='small')}
<h2 class='pb'>Appendix B. The first 25 thousand ha: the 160 patches to burn in year one</h2>
<p>Ranked on benefit per 100 ha treated (held out 2022-25). "all5 core" marks patches that also burnt 5 of 9 seasons. Lines and line km are the practical lines inside the patch (block boundaries); edge km is the inferred boundary need on the patch edge. Coordinates are the patch centroid (WGS84).</p>
{tbl(top, fmt={'% burnt per season': lambda v: f'{v:.0f}%', 'line km': lambda v: f'{v:.1f}', 'edge km (inf.)': lambda v: f'{v:.1f}', 'lat': lambda v: f'{v:.4f}', 'lon': lambda v: f'{v:.4f}', 'ha/yr cool-burnt': lambda v: f'{v:.0f}', 'ha/yr stopped outside': lambda v: f'{v:.0f}', 'forest ha': lambda v: f'{v:.0f}'}, cls='small')}
<h2 class='pb'>Appendix C. Files</h2>
<p>All under <code>/mnt/project-files/ratapani/fsi/scouting/</code>.</p>
<ul>
<li><b>This plan</b>: <code>joint_plan.md</code> (note), <code>report/joint_plan_mp.pdf</code>; code <code>code/joint_plan/j1_overlap.py</code> (overlap, patch values, programmes), <code>j2_fires.py</code> (every fire by start patch and size), <code>j3_figs.py</code>, <code>j4_pdf.py</code>.</li>
<li><b>Plan data</b>: <code>code/joint_plan/out/j1_patches.csv</code> and <code>.geojson</code> (every repeat patch: burn value, line value, boundary km, role under the first and full programmes), <code>j1_lines.csv</code> and <code>.geojson</code> (every practical line with its patch and role), <code>j1_programmes.csv</code>, <code>j1_by_division.csv</code> (every division under every programme size), <code>j2_fires.csv</code> (every scar fire 2017-25 with its start patch and tier), <code>j2_bigfires.csv</code>.</li>
<li><b>Lines</b> (fire_lines_v2.md, section 9): <code>code/fire_lines_v2/out/proposed_fire_lines_mp_practical.geojson</code> and <code>.csv</code>, <code>proposed_lines_by_division_practical.csv</code>; figures <code>figs_r28/</code>.</li>
<li><b>Control burning</b> (control_burning.md): <code>code/control_burn/out/control_burn_patches_mp.geojson</code> and <code>.csv</code>, <code>control_burn_by_division.csv</code>, the clock <code>cb2_age.csv</code>, calendar <code>cb3_weekly.csv</code>, sizes <code>cb3_sizes.csv</code>, leverage <code>cb5_leverage.csv</code>, design <code>cb6_design.csv</code>, watchers <code>cb9_squares.csv</code>, <code>cb9_windows.csv</code>, <code>cb9_budget.csv</code>; figures <code>figs_r29/</code>.</li>
<li><b>Burn scars</b>: <code>fire-alert-scars/mp/README.md</code>, <code>mp/out/mp_events.csv</code>, <code>scars_mp_hist.csv</code>, outlines via <code>mp/scripts/read_geom.py</code>; frozen reference <code>fire-alert-scars/reference/v2_2026-10-16/</code>.</li>
</ul>
<h2>Appendix D. Method in brief</h2>
<ul>
<li><b>Lattice.</b> 60 m cells (EPSG:32643), forest = WorldCover tree and shrub; each scar outline rasterised per fire with its start cells and day of burn.</li>
<li><b>Repeat patches.</b> Cells burnt in 3+ of the 5 seasons 2017-21 (tr3), 8-connected, at least 10 forest ha; all5 = 5+ of 9 seasons. Patch value: fires 2022-25 whose majority start cell is in the patch; their forest ha inside the patch (converted) and outside it (stopped), times 0.70 protection; ranked on benefit per 100 ha.</li>
<li><b>Lines.</b> Candidate cuts across each compartment as least-cost paths (roads 0.20, nalas 0.30, forest edge 0.40, open 0.50, crests 0.50, forest 1.00, grade penalty); greedy choice on the drop-best-year objective; scoring: a fire spreads again inside its own outline from its start, each line crossing stops it with chance 0.70; saved = forest ha of the outline beyond the line. Held out: chosen 2017-21, scored 2022-25.</li>
<li><b>Fuel clock.</b> VIIRS heat points on burnt cells relative to unburnt forest in the same division, season, 5 km square and week (indirect standardisation), bootstrap over division-seasons; landscape leverage by two-way fixed-effects regression (square, division x season).</li>
<li><b>Joining.</b> Each practical line is assigned to the repeat patch it mostly runs through (within 150 m). A burnt patch's lines count as block boundaries (cost only); an unburnt patch's lines count at their held-out saving. Programme sizes take patches in rank order of burn benefit; everything else keeps its breaks.</li>
</ul>
</body></html>""")
html = ''.join(H); open(REP + 'joint_plan_mp.html', 'w').write(html)
CH = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
subprocess.run([CH, '--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer', '--print-to-pdf=' + REP + 'joint_plan_mp.pdf', 'file://' + REP + 'joint_plan_mp.html'], check=True, capture_output=True, timeout=300)
print('pdf', os.path.getsize(REP + 'joint_plan_mp.pdf') / 1e6, 'MB')
