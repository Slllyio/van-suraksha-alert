"""Figures for squares_v2_pooled.md (from the results tables only)."""
import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
B = pd.read_csv(f'{OUT}/pooled_bins.csv'); G = pd.read_csv(f'{OUT}/gapfit.csv')
# ---- fig 1: pooled outward move against the time gap
fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
for j, (slot, lab) in enumerate([('13:30 day', 'day pairs (13:00-14:30 IST)'), ('01:30 night', 'night pairs (01:30-03:00 IST)')]):
    b = B[(B.dim == 'slot x gap') & B.bin.str.startswith(slot)]
    gm = b.gap_min.values; m = b.mean_m.values; lo = b.lo.values * gm / 60; hi = b.hi.values * gm / 60
    ax[j].errorbar(gm, m, yerr=[m - lo, hi - m], fmt='o', color='C3', capsize=4, label='fires (all MP, 2018-26)')
    nl = b.null_speed.values * gm / 60
    nlo = np.array([float(s.split(' to ')[0]) for s in b.null_ci]) * gm / 60; nhi = np.array([float(s.split(' to ')[1]) for s in b.null_ci]) * gm / 60
    ax[j].errorbar(gm + 2, nl, yerr=[nl - nlo, nhi - nl], fmt='s', color='grey', capsize=4, label='static industrial sites (null)')
    g = G[(G.set == 'fires') & (G.slot == slot) & (G.direction == 'outward')].iloc[0]
    xx = np.linspace(0, 80, 10); ax[j].plot(xx, g.intercept_m + g.speed_m_h * xx / 60, 'C3--', lw=1,
                                            label=f'fit: {g.intercept_m:+.0f} m + {g.speed_m_h:.1f} m/h x gap')
    ax[j].axhline(0, color='k', lw=.5); ax[j].set_xlabel('time between the two looks (min)'); ax[j].set_title(lab)
    ax[j].legend(fontsize=8, loc='lower left')
ax[0].set_ylabel('mean outward move of the fire centre (m)')
plt.tight_layout(); plt.savefig(f'{OUT}/fig1_move_vs_gap.png', dpi=120); plt.close()
# ---- fig 2: diurnal curve
S = pd.read_csv(f'{OUT}/diurnal_segments_noratapani.csv'); F1 = json.load(open(f'{OUT}/diurnal_fit_noratapani.json'))['forest']
F0 = json.load(open(f'{OUT}/diurnal_fit.json'))['forest']; M = json.load(open('/mnt/project-files/research/fire-continuity/results/diurnal.json'))
fig, ax = plt.subplots(figsize=(9, 4.5))
s = S[(S.subset == 'forest') & (S.set == 'fires')]
for r in s.itertuples():
    lo, hi = [float(x) for x in r.ci_m_h.split(' to ')]
    t0, t1 = r.start_ist, r.start_ist + r.gap_h
    segs = [(t0, min(t1, 24))] + ([(0, t1 - 24)] if t1 > 24 else [])
    for a, b_ in segs:
        ax.plot([a, b_], [r.speed_m_h] * 2, color='C3', lw=2.5); ax.fill_between([a, b_], lo, hi, color='C3', alpha=.2)
hh = np.array([float(h) for h in F1['curve']]); ax.plot(hh, list(F1['curve'].values()), 'k-', label='fitted rate curve (fitted outside Ratapani)')
ax.plot([float(h) for h in F0['curve']], list(F0['curve'].values()), 'k:', label='same, all MP')
dh = (hh - M['peak_ist'] + 12) % 24 - 12; r = M['base'] + (1 - M['base']) * np.exp(-dh ** 2 / (2 * M['width_h'] ** 2))
r = r / r.mean() * np.mean(list(F1['curve'].values()))
ax.plot(hh, r, color='C0', ls='--', label='current burning clock (MODIS counts), same daily mean')
ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 3)); ax.axhline(0, color='k', lw=.5)
ax.set_xlabel('hour of day (IST)'); ax.set_ylabel('pooled outward speed (m/h)')
ax.set_title('Forest and scrub fires, MP 2018-26: red bars = one kind of pair each (its time span, 95% range)')
ax.legend(fontsize=8, loc='upper left'); plt.tight_layout(); plt.savefig(f'{OUT}/fig2_diurnal.png', dpi=120); plt.close()
# ---- fig 3: what the speed depends on
dims = [('slot x pixels in both looks', 'pixels in the two looks'), ('slot x FRP (both looks, MW)', 'FRP of the two looks, quintiles within day / night (Q1 low)'),
        ('slot x fire age h', 'hours since first detection here'), ('slot x forest type', 'forest type (VTM)')]
fig, ax = plt.subplots(2, 2, figsize=(12, 8))
for a, (dim, lab) in zip(ax.ravel(), dims):
    for k, (slot, col) in enumerate([('13:30 day', 'C3'), ('01:30 night', 'C0')]):
        b = B[(B.dim == dim) & B.bin.str.startswith(slot)].copy()
        if dim == 'slot x forest type': b = b[b.n >= 1000]
        b['lab'] = b.bin.str.split(', ', n=1).str[1]
        if 'FRP' in dim: b['lab'] = [f'Q{i + 1}' for i in range(len(b))]
        if k == 0: order = list(b.lab)
        b = b.set_index('lab').reindex(order)
        x = np.arange(len(order)) + (k - .5) * .35
        a.errorbar(x, b.speed, yerr=[b.speed - b.lo, b.hi - b.speed], fmt='o', color=col, capsize=3, label=slot)
    a.set_xticks(np.arange(len(order))); a.set_xticklabels(order, rotation=30, ha='right', fontsize=8)
    a.axhline(0, color='k', lw=.5); a.set_title(lab); a.set_ylabel('pooled outward speed (m/h)')
ax[0, 0].legend()
plt.tight_layout(); plt.savefig(f'{OUT}/fig3_dependence.png', dpi=120); plt.close()
print('ok')
