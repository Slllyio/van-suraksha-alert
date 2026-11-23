# Fire lines and control burning together: the combined plan for MP (round r30, 19 Oct 2026)

Akkshay (18:31Z): "now make the whole plan of using natural terrain based firelines and control burning together in coordination with each other and how much area will be saved ... very detailed pdf containing all maps, figures, tables and data ... based on the scars".

**The report: `report/joint_plan_mp.pdf`** (26 pages, 15 figures; section 7 = the five checks of control_burning.md sections 10-14, 20 Oct; `j1_patches.csv/.geojson` carry the per-patch escape flag; `j5_checks.py`; every division, the 160 year-one patches). HTML source beside it. Code `code/joint_plan/j1_overlap.py` (overlap, patch values, programme sizes), `j2_fires.py` (every scar fire 2017-25 by start patch, tier and size), `j3_figs.py` (`figs_r30/`), `j4_pdf.py` (Chromium print).

## What the join shows (DATA, held out 2022-25)

- **Same ground.** 7,347 of the 7,703 practical lines (4,840 of 4,986 km, 97%) run inside the 3,867 tr3 repeat patches; 736 patches carry lines. A burnt patch does not need its lines as breaks that season, so the two savings cannot be added. Under full burning the lines' own saving inside burnt patches (24.8k ha/yr) is forgone and only 146 km stay as breaks.
- **Rule.** Burn every patch that can be burnt, 15-28 Feb, every year, block by block inside its practical lines (the lines are the burn-block boundaries, cleared Dec-Jan; the patch edge needs a boundary on the part with no natural barrier, [inference] 60% of the perimeter). Where a patch cannot be burnt, the same lines stay as breaks. Nothing outside the patches. Watchers on the ranked squares from 8 Mar.
- **Area saved** (MP burnt forest 718.7k ha/yr; lines Rs 1,356/km, burning [inference] Rs 120/ha):

| programme | patches burnt | ha burnt | block-line km | edge km (inf.) | break km elsewhere | forest ha/yr not burnt at all | % MP | patch ha/yr cool-burnt instead | total ha/yr | % MP | Rs crore/yr | Rs per ha not burnt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lines only, 4,986 km | 0 | 0 | 0 | 0 | 4,986 | 25,351 | 3.5 | 0 | 25,351 | 3.5 | 0.7 | 267 |
| burn first 25k ha | 160 | 24,638 | 573 | 903 | 4,414 | 36,295 | 5.0 | 9,578 | 45,873 | 6.4 | 1.1 | 301 |
| first 50k | 233 | 49,923 | 907 | 1,656 | 4,079 | 40,010 | 5.6 | 19,467 | 59,477 | 8.3 | 1.5 | 375 |
| **first 100k (first programme)** | 465 | 99,945 | 1,934 | 3,368 | 3,052 | **43,179** | 6.0 | **37,894** | **81,073** | 11.3 | 2.3 | 540 |
| first 200k | 938 | 198,785 | 3,521 | 6,838 | 1,465 | 44,054 | 6.1 | 69,578 | 113,632 | 15.8 | 4.0 | 905 |
| all 419k ha | 3,867 | 419,020 | 4,840 | 16,296 | 146 | 44,901 | 6.2 | 107,878 | 152,779 | 21.3 | 7.9 | 1,763 |

- **Ceiling.** Forest not burnt at all tops out near 45k ha/yr (6%) under any mix (patch ground burns 37%/season held out 2022-25, 53% over 2017-25; all programme numbers use the held-out share): the patches carry 20% of MP's burnt forest and start 21% of its 200 ha+ fires (12% start in the first 100k ha); the other 80% burns on ground that burns once in 28 years, where nothing can be placed in advance (live alerts + watchers). The conversion (108k ha at most) is the same ground burnt cool in Feb; the record cannot say what that does to regeneration or wildlife.
- **Cost per ha not burnt**: lines alone Rs 267; with 100k ha burnt Rs 540 (Rs 288 per ha touched). [inference] Crews: first programme ~6,700 crew-days in 12 working days = ~560 crews of five (~2,800 people); full ~2,300 crews.
- **Per division (first programme)**, hectares touched per year: Ratapani 12.7k (4.0k not burnt + 8.7k cool-burnt), Sehore 6.2k, Dewas 4.9k, Khandwa 4.6k, South Balaghat 3.9k, Narsinghpur 3.6k, Chhatarpur 3.3k ... (`code/joint_plan/out/j1_by_division.csv`, every division under every size).
- **Three-year build-up**: Y1 first 25k ha (all5 cores first) + 1,000 km of breaks, scar-check every block; Y2 first 100k ha; Y3 on, every patch a crew can hold, re-ranked yearly on the latest five seasons.

## Files
`code/joint_plan/out/j1_patches.csv/.geojson` (every patch: burn value, line value, boundary km, role), `j1_lines.csv/.geojson` (every line: patch, role), `j1_programmes.csv`, `j1_by_division.csv`, `j2_fires.csv`, `j2_bigfires.csv`; `figs_r30/r30_fig1_map_mp.png` (plan map), `fig2_divisions`, `fig3_example` (Ratapani patch with block lines by ground type), `fig4_frontier`, `fig5_divisions_bar`, `fig6_calendar` (work plan), `fig7_bigfires`.

- 20 Oct: `j1_patches.csv/.geojson` also carry `uphill_side`, `repeat_fuel_side` and `feb_downwind_side` per patch (new_questions.md section 4): large escapes go uphill or toward the neighbouring repeat-burn forest, not downwind.
