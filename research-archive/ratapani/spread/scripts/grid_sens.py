"""Audit item 4: grid-size sensitivity of the physics. Builds 40 m and 60 m copies of the model grid (block aggregates of the 20 m layers:
elevation and slope mean, aspect subsampled, land cover by majority, fuel and leaf-fall means, a road barrier where any 20 m road pixel
falls in the block, first-burn days per season), then runs the final physics (3.0 t/ha loose bed, roads, no wind, no scar snapping) from the
first pass of every scarred S-NPP fire with a grown outline at each resolution, with the outline block-reduced the same way (burned if
half the block burned). Scores: Sorensen at the outline's area, free-run area and Sorensen at 26 h and 48 h, later-pass hits (240 m).
  python3 grid_sens.py build                      -> data40/, data60/
  SPREAD_DATA=/tmp/claude-0/spread/data40 python3 grid_sens.py run k/n out.parquet
"""
import os, sys, numpy as np, pandas as pd, time, pickle, json
D20 = '/tmp/claude-0/spread/data'


def block(a, f, how):
    H, W = a.shape[-2] // f * f, a.shape[-1] // f * f; a = a[..., :H, :W]
    b = a.reshape(a.shape[:-2] + (H // f, f, W // f, f))
    if how == 'mean':
        return np.nanmean(b, axis=(-3, -1))
    if how == 'any':
        return b.any(axis=(-3, -1))
    if how == 'sub':
        return a[..., ::f, ::f]
    if how == 'mode':
        flat = b.transpose(0, 2, 1, 3).reshape(H // f, W // f, f * f)
        out = np.zeros((H // f, W // f), a.dtype)
        for v in np.unique(a):
            cnt = (flat == v).sum(-1); best = out.copy(); 
            if v == np.unique(a)[0]:
                bestc = np.zeros_like(cnt)
            m = cnt > bestc; out[m] = v; bestc[m] = cnt[m]
        return out
    if how == 'minburn':      # first burn day in the block; -999 when nothing burned
        bb = np.where(b > -999, b, 32767).min(axis=(-3, -1)); return np.where(bb == 32767, -999, bb).astype(a.dtype)


def build():
    G = np.load(f'{D20}/grid20.npz'); RF = np.load(f'{D20}/rfuel20_loose.npz'); LF = np.load(f'{D20}/leaffall20.npz')['lf']; RD = np.load(f'{D20}/barriers.npz')['road']
    for f in (2, 3):
        out = f'/tmp/claude-0/spread/data{20 * f}'; os.makedirs(out, exist_ok=True)
        g = dict(elev=block(G['elev'].astype(np.float32), f, 'mean'), slope=block(G['slope'].astype(np.float32), f, 'mean'), upslope_az=block(G['upslope_az'], f, 'sub'),
                 wc=block(G['wc'], f, 'mode'))
        tr = G['transform'].copy(); tr[0] = 20.0 * f; tr[4] = -20.0 * f; g['transform'] = tr; g['shape'] = np.array(g['wc'].shape)
        for k in G.keys():
            if k.startswith('burn_'):
                g[k] = block(G[k], f, 'minburn')
        np.savez_compressed(f'{out}/grid20.npz', **g)
        np.savez_compressed(f'{out}/rfuel20_loose.npz', **{k: block(RF[k].astype(np.float32), f, 'mean').astype(np.float32) for k in RF.keys()})
        np.savez_compressed(f'{out}/leaffall20.npz', lf=block(LF.astype(np.float32), f, 'mean').astype(np.float32))
        np.savez_compressed(f'{out}/barriers.npz', road=block(RD, f, 'any'))
        print(out, g['wc'].shape, 'burnable share', float(np.isin(g['wc'], [10, 20, 30]).mean()), 'road px', int(block(RD, f, 'any').sum()), flush=True)


def run(k_n, out):
    import sim, score
    from scipy import ndimage
    f = int(round(sim.RES / 20.0)); R_MAX = 2500.0; HIT = int(round(240 / sim.RES))
    CFG = dict(fuel='rfuel', rfuel_file='rfuel20_loose.npz', leaffall='interp', ros_mult=2, ign_snap=False, wind=False, hours=48, strict=1, barriers=True, pad_m=2600)
    store = pickle.load(open(f'{D20}/grown_scars.pkl', 'rb'))
    v = pd.read_parquet(f'{D20}/viirs_events.parquet'); v = v[v.t.dt.month <= 6]
    ok = pd.read_parquet(f'{D20}/rundir.parquet').event.values; v = v[v.event.isin(ok) & v.event.isin(list(store.keys()))]
    ids = sorted(v.event.unique()); k, n = map(int, k_n.split('/')); ids = ids[k::n]
    def truth(e, win):
        i0, i1, j0, j1 = win; st = store[e]; r, c = st['rows'] // f, st['cols'] // f
        cnt = np.zeros((i1 - i0, j1 - j0), np.int32); rr, cc = r - i0, c - j0
        okk = (rr >= 0) & (rr < cnt.shape[0]) & (cc >= 0) & (cc < cnt.shape[1]); np.add.at(cnt, (rr[okk], cc[okk]), 1)
        return cnt >= max(f * f // 2, 1)
    wx = {}; rows = []; tt = time.time()
    for q, e in enumerate(ids):
        ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        o = sim.run_event(ev, wx[s], CFG, hours=48, scar_fn=None)
        B, (i0, i1, j0, j1), t0 = o['burnable'], o['win'], o['t0']
        S = truth(e, (i0, i1, j0, j1))
        if S.sum() < max(25 // (f * f), 3):
            continue
        tfirst = (ev.t.min() - t0).total_seconds() / 60; tph = (o['T'] - tfirst) / 60.0; tph = np.where(np.isfinite(tph), tph, 96.0)
        first = ev[ev.overpass == ev.overpass.min()]
        yy, xx = np.mgrid[i0:i1, j0:j1]; px = sim.X0 + xx * sim.RES + sim.RES / 2; py = sim.Y0 - yy * sim.RES - sim.RES / 2
        d_near = np.full(px.shape, np.inf)
        for a, b in zip(first.x.values, first.y.values):
            d_near = np.minimum(d_near, np.hypot(px - a, py - b))
        mask = np.isin(sim.WC[i0:i1, j0:j1], [10, 20, 30]) & (d_near <= R_MAX)
        nS = int(S.sum()); Pp = score.topn(tph, mask, nS); Pc = score.topn(d_near, mask, nS)
        P26 = mask & (tph <= 26); P48 = mask & (tph <= 48)
        row = dict(event=int(e), season=s, res=sim.RES, scar_px=nS, scar_ha=nS * sim.RES ** 2 / 1e4, sor=score.soren(Pp, S), sor_circle=score.soren(Pc, S),
                   area26_ha=P26.sum() * sim.RES ** 2 / 1e4, sor26=score.soren(P26, S), area48_ha=P48.sum() * sim.RES ** 2 / 1e4, sor48=score.soren(P48, S),
                   n_burnable=int((B & mask).sum()))
        later = ev[(ev.t >= ev.t.min() + pd.Timedelta(hours=6)) & (ev.t <= ev.t.min() + pd.Timedelta(hours=72))]
        if len(later):
            r, c = sim.rc(later.x.values, later.y.values); r -= i0; c -= j0; h = h26 = hc = 0
            for a, b in zip(r, c):
                sl = (slice(max(a - HIT, 0), a + HIT + 1), slice(max(b - HIT, 0), b + HIT + 1))
                h += bool(Pp[sl].any()); h26 += bool(P26[sl].any()); hc += bool(Pc[sl].any())
            row.update(n_later=len(later), hit=h, hit26=h26, hit_circle=hc)
        rows.append(row)
        if q % 50 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out); print('done', len(rows))


if __name__ == '__main__':
    build() if sys.argv[1] == 'build' else run(sys.argv[2], sys.argv[3])
