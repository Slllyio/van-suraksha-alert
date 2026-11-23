"""Observed fire advance between consecutive VIIRS overpasses (same event), against ERA5-Land wind
and terrain. Finest time scale we have (~11-13 h). Writes a table and prints the wind/slope test."""
import numpy as np, pandas as pd, sys
sys.path.insert(0, '/tmp/claude-0/spread/scripts')
import sim
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.t.dt.month <= 6]
rows = []; wx = {}
for e, ev in v.groupby('event'):
    if ev.overpass.nunique() < 2:
        continue
    s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    W, P = wx[s]; pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]; w = W[pid]
    passes = sorted(ev.overpass.unique())
    for a, b in zip(passes[:-1], passes[1:]):
        A, B = ev[ev.overpass == a], ev[ev.overpass == b]
        dt_h = (B.t.min() - A.t.max()).total_seconds() / 3600
        if dt_h <= 0 or dt_h > 36:
            continue
        ww = w.loc[A.t.max().floor('h'): B.t.min().floor('h')]
        if len(ww) == 0:
            continue
        u = (ww.ws * np.sin(np.radians(ww.waz))).mean(); vv = (ww.ws * np.cos(np.radians(ww.waz))).mean()
        waz = np.degrees(np.arctan2(u, vv)) % 360; wsp = np.hypot(u, vv)
        ca = (A.x.mean(), A.y.mean())
        for _, d in B.iterrows():
            # nearest earlier detection, and displacement from it
            dd = np.hypot(A.x.values - d.x, A.y.values - d.y); k = dd.argmin()
            dx, dy = d.x - A.x.values[k], d.y - A.y.values[k]
            r, c = sim.rc(np.array([d.x]), np.array([d.y]))
            up = float(sim.UPAZ[r[0], c[0]]); sl = float(sim.SLOPE[r[0], c[0]])
            rows.append(dict(event=e, season=s, dt_h=dt_h, night=B.t.min().hour >= 15, n_old=len(A), n_new=len(B),
                             d=dd[k], bearing=np.degrees(np.arctan2(dx, dy)) % 360, waz=waz, wsp=wsp,
                             rh_min=ww.rh.min(), m1_min=ww.m1.min(), upslope_az=up, slope=sl,
                             dcent=np.hypot(d.x - ca[0], d.y - ca[1])))
t = pd.DataFrame(rows); t.to_parquet(f'{sim.DATA}/passpairs.parquet')
print(len(t), 'new detections in', t.event.nunique(), 'events;', 'pairs', t.groupby(['event', 'dt_h']).ngroups)
print('distance to nearest earlier detection (m): quantiles', np.percentile(t.d, [25, 50, 75, 90]).round(0))
print('advance per hour (m/h) for d>400 m:', np.percentile(t[t.d > 400].d / t[t.d > 400].dt_h, [25, 50, 75]).round(0))
m = t[t.d > 500].copy()
m['rel'] = ((m.bearing - m.waz + 180) % 360) - 180
m['rel_s'] = ((m.bearing - m.upslope_az + 180) % 360) - 180
def sector(x): return pd.cut(np.abs(x), [0, 45, 135, 180], labels=['downwind', 'cross', 'upwind'], include_lowest=True)
print('\nMoves > 500 m (n=%d): share by direction relative to the mean wind over the interval' % len(m))
print((m.groupby(sector(m.rel), observed=True).size() / len(m)).round(3).to_dict(), ' (uniform would be 0.25/0.5/0.25)')
mw = m[m.wsp >= 2]
print('  same, wind >= 2 m/s (n=%d):' % len(mw), (mw.groupby(sector(mw.rel), observed=True).size() / max(len(mw), 1)).round(3).to_dict())
ms = m[m.slope >= 5]
print('  relative to upslope, slope >= 5 deg (n=%d):' % len(ms), (ms.groupby(sector(ms.rel_s), observed=True).size() / max(len(ms), 1)).round(3).to_dict())
print('  mean cos(bearing - wind):', np.cos(np.radians(m.rel)).mean().round(3), ' corr(d, wind speed):', np.corrcoef(m.d, m.wsp)[0, 1].round(3))
print('  day vs night new detections:', t.night.value_counts().to_dict())
