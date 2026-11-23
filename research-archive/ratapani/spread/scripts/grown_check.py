"""Where does the scar thread's grown polygon differ from the raster label, pixel by pixel? For each fire: the polygon-only
pixels are classed by the research thread's burn rasters: never burned in the rasters, burned with a window overlapping the
fire's detection days (same fire, dropped by the 400 m connectivity rule), window before the fire (earlier burn), window
after the fire (later burn). -> data/grown_check.parquet"""
import numpy as np, pandas as pd, sys
import sim, score, grown
_NPZ = sim.G
class _G(dict):
    def __missing__(self, k):
        a = _NPZ[k]
        if k.startswith('burn_'):
            if len(self) > 8: self.pop(next(iter(self)))
            self[k] = a
        return a
sim.G = _G()
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); st = grown.load(); ok = set(pd.read_parquet(f'{sim.DATA}/rundir.parquet').event.values)
pad = int(2600 / sim.RES); rows = []
for e, ev in v.groupby('event'):
    if e not in st or e not in ok:
        continue
    s = int(ev.season.iloc[0]); r, c = sim.rc(ev.x.values, ev.y.values)
    i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX); win = (i0, i1, j0, j1)
    S, _ = score.scar_footprint(dict(win=win, season=s), ev); Gm, _ = grown.scar_footprint(dict(win=win), ev)
    be = sim.G[f'burn_end_{s}'][i0:i1, j0:j1]; bs = sim.G[f'burn_start_{s}'][i0:i1, j0:j1]
    d0, d1 = ev.t.min().dayofyear, ev.t.max().dayofyear
    only = Gm & ~S; n = int(only.sum())
    burned = be > -999
    overlap = burned & (be >= d0) & (bs <= d1); before = burned & (be < d0); after = burned & (bs > d1)
    # distance of polygon-only ground from the first-pass detections
    first = ev[ev.overpass == ev.overpass.min()]
    yy, xx = np.mgrid[i0:i1, j0:j1]; px = sim.X0 + xx * sim.RES + sim.RES / 2; py = sim.Y0 - yy * sim.RES - sim.RES / 2
    d = np.full(px.shape, np.inf)
    for a, b in zip(first.x.values, first.y.values):
        d = np.minimum(d, np.hypot(px - a, py - b))
    rows.append(dict(event=e, season=s, n_pass=ev.overpass.nunique(), raster_px=int(S.sum()), grown_px=int(Gm.sum()), only_px=n,
                     only_never=float((only & ~burned).sum() / max(n, 1)), only_overlap=float((only & overlap).sum() / max(n, 1)),
                     only_before=float((only & before).sum() / max(n, 1)), only_after=float((only & after).sum() / max(n, 1)),
                     only_beyond2500=float((only & (d > 2500)).sum() / max(n, 1)), grown_beyond2500=float((Gm & (d > 2500)).sum() / max(int(Gm.sum()), 1)),
                     only_median_dist=float(np.median(d[only])) if n else np.nan, raster_median_dist=float(np.median(d[S])) if S.any() else np.nan,
                     after_gap_days=float(np.median(bs[only & after] - d1)) if (only & after).any() else np.nan))
d = pd.DataFrame(rows); d.to_parquet(f'{sim.DATA}/grown_check.parquet')
w = d.only_px
print('fires', len(d), 'polygon-only ground median ha', round(d.only_px.median() * .04, 1), '(raster label median', round(d.raster_px.median() * .04, 1), ')')
for c in ['only_never', 'only_overlap', 'only_before', 'only_after', 'only_beyond2500']:
    print(f'{c:16s} pixel-weighted share {np.average(d[c], weights=w):.3f}   median per fire {d[c].median():.3f}')
print('median gap (days) between the fire and a LATER raster burn on polygon-only ground:', round(d.after_gap_days.median(), 1))
print('median distance from the first pass: raster label', round(d.raster_median_dist.median()), 'm, polygon-only ground', round(d.only_median_dist.median()), 'm; grown polygon beyond 2.5 km', round(np.average(d.grown_beyond2500, weights=d.grown_px), 3))
print('by passes (pixel-weighted never / overlap / before / after):')
for k, g in d.groupby(d.n_pass.clip(upper=3)):
    print('  ', k, [round(np.average(g[c], weights=g.only_px), 3) for c in ['only_never', 'only_overlap', 'only_before', 'only_after']])
