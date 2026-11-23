"""Step 6. Figures for repeat_patch_fire_lines.md (reads out/tables.json, scratch r26 entries/patches/tests)."""
import json, pickle
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from scipy import ndimage as ndi
import c26 as C

T = json.load(open(C.OUT + 'tables.json'))
SETN = lambda k: 'core' if k in C.CORE else 'rest'


def fig_repeat():
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    for grp, col in (('core', 'C1'), ('rest', 'C0')):
        if grp not in T['hist_indep']: continue
        o = np.array(T['hist'][grp]); e = np.array(T['hist_indep'][grp])
        x = np.arange(1, 10); ax[0].plot(x, o[1:] / o[1:].sum() * 100, 'o-', color=col, label=f'{grp}: observed')
        ax[0].plot(x, e[1:] / e[1:].sum() * 100, 's--', color=col, alpha=.6, label=f'{grp}: if seasons were independent')
    ax[0].set_yscale('log'); ax[0].set_xlabel('seasons burnt, 2017-25 (120 m forest cells that burnt at least once)'); ax[0].set_ylabel('% of burnt-at-least-once cells')
    ax[0].legend(fontsize=8); ax[0].set_title('How often the same 120 m of forest burns')
    S1 = pd.DataFrame(T['step1'])
    for grp, col in (('core', 'C1'), ('rest', 'C0')):
        r = S1[(S1.grp == grp) & (S1.set == 'tr3')]
        if not len(r): continue
        r = r.iloc[0]; ys = list(C.ALL)
        ax[1].plot(ys, [r[str(y)] if str(y) in r else r[y] for y in ys], 'o-', color=col, label=f'{grp}: patches = {r.pct_forest}% of forest')
    ax[1].axvspan(2016.5, 2021.5, color='0.9'); ax[1].text(2017, 2, 'seasons that define the patches', fontsize=8)
    ax[1].set_ylabel("% of the season's burnt forest inside the patches"); ax[1].set_ylim(0, None)
    ax[1].set_title('Patches burnt in >=3 of 2017-21: share of each season\'s burning'); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(C.OUT + 'fig_repeat.png', dpi=110); plt.close(fig)


def fig_entries():
    E = pd.read_parquet(C.SC + 'entries_tr3.parquet'); S = pd.read_parquet(C.SC + 'patches_tr3.parquet')
    E['grp'] = E.key.map(SETN); S['grp'] = S.key.map(SETN)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    labs = ['started inside', 'started at the edge (<400 m)', 'came from outside (>=400 m)', 'not connected to the start']
    cols = ['C3', 'C1', 'C2', '0.6']
    xs = []
    for i, (grp, per) in enumerate([(g, p) for g in ('core', 'rest') for p in ('2017-21', '2022-25')]):
        e = E[(E.grp == grp) & E.year.isin(C.TRAIN if per == '2017-21' else C.TEST)]
        d = e.sort_values('burn_ha', ascending=False).drop_duplicates(['key', 'patch', 'year'])
        if not len(d): continue
        v = [(d.status == 'inside').mean(), ((d.status == 'entered') & ~d.from_out.fillna(False).astype(bool)).mean(),
             ((d.status == 'entered') & d.from_out.fillna(False).astype(bool)).mean(), d.status.isin(['unreached', 'no_start']).mean()]
        b = 0
        for j, vv in enumerate(v):
            ax[0].bar(i, vv * 100, bottom=b, color=cols[j], label=labs[j] if i == 0 else None); b += vv * 100
        xs.append(f'{grp}\n{per}\n(n={len(d)})')
    ax[0].set_xticks(range(len(xs))); ax[0].set_xticklabels(xs, fontsize=8); ax[0].set_ylabel('% of patch-seasons'); ax[0].legend(fontsize=7, loc='lower right')
    ax[0].set_title('Where the main fire of each patch-season started')
    s3 = S[S.n_entered >= 3]
    for grp, col in (('core', 'C1'), ('rest', 'C0')):
        q = s3[s3.grp == grp]
        ax[1].scatter(q.chance_share + np.random.default_rng(1).normal(0, .007, len(q)), q.mode_share + np.random.default_rng(2).normal(0, .007, len(q)), s=8, alpha=.5, color=col, label=f'{grp} ({len(q)} patches)')
    ax[1].plot([0, 1], [0, 1], 'k--', lw=1); ax[1].axhline(.6, color='0.5', lw=.8)
    ax[1].set_xlabel('top-segment share expected by chance (same entries, random segment)'); ax[1].set_ylabel('observed share through the top ~1 km segment')
    ax[1].set_title('Patches with >=3 entries (2017-21): same side or chance?'); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(C.OUT + 'fig_entries.png', dpi=110); plt.close(fig)


def fig_test():
    D = pd.DataFrame(T['test']); D = D[D.p == 0.35]
    M = [('entry', 'entry-side lines\n(proposed)'), ('rand_edge', 'other edge segment\nof same patch'), ('ring', 'whole perimeter\nring'), ('road', 'nearest\nexisting track'), ('r25_same_km', 'round-25 plan,\nsame km')]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    for a, grp in zip(ax, ('core', 'rest')):
        for j, (w, col) in enumerate((('all', 'C0'), ('patch', 'C2'))):
            for i, (m, lab) in enumerate(M):
                r = D[(D.grp == grp) & (D.method == m) & (D.what == w)]
                if not len(r): continue
                r = r.iloc[0]; x = i + (j - .5) * .38
                a.bar(x, r.test, .36, color=col, label=('all ground cut off' if w == 'all' else 'forest of the patch itself') if i == 0 else None)
                a.errorbar(x, r.test, yerr=[[r.test - r.lo], [r.hi - r.test]], color='k', lw=1, capsize=2)
        a.set_xticks(range(len(M))); a.set_xticklabels([l for _, l in M], fontsize=8); a.set_ylabel('ha saved per km of line per year (stop chance 0.35)')
        a.set_title(f'{grp}: held-out 2022-25'); a.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(C.OUT + 'fig_test.png', dpi=110); plt.close(fig)


def fig_examples(picks):
    E = pd.read_parquet(C.SC + 'entries_tr3.parquet'); RG = pickle.load(open(C.SC + 'rings_tr3.pkl', 'rb'))
    S = pd.read_parquet(C.SC + 'patches_tr3.parquet')
    fig, axs = plt.subplots(2, 2, figsize=(10, 10.4)); axs = axs.ravel()
    for ax, (k, p) in zip(np.atleast_1d(axs), picks):
        L = pickle.load(open(C.SC + f'fires_{k}.pkl', 'rb')); Z = np.load(C.SC + f'patches_{k}.npz'); W = L['W']
        lab = Z['lab_tr3']; cnt = Z['cnt_tr']; m = RG['meta'][k][p]; ring, seg = RG['rings'][k][p]; s = S[(S.key == k) & (S.patch == p)].iloc[0]
        cx, cy = m['cx'], m['cy']; rr = ring // W; cc = ring % W
        half = max(25, int(max(np.ptp(rr), np.ptp(cc)) / 2) + 25)
        c0, c1, r0, r1 = int(cx - half), int(cx + half), int(cy - half), int(cy + half)
        b0, b1, a0, a1 = c0 // 2, c1 // 2, r0 // 2, r1 // 2
        sub = cnt[max(a0, 0):a1, max(b0, 0):b1]
        b0, a0 = max(b0, 0), max(a0, 0); sub = cnt[a0:a1, b0:b1]
        ax.imshow(sub, cmap='YlOrRd', vmin=0, vmax=5, extent=(b0 * 2 - .5, b0 * 2 + sub.shape[1] * 2 - .5, a0 * 2 + sub.shape[0] * 2 - .5, a0 * 2 - .5), interpolation='nearest')
        pm = np.kron(lab[a0:a1, b0:b1] == p, np.ones((2, 2)))
        ax.contour(np.arange(pm.shape[1]) + b0 * 2, np.arange(pm.shape[0]) + a0 * 2, pm, levels=[.5], colors='k', linewidths=1.2)
        line = ring[seg == s.mode_seg]
        ax.plot(line % W, line // W, 's', ms=2.2, color='cyan', mec='b', mew=.3, label='proposed line (2017-21 entries)')
        e = E[(E.key == k) & (E.patch == p)].sort_values('burn_ha', ascending=False).drop_duplicates('year')
        for _, q in e.iterrows():
            col = 'C2' if q.year in C.TRAIN else 'C0'
            if q.status == 'entered':
                sx, sy = np.clip(q.sx, c0 + 1, c1 - 1), np.clip(q.sy, r0 + 1, r1 - 1)
                ax.annotate('', xy=(q.ex, q.ey), xytext=(sx, sy), arrowprops=dict(arrowstyle='->', color=col, lw=1.6), annotation_clip=False).arrow_patch.set_clip_box(ax.bbox)
                ax.text(sx, sy, str(q.year)[2:], fontsize=7, color=col)
            elif q.status == 'inside':
                ax.plot(cx, cy, 'x', color=col, ms=6); ax.text(cx + 1, cy + 1 + (q.year % 5) * 2, f'{str(q.year)[2:]} in', fontsize=7, color=col)
        ax.set_xlim(c0, c1); ax.set_ylim(r1, r0)
        for ch in ax.get_children():
            if hasattr(ch, 'set_clip_on'): ch.set_clip_on(True); ax.set_xticks([]); ax.set_yticks([])
        tl = e[e.year.isin(C.TEST)]
        ax.set_title(f"{L['div']} patch {p}: {m['forest_ha']:.0f} ha\n2017-21: {int(s.n_entered)} entries, {s.mode_share:.0%} via line; 2022-25: "
                     f"{int(((tl.status == 'entered') & (tl.seg == s.mode_seg)).sum())} of {len(tl)} via line", fontsize=8)
        ax.plot([c0 + 3, c0 + 3 + 1000 / C.RES], [r1 - 3, r1 - 3], 'k-', lw=3); ax.text(c0 + 3, r1 - 5, '1 km', fontsize=7)
    np.atleast_1d(axs)[0].legend(handles=[plt.Line2D([], [], color='C2', lw=1.6, label='entry 2017-21 (start -> entry)'), plt.Line2D([], [], color='C0', lw=1.6, label='entry 2022-25 (held out)'),
                                           plt.Line2D([], [], color='cyan', marker='s', ls='', label='proposed line'), plt.Line2D([], [], color='k', marker='x', ls='', label='started inside')], fontsize=7, loc='lower right')
    fig.tight_layout(); fig.savefig(C.OUT + 'fig_examples.png', dpi=110); plt.close(fig)


if __name__ == '__main__':
    import sys
    fig_repeat(); fig_entries(); fig_test()
    PL = pd.read_csv(C.OUT + 'test_lines.csv')
    if len(sys.argv) > 1: picks = [(a.split(':')[0], int(a.split(':')[1])) for a in sys.argv[1:]]
    else:
        PL['score'] = PL.test_patch_ha + 20 * PL.test_through_line
        picks = [tuple(x) for x in PL.sort_values('score', ascending=False).drop_duplicates('key')[['key', 'patch']].head(4).values]
    fig_examples(picks)
