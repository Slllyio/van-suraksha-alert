"""Maps of the learned restart for example fires: one panel per satellite pass (what was known, where the next pass was
forecast at the persistence area by the learned model and by persistence itself, where it actually showed up), plus the
end footprint at the scar's area. Usage: lr_examples.py modeldir event[,event...] outdir"""
import numpy as np, pandas as pd, sys, os, json
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import lightgbm as lgb
import sim, score, foot_restart as fr
mdir, events, outdir = sys.argv[1], [int(x) for x in sys.argv[2].split(',')], sys.argv[3]; os.makedirs(outdir, exist_ok=True)
v, _ = fr.events(); wx = {}; summ = []
cols = ['lime', 'yellow', 'orange', 'red', 'deeppink', 'violet', 'white']
for e in events:
    st = fr.fire_setup(v[v.event == e])
    if st is None:
        continue
    ev, passes, win, S = st; s = int(ev.season.iloc[0]); i0, i1, j0, j1 = win
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    Mn, Ms = lgb.Booster(model_file=f'{mdir}/next_{s}.txt'), lgb.Booster(model_file=f'{mdir}/scar_{s}.txt')
    F, B, cid = fr.fire_static(ev, win)
    steps = []
    for k in range(1, len(passes) + 1):
        X, yn, ys, m = fr.step_rows(ev, passes, k, F, B, cid, S, win, wx[s], False)
        pn = np.zeros(S.shape, np.float32); pn[m['mask']] = Mn.predict(X); ps = np.zeros(S.shape, np.float32); ps[m['mask']] = Ms.predict(X)
        steps.append((k, m, pn, ps, X))
    # crop around everything
    mm = S.copy()
    for k, m, pn, ps, X in steps:
        mm |= m['d_all'] <= fr.PERS
    rr, cc = np.nonzero(mm); pad = 15
    a0, a1 = max(rr.min() - pad, 0), min(rr.max() + pad, mm.shape[0]); b0, b1 = max(cc.min() - pad, 0), min(cc.max() + pad, mm.shape[1]); crop = (slice(a0, a1), slice(b0, b1))
    x0, x1 = sim.X0 + (j0 + b0) * sim.RES, sim.X0 + (j0 + b1) * sim.RES; y1, y0 = sim.Y0 - (i0 + a0) * sim.RES, sim.Y0 - (i0 + a1) * sim.RES; ext = (x0, x1, y0, y1)
    hs = LightSource(azdeg=315, altdeg=45).hillshade(sim.ELEV[i0 + a0:i0 + a1, j0 + b0:j0 + b1].astype(float), vert_exag=2, dx=20, dy=20)
    n = len(steps); fig, axs = plt.subplots(1, n, figsize=(6.5 * n, 6.5), squeeze=False); rows = []
    for ax, (k, m, pn, ps, X) in zip(axs[0], steps):
        mask, d_all, known, target = m['mask'], m['d_all'], m['known'], m['target']
        ax.imshow(hs, cmap='gray', extent=ext, origin='upper', vmin=0, vmax=1)
        ax.contour(S[crop].astype(float), levels=[0.5], colors=['cyan'], linewidths=2, extent=ext, origin='upper'); ax.plot([], [], color='cyan', lw=2, label=f'mapped scar ({S.sum() * 0.04:.0f} ha)')
        top = lambda sc, nn: score.topn(-sc, mask, nn)
        if target is not None:
            Pm = mask & (d_all <= fr.PERS); n_p = int(Pm.sum()); Pl = top(pn, n_p)
            ax.imshow(np.ma.masked_where(~Pl[crop], np.ones_like(hs)), cmap='spring', extent=ext, origin='upper', alpha=0.45, vmin=0, vmax=2)
            ax.contour(Pm[crop].astype(float), levels=[0.5], colors=['white'], linewidths=1.4, extent=ext, origin='upper', linestyles='--')
            hl, hp = fr.hits(target, Pl, win), fr.hits(target, Pm, win)
            ax.plot([], [], color='magenta', lw=6, alpha=0.45, label=f'learned, {n_p * 0.04:.0f} ha: next pass hit {hl}/{len(target)}')
            ax.plot([], [], color='white', lw=1.4, ls='--', label=f'persistence (475 m), same area: hit {hp}/{len(target)}')
            ax.scatter(target.x, target.y, s=90, marker='x', color='red', lw=2, zorder=6, label=f'next pass, +{float(X[0, fr.FEATS.index("lead_h")]):.0f} h')
            rows.append(dict(event=e, season=s, k=k, hit_learn=hl, hit_pers=hp, n_target=len(target), area_ha=n_p * 0.04))
            ttl = f'Fire {e} ({s}), after pass {k}: where will pass {k + 1} show fire?'
        else:
            nn = int(S.sum()); Pl, Pd = top(ps, nn), top(-d_all, nn)
            ax.contour(Pl[crop].astype(float), levels=[0.5], colors=['magenta'], linewidths=1.8, extent=ext, origin='upper'); ax.plot([], [], color='magenta', lw=1.8, label=f'learned end footprint, scar area: Sorensen {score.soren(Pl, S):.2f}')
            ax.contour(Pd[crop].astype(float), levels=[0.5], colors=['white'], linewidths=1.4, extent=ext, origin='upper', linestyles='--'); ax.plot([], [], color='white', lw=1.4, ls='--', label=f'distance from all passes, scar area: {score.soren(Pd, S):.2f}')
            rows.append(dict(event=e, season=s, k=k, sor_learn=round(score.soren(Pl, S), 3), sor_dist=round(score.soren(Pd, S), 3)))
            ttl = f'Fire {e} ({s}), all {len(passes)} passes known: where did it end?'
        for q, p_ in enumerate(passes[:k]):
            sub = ev[ev.overpass == p_]; ax.scatter(sub.x, sub.y, s=70, marker='*' if q == 0 else 'o', color=cols[q % len(cols)], edgecolor='k', zorder=5, label=f'pass {q + 1} ({sub.t.min().strftime("%d %b %H:%M")} UTC)')
        ax.legend(loc='lower left', fontsize=7.5); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(ttl, fontsize=10)
    fig.tight_layout(); fig.savefig(f'{outdir}/restart_{s}_{e}.png', dpi=95); plt.close(fig); summ += rows; print(rows, flush=True)
json.dump(summ, open(f'{outdir}/restart_summary.json', 'w'), indent=1)
