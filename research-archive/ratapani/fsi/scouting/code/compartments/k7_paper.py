"""Part B. Conference paper (PDF) on fire lines, repeat-burn patches and compartments for all of MP, 2017-25.
Every number in the text is read from the round-25/26/27 output files at build time (paths below), not typed in.
Run: python k7_paper.py   Out: scouting/conference/fire_lines_mp_2017_25.pdf"""
import json
import numpy as np, pandas as pd
from PIL import Image as PImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether)
import k0 as K

SC_ = '/mnt/project-files/ratapani/fsi/scouting/code/'
R25 = json.load(open(SC_ + 'fire_lines/out/summary_tables.json'))
R26 = json.load(open(SC_ + 'repeat_patch_lines/out/tables.json'))
R27 = json.load(open(K.OUT + 'tables.json'))
ST = pd.read_csv(K.OUT + 'strategy_table.csv')
DT = pd.read_csv(K.OUT + 'division_table.csv')
TP = pd.read_csv(K.OUT + 'top_tested_patches.csv')
FC = pd.read_csv(K.OUT + 'final_budget_curve.csv')
FP = pd.read_csv(K.OUT + 'final_patches.csv')
HY = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/history_by_year.csv')
AL = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/mp_alert_event.csv', usecols=['sensor'])
FIG = K.CONF + 'figs/'

ss = getSampleStyleSheet()
BODY = ParagraphStyle('b', parent=ss['BodyText'], fontName='Times-Roman', fontSize=10.2, leading=13.4, alignment=TA_JUSTIFY, spaceAfter=5)
H1 = ParagraphStyle('h1', parent=ss['Heading1'], fontName='Helvetica-Bold', fontSize=13, spaceBefore=10, spaceAfter=5)
H2 = ParagraphStyle('h2', parent=ss['Heading2'], fontName='Helvetica-Bold', fontSize=11, spaceBefore=7, spaceAfter=3)
CAP = ParagraphStyle('c', parent=BODY, fontSize=8.6, leading=10.6, textColor=colors.HexColor('#333333'), spaceAfter=9)
TIT = ParagraphStyle('t', parent=ss['Title'], fontName='Helvetica-Bold', fontSize=17, leading=21)
AUT = ParagraphStyle('a', parent=BODY, alignment=TA_CENTER, fontSize=10)
ABS = ParagraphStyle('ab', parent=BODY, fontSize=9.6, leading=12.6, leftIndent=18, rightIndent=18)
REF = ParagraphStyle('r', parent=BODY, fontSize=8.8, leading=11, leftIndent=12, firstLineIndent=-12, alignment=0)
TC = ParagraphStyle('tc', parent=BODY, fontSize=7.8, leading=9.4, alignment=0, spaceAfter=0)

S = []
P = lambda t, st=BODY: S.append(Paragraph(t, st))


def f(x, d=1): return f'{x:,.{d}f}'


def st(s, B, p=0.35):
    r = ST[(ST.strategy == s) & (ST.budget == B) & (ST.p == p)]
    return r.iloc[0]


def fig(name, cap, w=16.5):
    im = PImage.open(FIG + name); r = im.size[1] / im.size[0]
    h = w * r
    if h > 20: w = 20 / r; h = 20
    S.append(KeepTogether([Image(FIG + name, width=w * cm, height=h * cm), Paragraph(cap, CAP)]))


def table(rows, widths, head=1, cap=None):
    data = [[Paragraph(str(c), TC) for c in r] for r in rows]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=head)
    t.setStyle(TableStyle([('LINEABOVE', (0, 0), (-1, 0), 0.8, colors.black), ('LINEBELOW', (0, head - 1), (-1, head - 1), 0.5, colors.black),
                           ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('BACKGROUND', (0, 0), (-1, head - 1), colors.HexColor('#eef2f6')), ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5)]))
    blk = [t]
    if cap: blk.append(Paragraph(cap, CAP))
    S.append(KeepTogether(blk))


# ---------------- numbers ----------------
ev_hist = int(HY.fire_events.sum()); s5 = {r['set']: r for r in R26['step1'] if r['grp'] == 'all MP'}
s3c = [r for r in R26['step1'] if r['grp'] == 'core' and r['set'] == 'tr3'][0]; s3r = [r for r in R26['step1'] if r['grp'] == 'rest' and r['set'] == 'tr3'][0]
e_rc = R26['entries']['tr3|rest|def']; e_rt = R26['entries']['tr3|rest|test']; e_cc = R26['entries']['tr3|core|def']
e_all = R26['entries']['tr3|all MP|def'] if 'tr3|all MP|def' in R26['entries'] else None
thr = R26['through_line_test']['all MP|all_entries']
t26 = {(r['grp'], r['p'], r['method'], r['what']): r for r in R26['test'] if 'method' in r}
r25c, r25r = R25['core']['20'], R25['rest_of_mp']['20']
c5, rk5, co5, ri5, en5 = (st(s, 500) for s in ('comp', 'randkm', 'corridor', 'ring', 'entry'))
c1k = st('comp', 1000); c100 = st('comp', 100); co1k = st('corridor', 1000)
d_rk5, d_co5, d_ri5, d_en5 = (st(f'comp_minus_{s}', 500) for s in ('randkm', 'corridor', 'ring', 'entry'))
d_rk1k = st('comp_minus_randkm', 1000)
c5p1 = st('comp', 500, 1.0)
fr = {r['strategy']: r for r in R27['fronts_500']}
ns = R27['nstar']; sb = R27['saved_by_start']; share_inside = sb['inside'][0] / (sb['inside'][0] + sb['other'][0])
TPs = TP.sort_values('test_ha_yr', ascending=False); top1 = TPs.test_ha_yr.iloc[0] / TP.test_ha_yr.sum(); top5 = TPs.test_ha_yr.head(5).sum() / TP.test_ha_yr.sum()
burnt_f = R27['test_burnt_forest_ha_yr']
_h = np.array(R26['hist']['all MP']); _i = np.array(R26['hist_indep']['all MP'])
ratio6 = 100 * _h[6:].sum() / _h[1:].sum(); ratio6i = 100 * _i[6:].sum() / _i[1:].sum()
n_viirs = int(AL.sensor.str.startswith('viirs').sum()); n_modis = int((AL.sensor == 'modis').sum())

# ---------------- title / abstract ----------------
P('Where should fire lines go? Repeat-burn patches, entry sides, corridor lines and internal compartments in the forests of Madhya Pradesh, 2017-2025', TIT)
P('Akkshay (project lead) and the fire-line analysis team &nbsp;|&nbsp; Draft for conference presentation, October 2026', AUT)
S.append(Spacer(1, 6))
P(f"""<b>Abstract.</b> Fire lines are the main pre-season tool against forest fires in Madhya Pradesh (MP), but there is little
evidence on where new lines save the most forest. We built a fire history for all of MP from satellite fire detections and
burn-scar outlines ({f(ev_hist, 0)} forest fire events, 2017-2025). We chained these events into multi-day fires and tested three line
strategies on held-out seasons. Lines were placed using 2017-21 fires and scored on 2022-25 fires. A line protects the ground a fire
could reach only by crossing it, and it holds with an assumed chance of 0.35. (1) <i>Corridor lines</i> across narrow paths that past fires
ran through saved about {r25c['plan']['ha_per_km_yr']:.1f}-{r25r['plan']['ha_per_km_yr']:.1f} ha per km of line per year, against about
0.5-0.6 for random lines. (2) Fire keeps returning to the same ground: {s5['tr3']['pct_forest'] if 'tr3' in s5 else 4.8}% of forest
(burnt in at least 3 of 5 seasons) held about a fifth to a quarter of later burning. But the main fire of a patch-season started
inside the patch in about 40% of cases. Lines on the side that fires "usually" came in from saved only
{t26[('all MP', 0.35, 'entry', 'patch')]['test']:.2f} ha of the patch per km per year. (3) <i>Internal compartment lines</i> split
large repeat patches into n parts, with n chosen by a statewide greedy knapsack. At a 500 km statewide budget they saved
{c5.patch_ha_km_yr:.1f} ha of repeat-patch forest (95% range {c5.patch_lo:.1f}-{c5.patch_hi:.1f}) and {c5.forest_ha_km_yr:.1f} ha of all forest
per km per year. This beats corridor lines ({co5.patch_ha_km_yr:.1f} / {co5.forest_ha_km_yr:.1f}) and perimeter rings, but random cuts in the same
patches did nearly as well ({rk5.patch_ha_km_yr:.1f}). All strategies are small in absolute terms. 500 km of compartment lines would have
saved {c5.pct_burnt_forest:.2f}% of the forest burnt each year. In-sample benefits overstate held-out benefits by about ten times.
Fire lines in MP are best seen as anchors for patrol and early burning in a few large, often-burnt patches, not as a way
to cut statewide burnt area.""", ABS)

# ---------------- 1 study area & data ----------------
P('1. Study area and data', H1)
P(f"""<b>Study area.</b> Madhya Pradesh has about 77,500 km<super>2</super> of forest cover (FSI 2021), mostly dry and moist
deciduous teak and sal forest. The fire season runs from mid-February to mid-June, and most fires are surface fires lit by people.
We worked at the level of the {R27['n_div']} forest divisions that have fire data. Eight tiger-reserve divisions and Ratapani
(Obedullahganj) are reported as a "core" set because their scar outlines were checked most carefully.""")
P(f"""<b>Active fire detections.</b> NASA FIRMS archive detections, 15 Feb-15 Jun of 2017-2025, clipped to MP forest beats:
{f(len(AL), 0)} detections. Of these, {f(n_viirs, 0)} are VIIRS 375 m (Suomi-NPP throughout, NOAA-20 from 2018) and
{f(n_modis, 0)} are MODIS 1 km (Aqua and Terra). The scar-history events were built only from S-NPP, NOAA-20 and MODIS points;
NOAA-21 VIIRS detections (available from 2023) were not used in the event history. Detections were grouped into fire
events (same day, within 1 km), keeping those in forest (at least 10% tree or shrub cover within 375 m).""")
P(f"""<b>Burn-scar history.</b> For each forest fire event, a burn-scar outline was drawn from Sentinel-2/Landsat images before and after
the fire (the project's alert-scar method, with grown outlines). The statewide run covers {f(ev_hist, 0)} events, of which 153,817 lie
outside the tiger reserves. The tiger reserves (12,586 events) and Ratapani (scar outlines v2) were run separately.
A clear scar was found for 78-90% of events each year. Burnt area (each patch counted once) ranged from
{f(HY.burned_ha_union.min() / 1e3, 0)} thousand ha (2020) to {f(HY.burned_ha_union.max() / 1e3, 0)} thousand ha (2021) a year. On a check sample, real
fires got a clear scar 84% of the time and control points 4%.""")
P("""<b>Other layers.</b> The Vegetation Type Map of India (VTM; 60 m lattice, tree forest and scrub classes) defines forest. All
outlines are clipped to it. Overture Maps roads and tracks (2026-09), beat boundaries and terrain (terrarium tiles, ~140 m,
for ridge and valley lines) give the candidate lines that follow existing features. All analysis is on a 60 m grid in UTM 43N.""")

# ---------------- 2 methods ----------------
rows = [['season', 'forest fire events', 'clear scar %', 'any scar %', 'burnt ha (each patch once)']]
for _, r in HY.iterrows(): rows.append([int(r.year), f(r.fire_events, 0), f'{r.clear_scar_pct:.1f}', f'{r.any_scar_pct:.1f}', f(r.burned_ha_union, 0)])
rows.append(['2017-25', f(HY.fire_events.sum(), 0), '', '', f(HY.burned_ha_union.sum(), 0)])
table(rows, [2.2, 3.2, 2.4, 2.4, 4.2], cap='<b>Table 0.</b> Burn-scar history used (fire-alert-scars/mp/out/history_by_year.csv). Burnt area is not clipped to forest here; all analyses below clip to VTM forest.')
P('2. Methods', H1)
P('2.1 Fire chaining and starts', H2)
P("""Daily scar events are chained into one <i>fire</i> when their outlines lie within 60 m of each other and their dates are at most
4 days apart. A fire's footprint is the union of its outlines on the 60 m grid. Its <i>start</i> is the set of cells within 400 m of the
first VIIRS look (all detections within 2 hours of the earliest overpass). Fires are counted by the season of their first look.""")
P('2.2 Benefit of a line and the stop chance', H2)
P("""A line is a chain of 60 m cells. For each past fire, the fire is let spread again from its start, cell to neighbouring cell, but only
inside its own footprint. Ground that it can then reach only by crossing the line is the ground the line <i>could</i> have protected.
A cleared line does not always stop a front. From the project's front-stopping analysis, a road within 40 m raises the odds that a
front stops 3.3-fold (95% range 2.2-4.6). A front in tree cover stops within 100 m about 15% of the time. Together these give a
stop chance of about 0.35 per crossing (range 0.28-0.45). We use 0.35 throughout, and 1.0 as an upper bound. With several lines,
ground that needs k crossings is burnt with chance 0.65<super>k</super>. Lines are compared per km of line per year. This is a proxy for cost,
since each km must be cleared before every season.""")
P('2.3 Held-out design', H2)
P("""Every line strategy is chosen using fires of 2017-21 only and scored on fires of 2022-25. Uncertainty comes from resampling whole
test fires within each division (1,000 bootstrap draws). All strategies are scored on the same fires, so differences between them are
paired. The same lines are also scored on the 2017-21 fires they were chosen on, to show how much in-sample numbers overstate.""")
P('2.4 Corridor lines (round 25)', H2)
P("""For each division, a <i>spread-flow</i> map adds up, for each cell, the hectares that past fires could only reach through that cell.
Candidate lines (1-4 km) come from existing roads and tracks, beat boundaries, ridge and valley lines, and straight "neck" lines through
peaks of the flow map. A greedy search picks the line that saves most per km, then the next, and so on. Baselines are random forest
lines, random road and beat-edge pieces, roads only, and the most-burnt ground. In this round, rest-of-MP lines were trained on
2019-21, because the 2017-18 history was not yet finished.""")
P('2.5 Repeat-burn patches and entry direction (round 26)', H2)
P("""A 120 m forest cell "burnt" in a season if at least 2 of its 60 m cells were inside that season's scars. A <i>repeat patch</i> is a
connected area (at least 10 ha) of cells burnt in at least 3 of the 5 seasons 2017-21 (or at least 5 of 9 for 2017-25). For each fire
that burnt at least 1 ha of a patch, we asked whether its first-look detection lay inside the patch ("started inside"). If not, we
found where the fire first reached the patch along its spread path ("entry"). The ring of cells around the patch was cut into about
1 km edge segments, and each entry was assigned to the nearest one. A patch with at least 3 entries, 60% or more through one
segment, got an <i>entry-side line</i> on that segment.""")
P('2.6 Internal compartments and the n* algorithm (round 27)', H2)
P(f"""The idea is to divide a repeat scar into n parts, with n chosen by an algorithm so that little work has a large effect. Fires that start inside a patch cannot be stopped
by any edge line, but an internal line can keep them in the part where they started. Inside each compartment, candidate cuts are
straight chords in 8 directions at regular offsets, plus ridge, valley and track chains that cross it. A cut may run up to 120 m past
the patch edge and must leave two pieces of at least 2 ha. For each patch, a greedy search adds the cut that saves most patch forest
per km per year on 2017-21 fires, up to 20 cuts. This gives a benefit curve against n. Each curve is reduced to its upper concave
hull. A single statewide greedy knapsack then spends a km budget (100, 250, 500 or 1,000 km) on the next hull step with the highest
return per km, whichever patch it belongs to, and stops at the first step that does not fit. So every patch gets its own n*
(cuts taken + 1). All patches share one marginal return λ, the return of the last cut taken, which is the "knee" threshold.
Comparisons at the same statewide budgets: random straight cuts in the same patches (same km; 5 draws), entry-side lines, whole
perimeter rings, and round-25 corridor lines, each ranked by its own 2017-21 value.""")

# ---------------- 3 results ----------------
P('3. Results', H1)
P('3.1 Fire keeps returning to the same ground', H2)
P(f"""Burnt ground burns again far more often than chance would allow (Fig. 2a). Among 120 m forest cells burnt at least once in 2017-25,
{ratio6:.1f}% burnt in 6 or more seasons, against {ratio6i:.3f}% if each season burnt the same share of forest at random. Patches burnt in at least 3 of the 5 training
seasons cover {s3c['pct_forest']}% (core) and {s3r['pct_forest']}% (rest) of forest. In the held-out seasons 2022-25 they held
{s3c['in_test_yrs']}% and {s3r['in_test_yrs']}% of all burnt forest (Fig. 2b). But "every year" hardly exists. Forest burnt in all 5
training seasons is {s5['tr5']['pct_forest']}% of the total, and forest burnt in all 9 seasons is {s5['all9']['pct_forest']}%. Repeat burning
is concentrated in the Vindhyan and Satpura belts, Ratapani, Khandwa-Burhanpur and the east (Fig. 1, Fig. 10a).""")
fig('fig01_mp_repeat_map.png', '<b>Figure 1.</b> Repeat burning across MP, 2017-25. (a) Mean number of seasons burnt per forest cell (600 m blocks). (b) Share of forest burnt in at least 5 of 9 seasons (1.2 km blocks), with the core divisions labelled. Lines are forest division boundaries.')
fig('fig02_repeat_stats.png', '<b>Figure 2.</b> (a) Seasons burnt per 120 m forest cell (cells burnt at least once), observed against independent seasons (log scale). (b) Share of each season\'s burnt forest inside patches defined on 2017-21. The grey band is the held-out period.')

P('3.2 Fires do not keep entering from the same side', H2)
P(f"""In the rest of MP, the main fire of a patch-season (2017-21) started inside the patch in {e_rc['inside']}% of cases. It started within 400 m of
the edge, inside the location error of a VIIRS detection, in a further {round(e_rc['entered'] - e_rc['entered_from_out'], 1)}%. It came from
400 m or more outside in only {e_rc['entered_from_out']}% (Fig. 3a). The core set and the test years look the same. Among patches with at least
3 entries, the median share through the most-used 1 km segment was {e_rc['mode_share_med']} (rest), against {e_rc['chance_share_med']} expected by
chance (Fig. 3b). Held out, {round(100 * thr['share'])}% of 2022-25 entries came through the proposed segment, against {round(100 * thr['chance'])}% by
chance. This side preference is real but weak. Entry-side lines saved only {t26[('all MP', 0.35, 'entry', 'patch')]['test']:.2f} ha of the patch per km
per year (random edge segment {t26[('all MP', 0.35, 'rand_edge', 'patch')]['test']:.2f}).""")
fig('fig03_entries.png', '<b>Figure 3.</b> (a) Where the main fire of each patch-season started, for patches burnt at least 3 of 5 seasons in 2017-21. (b) Share of entries through the most-used edge segment against the share expected by chance with the same number of entries.')
fig('fig11_entry_examples.png', '<b>Figure 4.</b> Entry-side lines, examples from round 26. Green arrows are 2017-21 entries and blue arrows 2022-25 entries. Most test fires started inside or came in from other sides.', w=11)

P('3.3 Corridor lines', H2)
P(f"""With 20 km of line per division, corridor lines chosen on training fires saved {r25c['plan']['ha_per_km_yr']:.1f} ha/km/yr (core; 95% range
{r25c['plan']['lo']:.1f}-{r25c['plan']['hi']:.1f}) and {r25r['plan']['ha_per_km_yr']:.1f} (rest; {r25r['plan']['lo']:.1f}-{r25r['plan']['hi']:.1f}) in 2022-25.
Random forest lines saved {r25c['rand_forest']['ha_per_km_yr']:.2f} and {r25r['rand_forest']['ha_per_km_yr']:.2f}, and roads only
{r25c['road_only']['ha_per_km_yr']:.2f} and {r25r['road_only']['ha_per_km_yr']:.2f}. The same lines "saved" {r25c['train_ha_per_km_yr_plan']:.0f} ha/km/yr on their training fires. That is about 14 times the held-out value, because most
fire paths do not repeat. 20 km per division would have stopped {r25c['pct_test_ha_plan']:.2f}% of burnt area. Even lines chosen with
perfect hindsight reach only {r25c['pct_test_ha_oracle']:.1f}%. Straight lines placed by the same greedy logic did as well as lines on terrain features,
so where a line goes matters more than what it follows (Fig. 5).""")
fig('fig10_r25_corridor_maps.png', '<b>Figure 5.</b> Corridor lines, core divisions (round 25). Orange: spread-flow corridors of 2017-21 fires. Blue: 2022-25 burns. Cyan: first 20 km of lines chosen on 2017-21.', w=13)

P('3.4 Internal compartments', H2)
P(f"""Of the {R27['n_patches_tr3']:,} repeat patches (2017-21), {R27['patches_with_cuts']['n']:,} had at least one valid cut that would have saved
something in 2017-21. For most, the first cut was worth little (median {R27['patches_with_cuts']['first_cut_ha_km_yr_median']:.1f} ha/km/yr
in-sample). The statewide allocation therefore puts the km into a small number of large patches burnt by many fires (Fig. 6, Fig. 9b).
At 500 km it cuts {ns['500']['patches']} patches with {ns['500']['cuts']} cuts. The median n* is {ns['500']['nstar_median']:.0f}, 90% of
patches have n* of {ns['500']['nstar_p90']:.0f} or less, and the largest is {ns['500']['nstar_max']}. The marginal return of the last cut is
λ = {ns['500']['lam']:.1f} ha/km/yr in-sample. Benefit curves rise steeply for the first few cuts and then flatten (Fig. 9a).
{R27['kinds']['500'].get('straight', 0)} of the {sum(R27['kinds']['500'].values())} cuts are straight chords. Ridge, valley and track chains seldom cross a
compartment from edge to edge.""")
P(f"""Held out (2022-25), compartment cuts at 500 km saved {c5.patch_ha_km_yr:.2f} ha of repeat-patch forest per km per year
(95% range {c5.patch_lo:.2f}-{c5.patch_hi:.2f}) and {c5.forest_ha_km_yr:.2f} ha of all forest ({c5.forest_lo:.2f}-{c5.forest_hi:.2f}) (Table 1, Fig. 7).
In-sample they had "saved" {c5.patch_train_ha_km_yr:.1f}, so the held-out value is about a tenth. {round(100 * share_inside)}% of the
saved patch hectares came from fires that started inside a repeat patch, which is the mechanism behind the idea. The result is concentrated: one Ratapani patch
gives {round(100 * top1)}% of the statewide held-out total, and the top five patches give {round(100 * top5)}%.
{round(100 * R27['top_tested']['share_zero_test'])}% of the cut patches saved nothing in the four test seasons.""")
fig('fig05_examples.png', '<b>Figure 6.</b> Compartment cuts in four repeat patches (cuts chosen on 2017-21 at the 500 km statewide budget), shown over 2022-25 burns and fire starts. Coloured areas are compartments. Titles give n*, km of cut, and patch forest saved per year in-sample (2017-21) and held out (2022-25).')
rows = [['strategy (500 km statewide)', 'km', 'patch forest ha/km/yr (95% range)', 'all forest ha/km/yr (95% range)', 'in-sample patch ha/km/yr', '% of burnt forest saved per yr']]
for s, nm in (('comp', 'Compartment cuts'), ('randkm', 'Random cuts, same patches, same km'), ('corridor', 'Corridor lines (r25)'), ('ring', 'Perimeter ring'), ('entry', 'Entry-side lines (r26)')):
    r = st(s, 500); rows.append([nm, f(r.km, 0), f'{r.patch_ha_km_yr:.2f} ({r.patch_lo:.2f}-{r.patch_hi:.2f})', f'{r.forest_ha_km_yr:.2f} ({r.forest_lo:.2f}-{r.forest_hi:.2f})', f'{r.patch_train_ha_km_yr:.1f}', f'{r.pct_burnt_forest:.2f}'])
for s, nm in (('randkm', 'random'), ('corridor', 'corridor'), ('ring', 'ring'), ('entry', 'entry side')):
    r = st(f'comp_minus_{s}', 500); rows.append([f'Compartments minus {nm}', '', f'{r.patch_ha_km_yr:+.2f} ({r.patch_lo:+.2f} to {r.patch_hi:+.2f})', f'{r.forest_ha_km_yr:+.2f} ({r.forest_lo:+.2f} to {r.forest_hi:+.2f})', '', ''])
table(rows, [4.6, 1.1, 3.4, 3.4, 1.9, 2.1], cap=f'<b>Table 1.</b> Held-out (2022-25) comparison of the line strategies at a 500 km statewide budget, stop chance 0.35. Each strategy is ranked statewide by its own 2017-21 value. Differences are paired (same test fires). Denominator for the last column: {f(burnt_f, 0)} ha of forest burnt per year in 2022-25.')

P('3.5 Budget curves', H2)
P(f"""The benefit grows with the budget but with falling returns (Fig. 7). At 100, 250, 500 and 1,000 km, compartments saved
{st('comp', 100).patch_ha_km_yr:.1f}, {st('comp', 250).patch_ha_km_yr:.1f}, {c5.patch_ha_km_yr:.1f} and {c1k.patch_ha_km_yr:.1f} patch ha/km/yr held out,
which is {st('comp', 100).pct_burnt_forest:.2f}%, {st('comp', 250).pct_burnt_forest:.2f}%, {c5.pct_burnt_forest:.2f}% and {c1k.pct_burnt_forest:.2f}% of yearly burnt forest.
Compartments beat corridor lines, rings and entry-side lines at every budget. The margin over random cuts in the same patches is
small: {d_rk5.patch_ha_km_yr:+.2f} ({d_rk5.patch_lo:+.2f} to {d_rk5.patch_hi:+.2f}) at 500 km and {d_rk1k.patch_ha_km_yr:+.2f}
({d_rk1k.patch_lo:+.2f} to {d_rk1k.patch_hi:+.2f}) at 1,000 km. So most of the skill lies in <i>which patches</i> get lines, not in exactly where
inside them. If every line always held, 500 km would save {c5p1.patch_ha_km_yr:.1f} patch ha/km/yr ({c5p1.pct_burnt_forest:.2f}% of burnt forest).""")
fig('fig06_strategies.png', '<b>Figure 7.</b> Held-out hectares saved per km of line per year for each strategy and statewide budget (stop chance 0.35). (a) Repeat-patch forest. (b) All forest. Bars show 95% bootstrap ranges.')
fig('fig07_budget.png', '<b>Figure 8.</b> (a) Repeat-patch forest saved per year against the statewide budget, compartments in-sample (solid) and held out (dashed), with every strategy\'s joint held-out score. (b) λ, the in-sample marginal return of the last cut taken.')
fig('fig09_ncurve.png', '<b>Figure 9.</b> (a) Benefit against n for the 12 patches with the largest in-sample benefit (solid, 2017-21) and the same cuts held out (dotted, 2022-25). (b) Distribution of n* at each statewide budget.')

P('3.6 Divisions', H2)
dd = DT[DT.comp_km > 0]
P(f"""At 500 km, compartment cuts go to {R27['division_with_cuts']} divisions, led by Khandwa, Burhanpur, Ratapani, Chhatarpur, Noradehi and
Narsinghpur (Fig. 10b, Fig. 11). In the divisions that get most km, the held-out value is 1-8 patch ha/km/yr. Even there, cuts remove only
about 1-2% of the division's burnt forest. Division-level ranges are wide, and compartments beat corridor lines in
{R27['division_wins']['corridor']} of these {R27['division_with_cuts']} divisions.""")
fig('fig04_division_maps.png', '<b>Figure 10.</b> (a) Share of 2022-25 burnt forest that fell inside the 2017-21 repeat patches, by division. (b) km of compartment cuts allocated to each division by the 500 km statewide budget.')
fig('fig08_divisions.png', '<b>Figure 11.</b> Held-out repeat-patch forest saved per km per year in the 30 divisions with most compartment km (500 km budget): compartments (with 95% range), random cuts in the same patches, and corridor lines.')
rows = [['division', 'patches', 'cuts', 'km', 'compartments ha/km/yr (95%)', 'in-sample', 'random', 'corridor', '% of burnt forest']]
for _, r in dd.head(12).iterrows():
    rows.append([r.division.replace('_', ' '), int(r.patches_cut), int(r.cuts), f(r.comp_km), f'{r.comp_patch:.1f} ({r.comp_patch_lo:.1f}-{r.comp_patch_hi:.1f})', f'{r.comp_patch_train:.1f}', f'{r.randkm_patch:.1f}', f'{r.corridor_patch:.1f}', f'{r.comp_pct_burnt_forest:.2f}'])
table(rows, [3.6, 1.3, 1.1, 1.2, 3.2, 1.6, 1.4, 1.5, 1.7], cap='<b>Table 2.</b> The 12 divisions with most compartment km at the 500 km statewide budget. Values are held-out repeat-patch forest ha/km/yr (2022-25, stop chance 0.35). Full table: code/compartments/out/division_table.csv.')
rows = [['division', 'patch centre (lon, lat)', 'patch ha', 'n*', 'km', 'in-sample ha/yr (2017-25)']]
for _, r in FP.head(15).iterrows():
    rows.append([r.division.replace('_', ' '), f'{r.lon:.3f}, {r.lat:.3f}', f(r.patch_ha, 0), int(r.nstar_500), f'{r.km_500:.1f}', f'{r.insample_ha_yr_500:.0f}'])
table(rows, [4.4, 3.4, 1.8, 1.2, 1.4, 3.4], cap=f"<b>Table 3.</b> Final plan: the 15 repeat patches (burnt at least 5 of 9 seasons, 2017-25) with the most in-sample benefit at the 500 km statewide budget. The full plan has {int(FC[FC.budget == 500].patches.iloc[0])} patches and {int(FC[FC.budget == 500].cuts.iloc[0])} cuts. Expect about a tenth of the in-sample value in future seasons (Section 3.4). The geojson holds the compartments and cuts.")

# ---------------- 4 discussion ----------------
P('4. Discussion', H1)
P(f"""<b>What works.</b> Three things hold up out of sample. (i) Repeat burning is real and mappable: about 5% of forest takes
a fifth to a quarter of each season's burning. (ii) Lines placed where many past fires had to pass beat random or road-following lines.
This holds for corridor lines across narrow paths and, more strongly, for cuts inside large repeat patches. (iii) The best use of a fixed
budget is to concentrate it. A statewide greedy rule with one marginal threshold sends most km to a few dozen large patches, with
2-6 compartments each.""")
P(f"""<b>What does not.</b> Fires do not reliably come from the same side, so edge lines on the "usual" side protect very little. And no
passive line strategy cuts statewide burnt area by more than about 1%. In-sample estimates overstate the benefit by 10-14 times,
because most fire paths do not repeat. The 2022 and 2025 seasons gave most of the held-out benefit, and 2023 almost none.""")
P(f"""<b>Limits.</b> (1) <i>VIIRS 375 m.</i> Start locations are uncertain by about 375 m. Entry sides at 1 km and starts "inside" small patches are
therefore blurred. (2) <i>Scar edges.</i> Outlines come from 10-30 m imagery after the fire. Some small burns are missed (10-22% of events a year have no clear scar), and tiger-reserve outlines were drawn before a chip-edge fix, so large fires there may be cut short. (3) <i>Spread
model.</i> Fires are re-run only inside their own historical footprint, from the first detection. Flanking through unburnt ground, spotting and
second ignitions are ignored, which makes all benefits optimistic. When every new front more than 750 m from earlier detections is
counted as its own start, compartment benefits fall to {round(100 * fr['comp']['patch_ratio_to_main'])}% of the main value
({fr['comp']['patch_ha_km_yr']:.2f} patch ha/km/yr), level with random cuts ({fr['randkm']['patch_ha_km_yr']:.2f}). They are still above corridor
lines ({fr['corridor']['patch_ha_km_yr']:.2f}) and entry lines ({fr['entry']['patch_ha_km_yr']:.2f}). (4) <i>Suppression.</i> Past scars already include the
effect of crews and existing lines, so a new line is credited only with ground that actually burnt. (5) <i>The stop chance of 0.35</i> is
borrowed from roads, not measured on cleared fire lines. Results scale roughly with it, and the ranking of strategies does not change at 1.0.
(6) <i>Grid.</i> A 60 m cell chain is a sketch. Real lines are 10-20 m wide and must follow ridges, nalas or tracks on the ground.""")

# ---------------- 5 conclusion ----------------
P('5. Conclusions and recommendations', H1)
P(f"""1. Use the repeat-burn map (about 5% of forest, a fifth to a quarter of burning) to target pre-season effort.<br/>
2. Where new lines are cut, put them <i>inside</i> large repeat patches as compartment lines. Use 2-6 per patch, in the patches the statewide
allocation ranks first. Held out, this gave about 3 ha of patch forest (5 ha of all forest) per km per year, more than corridor, ring or entry-side lines.<br/>
3. Keep expectations modest. 500 km of such lines would have saved about {c5.pct_burnt_forest:.2f}% of yearly burnt forest. Lines are best used as
anchors for early (managed) burning and patrol inside the compartments, since {round(100 * share_inside)}% of their benefit comes from fires that
start inside the patch.<br/>
4. Do not build lines on the side fires "usually" come from, and do not expect upgrading roads to help much.<br/>
5. Judge any line plan on seasons it has not seen. In-sample benefits are about ten times too high.""")

# ---------------- appendix ----------------
P('Appendix A. Full held-out comparison', H1)
rows = [['budget', 'strategy', 'km', 'patch ha/km/yr (95%)', 'all forest ha/km/yr (95%)', 'in-sample patch', 'patch, stop 1.0', '% burnt forest']]
for B in K.BUDGETS:
    for s_, nm in (('comp', 'compartments'), ('randkm', 'random, same km'), ('rand', 'random, same n'), ('corridor', 'corridor (r25)'), ('ring', 'ring'), ('entry', 'entry side (r26)')):
        r = st(s_, B); r1 = st(s_, B, 1.0)
        rows.append([f'{B} km', nm, f(r.km, 0), f'{r.patch_ha_km_yr:.2f} ({r.patch_lo:.2f}-{r.patch_hi:.2f})', f'{r.forest_ha_km_yr:.2f} ({r.forest_lo:.2f}-{r.forest_hi:.2f})', f'{r.patch_train_ha_km_yr:.1f}', f'{r1.patch_ha_km_yr:.2f}', f'{r.pct_burnt_forest:.2f}'])
table(rows, [1.5, 2.8, 1.2, 3.1, 3.1, 1.7, 1.7, 1.6], cap='<b>Table A1.</b> All strategies and budgets, held out 2022-25, stop chance 0.35 unless stated (code/compartments/out/strategy_table.csv).')
rows = [['strategy (500 km)', 'patch ha/km/yr (95%)', 'all forest ha/km/yr (95%)', 'share of main value (patch)']]
for s_, nm in (('comp', 'compartments'), ('randkm', 'random, same km'), ('corridor', 'corridor (r25)'), ('ring', 'ring'), ('entry', 'entry side (r26)')):
    r = fr[s_]; rows.append([nm, f"{r['patch_ha_km_yr']:.2f} ({r['patch_lo']:.2f}-{r['patch_hi']:.2f})", f"{r['forest_ha_km_yr']:.2f} ({r['forest_lo']:.2f}-{r['forest_hi']:.2f})", f"{100 * r['patch_ratio_to_main']:.0f}%"])
table(rows, [4, 4, 4, 3.5], cap='<b>Table A2.</b> Conservative start rule: every new front more than 750 m from all earlier detections is treated as its own start (500 km budget).')
by = pd.DataFrame(R27['by_year_500']).pivot(index='strategy', columns='year', values='patch_ha_km')
rows = [['strategy (500 km)'] + [str(c) for c in by.columns]] + [[i] + [f'{v:.2f}' for v in by.loc[i]] for i in ('comp', 'randkm', 'corridor', 'ring', 'entry')]
table(rows, [4, 2.5, 2.5, 2.5, 2.5], cap='<b>Table A3.</b> Held-out repeat-patch forest saved per km, by test season (500 km budget).')
fig('fig12_entry_test.png', '<b>Figure A1.</b> Round-26 held-out test of entry-side lines against random edge segments, rings, nearest tracks and round-25 lines (round-26 scoring).', w=14)
fig('fig13_r25_divisions.png', '<b>Figure A2.</b> Round-25 corridor lines by division, 20 km per division, held out 2022-25.', w=15)
S.append(PageBreak()); P('Appendix B. Divisions with compartment cuts (500 km budget)', H1)
rows = [['division', 'patches', 'km', 'comp. ha/km/yr', 'random', 'corridor', 'ring', 'entry', 'patch ha/yr saved']]
for _, r in dd.iterrows():
    g = lambda v: '' if pd.isna(v) else f'{v:.1f}'
    rows.append([r.division.replace('_', ' '), int(r.patches_cut), f(r.comp_km), g(r.comp_patch), g(r.randkm_patch), g(r.corridor_patch), g(r.ring_patch), g(r.entry_patch), f(r.comp_patch_ha_yr)])
table(rows, [4.2, 1.4, 1.3, 2.2, 1.5, 1.5, 1.4, 1.4, 2.2], cap='<b>Table B1.</b> Every division that gets compartment cuts at 500 km statewide; held-out repeat-patch forest ha/km/yr of each strategy\'s own lines in that division (blank = no line of that kind there).')

# ---------------- references ----------------
P('References (to be verified)', H1)
refs = [
    'Forest Survey of India (2021). India State of Forest Report 2021. FSI, Dehradun. (Forest cover and forest fire chapters.)',
    'Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. A. (2014). The New VIIRS 375 m active fire detection data product: algorithm description and initial assessment. Remote Sensing of Environment.',
    'Giglio, L., Schroeder, W., Justice, C. O. (2016). The collection 6 MODIS active fire detection algorithm and fire products. Remote Sensing of Environment.',
    'NASA FIRMS. Fire Information for Resource Management System, archive active fire data (MODIS C6.1, VIIRS S-NPP and NOAA-20 375 m).',
    'Key, C. H., Benson, N. C. (2006). Landscape assessment: ground measure of severity, the Composite Burn Index; and remote sensing of severity, the Normalized Burn Ratio. USDA Forest Service Gen. Tech. Rep. RMRS-GTR-164-CD.',
    'Giglio, L., Boschetti, L., Roy, D. P., Humber, M. L., Justice, C. O. (2018). The Collection 6 MODIS burned area mapping algorithm and product. Remote Sensing of Environment.',
    'Roy, D. P., Huang, H., Boschetti, L., Giglio, L., et al. (2019). Landsat-8 and Sentinel-2 burned area mapping - a combined sensor multi-temporal change detection approach. Remote Sensing of Environment.',
    'Roy, P. S., et al. (2015). New vegetation type map of India prepared using satellite remote sensing. International Journal of Applied Earth Observation and Geoinformation.',
    'Agee, J. K., Bahro, B., Finney, M. A., et al. (2000). The use of shaded fuelbreaks in landscape fire management. Forest Ecology and Management.',
    'Finney, M. A. (2001). Design of regular landscape fuel treatment patterns for modifying fire growth and behavior. Forest Science.',
    'Syphard, A. D., Keeley, J. E., Brennan, T. J. (2011). Comparing the role of fuel breaks across southern California national forests. Forest Ecology and Management.',
    'Narayanaraj, G., Wimberly, M. C. (2011). Influences of forest roads on the spatial pattern of wildfire boundaries. International Journal of Wildland Fire.',
    'Kodandapani, N., Cochrane, M. A., Sukumar, R. (2004). Conservation threat of increasing fire frequencies in the Western Ghats, India. Conservation Biology.',
    'Efron, B., Tibshirani, R. J. (1993). An Introduction to the Bootstrap. Chapman and Hall.',
    'Overture Maps Foundation (2026). Transportation theme (roads and tracks), release 2026-09.',
    'Project reports (this work): fire_line_plan.md (round 25), repeat_patch_fire_lines.md (round 26), repeat_patch_compartments.md (round 27); fire-alert-scars/mp/README.md (burn-scar history).',
]
for i, r in enumerate(refs, 1): P(f'[{i}] {r}', REF)


def footer(c, d):
    c.saveState(); c.setFont('Helvetica', 7.5); c.setFillGray(0.4)
    c.drawString(2 * cm, 1.2 * cm, 'Fire lines, repeat patches and compartments in Madhya Pradesh, 2017-25 - draft, Oct 2026')
    c.drawRightString(19 * cm, 1.2 * cm, str(d.page)); c.restoreState()


doc = SimpleDocTemplate(K.CONF + 'fire_lines_mp_2017_25.pdf', pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.9 * cm,
                        title='Fire lines, repeat-burn patches and compartments in Madhya Pradesh, 2017-25', author='Fire-line analysis team')
doc.build(S, onFirstPage=footer, onLaterPages=footer)
print('pdf written')
