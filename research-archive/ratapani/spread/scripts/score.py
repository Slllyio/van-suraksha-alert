"""Score spread runs. Usage: python score.py <config.json> <out.parquet> [max_events] [seasons]"""
import numpy as np, pandas as pd, sys, json, time
from scipy import ndimage
import sim

def scar_footprint(o, ev):
    i0, i1, j0, j1 = o['win']; s = o['season']
    be = sim.G[f'burn_end_{s}'][i0:i1, j0:j1]; bs = sim.G[f'burn_start_{s}'][i0:i1, j0:j1]
    d0, d1 = ev.t.min().dayofyear, ev.t.max().dayofyear
    m = (be > -999) & (be >= d0) & (bs <= d1)
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return m, 0
    r, c = sim.rc(ev.x.values, ev.y.values); r -= i0; c -= j0
    near = np.zeros(m.shape, bool); near[np.clip(r, 0, m.shape[0] - 1), np.clip(c, 0, m.shape[1] - 1)] = True
    near = ndimage.binary_dilation(near, iterations=20)  # 400 m
    keep = np.unique(lab[near & m]); keep = keep[keep > 0]
    S = np.isin(lab, keep)
    # window length of the scar dating (days) for reference
    return S, int(np.median(be[S] - bs[S])) if S.any() else 0

def topn(score, valid, n):
    v = np.where(valid, score, np.inf).ravel()
    n = min(n, int(np.isfinite(v).sum()))
    sel = np.zeros(v.size, bool)
    if n > 0:
        sel[np.argpartition(v, n - 1)[:n]] = True
    return sel.reshape(score.shape)

def soren(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)

def main():
    cfg = json.load(open(sys.argv[1])) if sys.argv[1].endswith('.json') else json.loads(sys.argv[1])
    if 'fuelmap' in cfg and isinstance(cfg['fuelmap'], str):
        cfg['fuelmap'] = getattr(sim, cfg['fuelmap'])
    if 'fuelmap' in cfg:
        cfg['fuelmap'] = {int(k): v for k, v in cfg['fuelmap'].items()}
    maxev = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 9
    seasons = [int(s) for s in sys.argv[4].split(',')] if len(sys.argv) > 4 else list(range(2017, 2025))
    v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet')
    v = v[v.season.isin(seasons) & (v.t.dt.month >= 1)]
    rows, wx_cache = [], {}
    evs = v.groupby('event')
    ids = sorted(evs.groups)[:maxev]
    if len(sys.argv) > 5:
        k_, n_ = map(int, sys.argv[5].split('/')); ids = ids[k_::n_]
    tt = time.time()
    for k, e in enumerate(ids):
        ev = evs.get_group(e).sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx_cache:
            wx_cache.clear(); wx_cache[s] = sim.load_weather(s)
        o = sim.run_event(ev, wx_cache[s], cfg, hours=cfg.get('hours', 72), scar_fn=scar_footprint)
        T, dist, B = o['T'], o['dist'], o['burnable']
        S, scar_win = o['S'], o['scar_win']
        tmin = (T - (ev.t.min() - o['t0']).total_seconds() / 60)  # minutes since first detection
        row = dict(event=e, season=s, n_det=len(ev), n_pass=ev.overpass.nunique(), t0=ev.t.min(),
                   scar_px=int(S.sum()), scar_win=scar_win, ign_px=int(o['ig'].sum()),
                   area24=int((tmin <= 1440).sum()), area48=int((tmin <= 2880).sum()), area72=int(np.isfinite(T).sum()))
        tend = (ev.t.max() - ev.t.min()).total_seconds() / 60 + 12 * 60   # last detection + 12 h
        row['area_end'] = int((tmin <= tend).sum())
        if S.sum() >= 25 and o['ig'].sum() > 0:   # >= 1 ha of scar
            row['sor_end'] = soren(tmin <= tend, S)
            n = int(S.sum())
            Pm = topn(T, np.isfinite(T), n); Pi = topn(dist, B, n)
            row.update(sor_model=soren(Pm, S), sor_iso=soren(Pi, S), reach_frac=np.isfinite(T)[S].mean(),
                       sor24=soren(tmin <= 1440, S), sor48=soren(tmin <= 2880, S))
        # timing vs later overpasses
        later = ev[ev.t >= ev.t.min() + pd.Timedelta(hours=6)]
        i0, i1, j0, j1 = o['win']
        if len(later):
            hm = hi = 0; nl = 0
            for op, g in later.groupby('overpass'):
                tk = (g.t.min() - o['t0']).total_seconds() / 60
                if tk > cfg.get('hours', 72) * 60:
                    continue
                Ak = (T <= tk)
                rk = np.sort(dist[B])[min(max(Ak.sum() - 1, 0), B.sum() - 1)] if B.any() else 0
                r, c = sim.rc(g.x.values, g.y.values); r -= i0; c -= j0
                for a, b in zip(r, c):
                    sl = (slice(max(a - 12, 0), a + 13), slice(max(b - 12, 0), b + 13))   # +-250 m
                    nl += 1; hm += bool(Ak[sl].any()); hi += bool((B[sl] & (dist[sl] <= rk)).any())
            row.update(n_later=nl, hit_model=hm, hit_iso=hi)
        rows.append(row)
        if k % 50 == 0:
            print(k, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(sys.argv[2])

if __name__ == '__main__':
    main()
