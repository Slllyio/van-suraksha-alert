"""List timing (round 23): tables for the note and figures (out/fig*.png). Run after lt_score.py held/fwd and lt_night.py."""
import sys, os
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/list_timing')
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import lt_score as L
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/list_timing/out/'; SC = L.SC
ORDER = ['A20', 'A16f', 'B06n', 'B06f', 'B09n', 'C_f', 'C_n']


def missed_table():
    rows = []
    for per in ('held', 'fwd'):
        a = pd.read_parquet(SC + f'ev_A20_{per}.parquet').set_index(['division', 'lab'])
        b = pd.read_parquet(SC + f'ev_B06f_{per}.parquet').set_index(['division', 'lab']).loc[a.index]
        m = ~a.caught
        for dn in ('N', 'D'):
            mm = m & (a.dn == dn)
            rows.append(dict(period=per, first_pass='night' if dn == 'N' else 'day', fires=int((a.dn == dn).sum()), missed=int(mm.sum()),
                             missed_within_1km_of_flag=int(a.ext2[mm].sum()), missed_within_2_5km=int(a.ext5[mm].sum()),
                             missed_but_caught_by_B06f=int(b.caught[mm].sum()), caught_A_lost_by_B06f=int((a.caught & ~b.caught & (a.dn == dn)).sum())))
    T = pd.DataFrame(rows); T.to_csv(OUT + 'missed_A20.csv', index=False); print(T.to_string())


def fig_timeline():
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for d0 in (0, 24):
        for h, lab, c in ((1.5, 'VIIRS night\n(3 sats, 00:40-03:20)', '#3b5b92'), (13.4, 'VIIRS day\n(12:00-14:50)', '#d08b2a')):
            ax.axvspan(d0 + h - 0.9, d0 + h + 0.9, ymin=0.70, ymax=0.95, color=c, alpha=.85)
            if d0 == 0: ax.text(h, 0.99, lab, ha='center', va='bottom', fontsize=8, transform=ax.get_xaxis_transform())
        for h, lab in ((10.5, 'Terra'), (22.0, 'Terra')):
            ax.plot([d0 + h], [0.8], 'k|', ms=12, transform=ax.get_xaxis_transform())
    # arrival bands
    for y0, lab, dl in ((0.45, 'FSI SMS (+0.75-1.75 h)', (0.75, 1.75)), (0.22, 'NASA NRT (+4.5-6 h)', (4.5, 6))):
        for d0 in (0, 24):
            for h0, h1 in ((0.67, 3.35), (12.0, 14.83)):
                ax.axvspan(d0 + h0 + dl[0], d0 + h1 + dl[1], ymin=y0, ymax=y0 + 0.15, color='#888', alpha=.45)
        ax.text(-0.5, y0 + 0.07, lab, ha='right', va='center', fontsize=8, transform=ax.get_xaxis_transform())
    for h, lab, c in ((20, 'A 20:00', '#b22'), (16, "A' 16:00", '#e77'), (30, 'B 06:00', '#2a7'), (33, "B' 09:00", '#7c9'), (40, 'C 16:00', '#2a7')):
        ax.axvline(h, color=c, lw=1.6); ax.text(h, 0.04, lab, rotation=90, fontsize=8, color=c, ha='right', va='bottom', transform=ax.get_xaxis_transform())
    ax.set_xlim(-0.5, 48); ax.set_yticks([]); ax.set_xticks(range(0, 49, 3)); ax.set_xticklabels([f'{h % 24:02d}' for h in range(0, 49, 3)])
    ax.set_xlabel('IST hour (day t, then day t+1)'); ax.set_title('When passes happen (ticks: MODIS Terra), when the points arrive, and when each list can go out', fontsize=10, pad=30)
    fig.tight_layout(); fig.savefig(OUT + 'fig1_timeline.png', dpi=130); plt.close(fig)


def fig_scores():
    fig, axs = plt.subplots(1, 2, figsize=(11, 4), sharey=False)
    for ax, k, lab in ((axs[0], 'all', 'All fires'), (axs[1], 'new', 'Brand-new fires')):
        for j, per in enumerate(('held', 'fwd')):
            T = pd.read_csv(OUT + f'schedules_{per}.csv').set_index('sched').loc[ORDER]
            x = np.arange(len(T)) + (j - 0.5) * 0.36
            ax.bar(x, T[k], 0.34, yerr=[T[k] - T[f'{k}_lo'], T[f'{k}_hi'] - T[k]], capsize=2, label='held-out 2022-24' if per == 'held' else 'forward 2025-26',
                   color='#4c72b0' if per == 'held' else '#dd8452')
        ax.set_xticks(range(len(ORDER))); ax.set_xticklabels([L.LABEL[s] for s in ORDER], rotation=35, ha='right', fontsize=8)
        lo = min(pd.read_csv(OUT + f'schedules_{p}.csv')[k].min() for p in ('held', 'fwd'))
        ax.set_ylim(lo - 6, None); ax.set_ylabel('% caught (strict, at the same ground)'); ax.set_title(lab, fontsize=10)
    axs[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT + 'fig2_catch_by_schedule.png', dpi=130); plt.close(fig)


def fig_lead():
    fig, ax = plt.subplots(figsize=(9, 3.8)); data = []
    for s in ORDER:
        e = pd.read_parquet(SC + f'ev_{s}_held.parquet'); data.append(e.lead_last_h[e.caught].values)
    ax.boxplot(data, whis=(5, 95), showfliers=False); ax.set_xticks(range(1, len(ORDER) + 1)); ax.set_xticklabels([L.LABEL[s] for s in ORDER], rotation=30, ha='right', fontsize=8)
    ax.set_ylabel('hours from the freshest list that\nflagged the fire to its first detection'); ax.set_title('Lead time for caught fires (held-out 2022-24; box = middle half, whiskers 5-95%)', fontsize=10)
    fig.tight_layout(); fig.savefig(OUT + 'fig3_lead_time.png', dpi=130); plt.close(fig)


def fig_night():
    v = L.C.load_det(range(2019, 2027)); v = v[v.type == 0]; md = v.ld.dt.month * 100 + v.ld.dt.day; v = v[(md >= 215) & (md <= 531)]
    import features as Fe
    U = Fe.base()['U']; v = v[np.isin(v.row.values * L.C.W + v.col.values, U)]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6)); b = np.logspace(-1, 2.5, 50)
    for dn, c, lab in (('D', '#d08b2a', 'day pass'), ('N', '#3b5b92', 'night pass')):
        axs[0].hist(v.frp[v.daynight == dn].clip(0.1, 300), bins=b, histtype='step', lw=1.8, color=c, density=True, label=f'{lab} (median {v.frp[v.daynight == dn].median():.1f} MW)')
    axs[0].set_xscale('log'); axs[0].set_xlabel('FRP (MW), VIIRS type-0 points, 10 divisions 2019-26'); axs[0].legend(fontsize=8); axs[0].set_yticks([])
    F = pd.read_csv(OUT + 'night_fires_by_pass.csv'); F = F[F.fires.isin(['all', 'brand-new', 'other'])]
    x = np.arange(3)
    for j, per in enumerate(('held', 'fwd')):
        f = F[F.period == per].set_index('fires').loc[['all', 'brand-new', 'other']]
        axs[1].bar(x + (j - .5) * .36, f.night_pct, .34, label='held-out' if per == 'held' else 'forward', color='#4c72b0' if per == 'held' else '#dd8452')
    axs[1].axhline(37.1, color='k', ls='--', lw=1); axs[1].text(2.45, 37.6, 'night share of all points', ha='right', fontsize=8)
    axs[1].set_xticks(x); axs[1].set_xticklabels(['all fires', 'brand-new', 'other']); axs[1].set_ylabel('% first seen on the night pass'); axs[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT + 'fig4_night_vs_day.png', dpi=130); plt.close(fig)


if __name__ == '__main__':
    missed_table(); fig_timeline(); fig_scores(); fig_lead(); fig_night()
    for per in ('held', 'fwd'):
        print(pd.read_csv(OUT + f'schedules_{per}.csv').round(1).to_string())
