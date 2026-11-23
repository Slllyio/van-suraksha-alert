"""Step 6. What a control-burn programme can save, from the measured clock.
protection(age, month of burn) = 1 - re-burn ratio (cb2). The season's burning calendar (cb3_weekly) says when later fire would
have come. For a block burnt on date d, the share of its own later burning that is prevented = sum over later weeks of
(week share of the season's burning) x protection(age at that week). Applied to the repeat-patch early-burning table (m5: outside
ha stopped per 100 ha treated, at p = 1) and to the inside hectares.  Also a litter-physics table (share of the year's leaf fall
already on the ground by the burn date; curve from fuel_load_values.md) for comparison.  Out: out/cb6_design.csv, out/cb6_physics.csv"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
M5 = '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2/out/m5_curve.csv'
BURN_DATES = {'15 Feb': 46, '1 Mar': 60, '15 Mar': 74, '1 Apr': 91}
LITTER = {11: 5, 12: 10, 1: 20, 2: 25, 3: 25, 4: 10}   # share of the year's leaf fall by month (fuel_load_values.md, inference)


def litter_on_ground(doy):
    """Share of the year's leaf fall that has fallen by doy (Nov 1 = 0), linear within months."""
    order = [11, 12, 1, 2, 3, 4]; days = [30, 31, 31, 28, 31, 30]; cum = 0.0
    d = doy + 61 if doy <= 120 else doy + 61   # days since 1 Nov (non-leap, doy 1 = 1 Jan = day 62)
    for m, n in zip(order, days):
        if d <= n: return cum + LITTER[m] * d / n
        d -= n; cum += LITTER[m]
    return cum


def main():
    A = pd.read_csv(B.OUT + 'cb2_age.csv')
    am = A[A.kind == 'age x month'].set_index('g').ratio
    W = pd.read_csv(B.OUT + 'cb3_weekly.csv'); w = W.groupby('week')[['ha_all', 'ha_out_patch']].sum()
    share_all = (w.ha_all / w.ha_all.sum()).values; share_out = (w.ha_out_patch / w.ha_out_patch.sum()).values
    rows = []
    for name, d in BURN_DATES.items():
        mon = B.MON_LAB[0] if d < 60 else (B.MON_LAB[1] if d < 91 else B.MON_LAB[2])
        prot_all = prot_out = after_all = after_out = 0.0
        for wk in range(21):
            mid = B.D0 + 7 * wk + 3; age = mid - d
            if age < 0: continue
            ab = max(1, np.digitize(age, B.AGE_BINS[1:])); lab = f'{mon} burn, {B.AGE_LAB[min(ab, 5)]}'   # first 2 weeks: a planned burn is as safe as week 2-4 (the 1-2 wk ratio is the wildfire's own tail)
            r = am.get(lab, np.nan)
            if np.isnan(r):  # fall back to the age-only ratio
                r = A[(A.kind == 'age') & (A.g == B.AGE_LAB[min(ab, 5)])].ratio.iloc[0]
            p = max(0.0, 1 - r)
            prot_all += share_all[wk] * p; after_all += share_all[wk]; prot_out += share_out[wk] * p; after_out += share_out[wk]
        rows.append(dict(burn_date=name, share_of_season_burning_still_to_come=after_all, prevented_share_all=prot_all,
                         prevented_share_outside_patch=prot_out, litter_share_removed=litter_on_ground(d) / 100,
                         litter_left_by_1_Apr_vs_no_burn=(litter_on_ground(91) - litter_on_ground(d)) / litter_on_ground(91)))
    D = pd.DataFrame(rows); D.to_csv(B.OUT + 'cb6_physics.csv', index=False); print(D.round(3).to_string(index=False))
    C = pd.read_csv(M5)
    out = []
    for _, c in C.iterrows():
        for _, d in D.iterrows():
            out.append(dict(treated_ha=c.treated_ha, burn_date=d.burn_date, outside_ha_stopped_per_100ha=c.out_per_100ha_treated * d.prevented_share_outside_patch,
                            outside_ha_stopped=c.te_out_ha * d.prevented_share_outside_patch, inside_ha_prevented=c.te_in_ha * d.prevented_share_all,
                            pct_burnt_forest=100 * (c.te_out_ha * d.prevented_share_outside_patch + c.te_in_ha * d.prevented_share_all) / 718704))
    O = pd.DataFrame(out); O.to_csv(B.OUT + 'cb6_design.csv', index=False)
    print(O[O.burn_date.isin(['15 Feb', '1 Mar', '15 Mar'])].round(2).to_string(index=False))


if __name__ == '__main__':
    main()
