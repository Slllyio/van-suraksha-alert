"""Physics with the FSI thread's barrier layer, scored against the polygon outlines (Oct 15).
  python3 barrier_phys.py k/n out.parquet
Per fire (the 1,214 scarred S-NPP fires with a grown polygon) and per variant: Sorensen at the polygon's area (shape only), per-fire AUC,
free run burned area and Sorensen at 26 h and 48 h after the first detection, later-pass hits (within 240 m) at the polygon area and at 26 h.
Variants: none | ms (current: Microsoft roads hard) | p50 (segments with far-fire stop probability >= 0.5 hard: OSM roads, rail, roads >= 10 m,
TomTom roads, streams >= 5 km2) | all (every mapped line hard) | draw (3 draws, each segment holds with its stop probability; pixels ranked by
their mean arrival time) | ms_pp (ms + ground burned earlier this season by the scar polygons counts as consumed)."""
import os; os.environ['SCAR_GROWN'] = '1'
import numpy as np, pandas as pd, sys, time
import sim, score, grown, footprint
from sklearn.metrics import roc_auc_score
score.scar_footprint = grown.scar_footprint
BASE = dict(footprint.CFG)
VARIANTS = {'none': dict(barriers=False), 'ms': dict(barriers='ms'), 'p50': dict(barriers='p50'), 'all': dict(barriers='all'),
            'draw': dict(barriers='draw'), 'ms_pp': dict(barriers='ms', preburn_poly=True), 'ms_wind': dict(barriers='ms', wind=True)}   # ms_wind: audit item 5, wind by regime
NDRAW = 3


def run(ev, wx, cfg, e):
    if cfg['barriers'] == 'draw':
        Ts = []
        for d in range(NDRAW):
            c = dict(cfg, seed=d * 1000003 + int(e)); o = sim.run_event(ev, wx, c, hours=48, scar_fn=score.scar_footprint)
            Ts.append(np.minimum(tph_of(o, ev), 96.0))
        return o, np.mean(Ts, axis=0)
    o = sim.run_event(ev, wx, cfg, hours=48, scar_fn=score.scar_footprint)
    return o, np.minimum(tph_of(o, ev), 96.0)


def tph_of(o, ev):
    tfirst = (ev.t.min() - o['t0']).total_seconds() / 60
    t = (o['T'] - tfirst) / 60.0
    return np.where(np.isfinite(t), t, 96.0)


def main(k_n, out):
    v, ids = footprint.events(k_n); wx = {}; rows = []; tt = time.time()
    for k, e in enumerate(ids):
        ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        first = ev[ev.overpass == ev.overpass.min()]
        later = ev[(ev.t >= ev.t.min() + pd.Timedelta(hours=6)) & (ev.t <= ev.t.min() + pd.Timedelta(hours=72))]
        for name, over in VARIANTS.items():
            cfg = {**BASE, **over}
            o, tph = run(ev, wx[s], cfg, e)
            S, B, (i0, i1, j0, j1) = o['S'], o['burnable'], o['win']
            yy, xx = np.mgrid[i0:i1, j0:j1]
            px = sim.X0 + xx * sim.RES + sim.RES / 2; py = sim.Y0 - yy * sim.RES - sim.RES / 2
            d_near = np.full(px.shape, np.inf)
            for a, b in zip(first.x.values, first.y.values):
                d_near = np.minimum(d_near, np.hypot(px - a, py - b))
            mask = np.isin(sim.WC[i0:i1, j0:j1], [10, 20, 30]) & (d_near <= footprint.R_MAX)   # same candidate set for every variant
            n = int(S.sum()); y = S[mask]
            Pp = score.topn(tph, mask, n)
            P26 = mask & (tph <= 26); P48 = mask & (tph <= 48)
            row = dict(event=int(e), season=s, variant=name, scar_px=n, n_mask=int(mask.sum()), n_burnable=int((B & mask).sum()),
                       sor=score.soren(Pp, S), auc=roc_auc_score(y, -tph[mask]) if 0 < y.sum() < len(y) else np.nan,
                       area26=int(P26.sum()), sor26=score.soren(P26, S), area48=int(P48.sum()), sor48=score.soren(P48, S))
            if len(later):
                r, c = sim.rc(later.x.values, later.y.values); r -= i0; c -= j0; h = h26 = 0
                for a, b in zip(r, c):
                    sl = (slice(max(a - 12, 0), a + 13), slice(max(b - 12, 0), b + 13))
                    h += bool(Pp[sl].any()); h26 += bool(P26[sl].any())
                row.update(n_later=len(later), hit=h, hit26=h26)
            rows.append(row)
        if k % 25 == 0:
            print(k, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
