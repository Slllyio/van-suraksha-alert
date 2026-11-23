"""Step 4. Figures and tables for the round-28 note. Reads out/m1_sizes.json and out/m3_curve_*.csv.
Out: figs_r28/r28_fig1_curves.png (percent of burnt forest saved vs km), figs_r28/r28_fig2_perkm.png, out/m4_tables.md"""
import json, glob, os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M

LBL = {'tr3_sum': 'patches >=3/5 yrs, best total (r27)', 'tr3_med': 'patches >=3/5 yrs, median year', 'tr3_lo': 'patches >=3/5 yrs, drop best year',
       'tr2_sum': 'patches >=2/5 yrs, best total', 'tr2_med': 'patches >=2/5 yrs, median year', 'tr2_lo': 'patches >=2/5 yrs, drop best year',
       'tr3_oracle': 'hindsight on 2022-25 (ceiling), >=3/5', 'tr2_oracle': 'hindsight on 2022-25 (ceiling), >=2/5'}


def main():
    C = {}
    for fn in sorted(glob.glob(M.OUT + 'm3_curve_*.csv')):
        v = fn.split('m3_curve_')[1][:-4]; C[v] = pd.read_csv(fn)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for v, d in C.items():
        ls = '--' if 'oracle' in v else '-'
        ax[0].plot(d.km, d.pct_forest_p70, ls, label=LBL.get(v, v))
        ax[1].plot(d.km, d.perkm_forest_p70, ls, label=LBL.get(v, v))
    ax[0].set_xlabel('km of line statewide'); ax[0].set_ylabel('% of burnt forest saved, 2022-25, stop chance 0.70'); ax[0].grid(alpha=.3)
    ax[1].set_xlabel('km of line statewide'); ax[1].set_ylabel('forest ha saved per km per year (0.70)'); ax[1].grid(alpha=.3); ax[1].set_ylim(bottom=0)
    ax[0].set_xlim(0, 10000); ax[1].set_xlim(0, 10000); ax[1].set_ylim(0, 60)
    ax[0].legend(fontsize=7); plt.tight_layout(); plt.savefig(M.FIG + 'r28_fig1_curves.png', dpi=140); plt.close()
    rows = []
    for v, d in C.items():
        for B in M.BUDGETS:
            r = d[d.budget == B]
            if not len(r): continue
            r = r.iloc[0]
            rows.append(dict(variant=v, budget=B, km=round(r.km), patches=int(r.patches), perkm_patch_p35=r.perkm_p35, lo=r.perkm_lo, hi=r.perkm_hi,
                             perkm_forest_p35=r.perkm_forest_p35, perkm_forest_p70=r.perkm_forest_p70, pct35=r.pct_forest_p35, pct70=r.pct_forest_p70, pct100=r.pct_forest_p100,
                             insample=r.train_patch_mean / max(r.km, 1e-9), share_patches_saving=r.get('share_patches_saving', np.nan),
                             y22=r.test_patch_2022, y23=r.test_patch_2023, y24=r.test_patch_2024, y25=r.test_patch_2025))
    T = pd.DataFrame(rows); T.to_csv(M.OUT + 'm4_budget_table.csv', index=False)
    with open(M.OUT + 'm4_tables.md', 'w') as f:
        f.write('| variant | budget km | km | patches | patch ha/km/yr p.35 | 95% | forest ha/km/yr p.35 | p.70 | % burnt forest p.35 | p.70 | p1.0 | in-sample patch ha/km/yr | share patches saving held out |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n')
        for r in T.itertuples():
            f.write(f'| {LBL.get(r.variant, r.variant)} | {r.budget} | {r.km} | {r.patches} | {r.perkm_patch_p35:.1f} | {r.lo:.1f}-{r.hi:.1f} | {r.perkm_forest_p35:.1f} | {r.perkm_forest_p70:.1f} | {r.pct35:.2f} | {r.pct70:.2f} | {r.pct100:.2f} | {r.insample:.1f} | {r.share_patches_saving:.2f} |\n')
    print(T.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
