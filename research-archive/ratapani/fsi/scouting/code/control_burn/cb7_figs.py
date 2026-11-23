"""Figures: figs_r29/r29_fig1_clock.png (re-burn ratio by age and burn month), r29_fig2_calendar.png (when the season burns,
litter on the ground, and what a burn on each date prevents)."""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
import cb6_design as D6
FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r29/'


def main():
    A = pd.read_csv(B.OUT + 'cb2_age.csv'); C = pd.read_csv(B.OUT + 'cb2_cross.csv'); E = pd.read_csv(B.OUT + 'cb2_early.csv')
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.arange(len(B.AGE_LAB))
    a = A[A.kind == 'age'].set_index('g').loc[B.AGE_LAB]
    ax[0].errorbar(x, a.ratio, yerr=[a.ratio - a.lo, a.hi - a.ratio], fmt='o-', color='k', capsize=3, label='all burns')
    for m, col in zip(B.MON_LAB, ('tab:blue', 'tab:orange', 'tab:red')):
        am = A[A.kind == 'age x month'].set_index('g')
        ys = [am.ratio.get(f'{m} burn, {l}', np.nan) for l in B.AGE_LAB]
        ax[0].plot(x, ys, 's--', color=col, alpha=.8, label=f'burnt in {m}')
    ax[0].axhline(1, color='grey', lw=.8); ax[0].set_xticks(x); ax[0].set_xticklabels(B.AGE_LAB)
    ax[0].set_ylabel('fire points on burnt ground / expected if not yet burnt'); ax[0].set_xlabel('time since the burn'); ax[0].set_ylim(0, None)
    ax[0].set_title('Within the same season'); ax[0].legend(fontsize=8)
    labs = list(C.g) + list(E.g); vals = list(C.ratio) + list(E.ratio); lo = list(C.lo) + list(E.lo); hi = list(C.hi) + list(E.hi)
    ax[1].barh(range(len(labs)), vals, xerr=[np.array(vals) - np.array(lo), np.array(hi) - np.array(vals)], color='tab:green', capsize=3)
    ax[1].set_yticks(range(len(labs))); ax[1].set_yticklabels(labs, fontsize=8); ax[1].axvline(1, color='grey', lw=.8)
    ax[1].set_xlabel('fire points / expected (same square and week, ground not yet burnt this season)'); ax[1].set_title('Earlier seasons and pre-15 Feb burns')
    plt.tight_layout(); plt.savefig(FIG + 'r29_fig1_clock.png', dpi=130); plt.close()
    W = pd.read_csv(B.OUT + 'cb3_weekly.csv'); w = W.groupby('week')[['ha_all', 'ha_out_patch']].sum() / 9
    fig, ax = plt.subplots(figsize=(10, 4.5))
    days = B.D0 + 7 * np.arange(21) + 3
    ax.bar(days, w.ha_all / 1000, width=6, color='tab:red', alpha=.7, label='forest ha burnt per week (mean of 9 seasons, thousands)')
    ax.set_ylabel('thousand forest ha per week'); ax.set_xlabel('day of year (15 Feb = 46, 1 Apr = 91, 1 May = 121)')
    ax2 = ax.twinx(); dd = np.arange(1, 160)
    ax2.plot(dd, [D6.litter_on_ground(d) for d in dd], color='tab:brown', label='share of the year\'s leaf fall on the ground (no burn)')
    P = pd.read_csv(B.OUT + 'cb6_physics.csv')
    for i, (_, r) in enumerate(P.iterrows()):
        d = D6.BURN_DATES[r.burn_date]; ax2.annotate(f'block burnt {r.burn_date}: {100*r.prevented_share_all:.0f}% of its later burning prevented', (d, 8 + 7 * i), fontsize=7, ha='left', va='bottom', xytext=(2, 0), textcoords='offset points')
        ax.axvline(d, color='grey', ls=':', lw=.8)
    ax2.set_ylabel('% of annual leaf fall'); ax2.set_ylim(0, 110)
    ax.legend(loc='upper left', fontsize=8); ax2.legend(loc='upper right', fontsize=8); ax.set_title('When MP forest burns, when the litter falls, and what a block burn on each date prevents')
    plt.tight_layout(); plt.savefig(FIG + 'r29_fig2_calendar.png', dpi=130); plt.close(); print('figs ok')


if __name__ == '__main__':
    main()
