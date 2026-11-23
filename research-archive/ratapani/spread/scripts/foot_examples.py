"""Maps of the learned footprint for example fires: probability of burning per 20 m pixel from the first VIIRS pass, and the
equal-area footprints of the learned model, the circle and the physics model against the mapped scar.
Usage: foot_examples.py modeldir event[,event...] outdir"""
import numpy as np, pandas as pd, sys, os, json
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import lightgbm as lgb
import sim, score, footprint as fp
mdir, events, outdir = sys.argv[1], [int(x) for x in sys.argv[2].split(',')], sys.argv[3]; os.makedirs(outdir, exist_ok=True)
v, _ = fp.events(); wx = {}; summ = []
for e in events:
    ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    X, y, meta = fp.fire_features(ev, wx[s]); m = lgb.Booster(model_file=f'{mdir}/loso_{s}.txt')
    S, B, mask, (i0, i1, j0, j1), d_near, tph = meta['S'], meta['B'], meta['mask'], meta['win'], meta['d_near'], meta['tph']
    p = np.zeros(S.shape, np.float32); p[mask] = m.predict(X)
    n = int(S.sum()); top = lambda sc, nn: score.topn(-sc, mask, nn)
    Pl, Pc, Pp = top(p, n), top(-d_near, n), top(-tph, n); n_pred = int(round(float(p[mask].sum()))); Pl_f = top(p, n_pred)
    mm = S | mask; rr, cc = np.nonzero(mm); pad = 10
    a0, a1 = max(rr.min() - pad, 0), min(rr.max() + pad, mm.shape[0]); b0, b1 = max(cc.min() - pad, 0), min(cc.max() + pad, mm.shape[1]); crop = (slice(a0, a1), slice(b0, b1))
    x0, x1 = sim.X0 + (j0 + b0) * sim.RES, sim.X0 + (j0 + b1) * sim.RES; y1, y0 = sim.Y0 - (i0 + a0) * sim.RES, sim.Y0 - (i0 + a1) * sim.RES; ext = (x0, x1, y0, y1)
    hs = LightSource(azdeg=315, altdeg=45).hillshade(sim.ELEV[i0 + a0:i0 + a1, j0 + b0:j0 + b1].astype(float), vert_exag=2, dx=20, dy=20)
    first = ev[ev.overpass == ev.overpass.min()]
    fig, axs = plt.subplots(1, 2, figsize=(15, 7.5))
    ax = axs[0]; ax.imshow(hs, cmap='gray', extent=ext, origin='upper', vmin=0, vmax=1)
    im = ax.imshow(np.ma.masked_where(~mask[crop], p[crop]), cmap='magma', vmin=0, vmax=max(float(np.percentile(p[mask], 99)), 0.05), extent=ext, origin='upper', alpha=0.85)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label='chance the pixel burns in this fire (learned from 2017-24 scars, season held out)')
    ax.contour(S[crop].astype(float), levels=[0.5], colors=['cyan'], linewidths=1.8, extent=ext, origin='upper')
    ax.scatter(first.x, first.y, s=120, marker='*', color='lime', edgecolor='k', zorder=5, label='first VIIRS pass'); ax.scatter(ev.x, ev.y, s=25, facecolor='none', edgecolor='white', zorder=4, label='all passes')
    ax.plot([], [], color='cyan', lw=1.8, label=f'mapped scar ({n * 0.04:.0f} ha)'); ax.legend(loc='lower left', fontsize=8); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f'Fire {e} ({s}): learned burn chance from the first pass; expected area {n_pred * 0.04:.0f} ha', fontsize=10)
    ax = axs[1]; ax.imshow(hs, cmap='gray', extent=ext, origin='upper', vmin=0, vmax=1)
    for M, col, lab in [(Pc, 'white', f'circle, scar area: Sorensen {score.soren(Pc, S):.2f}'), (Pp, 'yellow', f'physics, scar area: {score.soren(Pp, S):.2f}'), (Pl, 'magenta', f'learned, scar area: {score.soren(Pl, S):.2f}'), (Pl_f, 'orange', f'learned, own area ({n_pred * 0.04:.0f} ha): {score.soren(Pl_f, S):.2f}')]:
        ax.contour(M[crop].astype(float), levels=[0.5], colors=[col], linewidths=1.6, extent=ext, origin='upper', linestyles='-' if col != 'orange' else '--'); ax.plot([], [], color=col, lw=1.6, ls='-' if col != 'orange' else '--', label=lab)
    ax.contour(S[crop].astype(float), levels=[0.5], colors=['cyan'], linewidths=2.2, extent=ext, origin='upper'); ax.plot([], [], color='cyan', lw=2.2, label='mapped scar')
    ax.scatter(first.x, first.y, s=120, marker='*', color='lime', edgecolor='k', zorder=5); ax.legend(loc='lower left', fontsize=8); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title('equal-area footprints against the scar', fontsize=10)
    fig.tight_layout(); fig.savefig(f'{outdir}/learned_{s}_{e}.png', dpi=100); plt.close(fig)
    summ.append(dict(event=e, season=s, scar_ha=n * 0.04, learned_area_ha=n_pred * 0.04, sor_learned=round(score.soren(Pl, S), 3), sor_circle=round(score.soren(Pc, S), 3), sor_physics=round(score.soren(Pp, S), 3), sor_learned_own_area=round(score.soren(Pl_f, S), 3)))
    print(summ[-1], flush=True)
json.dump(summ, open(f'{outdir}/learned_summary.json', 'w'), indent=1)
