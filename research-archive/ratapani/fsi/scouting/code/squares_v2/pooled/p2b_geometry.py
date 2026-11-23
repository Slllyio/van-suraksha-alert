"""Step 2b: signed view geometry of every look, and a view-angle-dependent bias model.
Why: the later of two passes 25-50 min apart is on an orbit ~6-12 deg further west, so it sees the same ground from
further east of its nadir. Any geolocation error that grows with view angle then looks like a systematic eastward 'move'.
1. Nadir local solar time (LST) per sensor x day/night x 1-deg latitude band = where the along-track pixel size is smallest.
   Signed across-track distance x = (LST_look - LST_nadir) * 15 deg * 111.32 km * cos(lat) (positive = east of nadir).
   View zenith from x with Earth curvature (orbit height 824 km).
2. Bias model, fitted on static sites: d_scan = (o_B - o_A) + h_s * (tan z_B - tan z_A),  same for d_track (signed tan z).
   h is an 'effective height' error (m); also fitted on fires jointly with a mean drift per hour.
Out: results/geometry_*.json, scratch nadir.csv, and pairs3.parquet (pairs2 + xA, xB, tanzA, tanzB)."""
import json, os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
rng = np.random.default_rng(6); CLIP = 2000.0
Re, H = 6371.0, 824.0
A = pd.read_parquet(f'{SC}/pts.parquet', columns=['sensor', 't', 'latitude', 'longitude', 'track_m', 'daynight'])
A = A[A.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])]
A['lst'] = (A.t.dt.hour + A.t.dt.minute / 60 + A.longitude / 15) % 24
A['lb'] = A.latitude.round().astype(int)
nad = []
for (s, dn, lb), g in A.groupby(['sensor', 'daynight', 'lb']):
    if len(g) < 2000: continue
    c0 = g.lst.median(); x = g.lst - c0
    k = (x.abs() < 0.6)
    if k.sum() < 500: continue
    # robust minimum: median track in 0.02 h bins, parabola through the bins near the minimum
    b = g[k].groupby((x[k] / 0.02).round()).track_m.median()
    bb = b[b <= b.min() + 40]
    co = np.polyfit(bb.index.values * 0.02, bb.values, 2)
    nad.append(dict(sensor=s, dn=dn, lat=lb, lst_nadir=c0 + (-co[1] / (2 * co[0]) if co[0] > 0 else bb.idxmin() * 0.02), n=len(g)))
Nd = pd.DataFrame(nad); Nd.to_csv(f'{SC}/nadir.csv', index=False); print(Nd.to_string())
def geom(sensor, dn, lat, lon, t):
    """signed across-track km (east of nadir positive) and signed tan(view zenith) for looks"""
    lst = (t.dt.hour + t.dt.minute / 60 + t.dt.second / 3600 + lon / 15) % 24
    x = np.full(len(lat), np.nan)
    for (s, d), g in Nd.groupby(['sensor', 'dn']):
        m = (sensor == s) & (dn == d)
        if m.any(): x[m] = (lst[m] - np.interp(lat[m], g.lat, g.lst_nadir)) * 15 * 111.32 * np.cos(np.radians(lat[m]))
    gam = x / Re; alpha = np.arctan2(Re * np.sin(np.abs(gam)), Re + H - Re * np.cos(gam)); z = alpha + np.abs(gam)
    return x, np.sign(x) * np.tan(z)
# check: track size against |x|
A = A.sample(300000, random_state=0)
x, tz = geom(A.sensor.values, A.daynight.values, A.latitude.values, A.longitude.values, A.t)
chk = pd.Series(A.track_m.values).groupby(pd.cut(np.abs(x), [0, 100, 200, 400, 600, 800, 1000, 1200, 1500, 2000])).median()
print('median track size by |x| km', chk.to_dict())
R = pd.read_parquet(f'{SC}/pairs2.parquet')
for L in 'AB':
    s = R['s' + L].values; dn = R.dn.values
    xx, tt = geom(s, dn, R['lat' + L].values, R['lon' + L].values, R['t' + L])
    R['x' + L], R['tz' + L] = xx, tt
R.loc[~R['sA'].isin(['S-NPP', 'NOAA-20', 'NOAA-21']), ['xA', 'tzA']] = np.nan
R.loc[~R['sB'].isin(['S-NPP', 'NOAA-20', 'NOAA-21']), ['xB', 'tzB']] = np.nan
R['dtz'] = R.tzB - R.tzA
R.to_parquet(f'{SC}/pairs3.parquet')
res = {}
sm = R.vv & R.small & np.isfinite(R.dtz)
res['across_track_km_small_pairs'] = {f'{t} {dn}': dict(xA_median=round(float(g.xA.median())), xB_median=round(float(g.xB.median())), dtz_mean=round(float(g.dtz.mean()), 2))
                                      for (t, dn), g in R[sm].groupby(['typ', 'dn'])}
def fitbias(g, with_v=False):
    out = {}
    for c in ['d_scan', 'd_track']:
        X = [(g.sB == 'NOAA-20') * 1.0 - (g.sA == 'NOAA-20'), (g.sB == 'NOAA-21') * 1.0 - (g.sA == 'NOAA-21'), g.dtz]
        if with_v: X.append(g.gap_min / 60)
        X = np.column_stack(X); y = g[c].clip(-CLIP, CLIP).values
        co = np.linalg.lstsq(X, y, rcond=None)[0]
        cl = pd.factorize(g.site if (g.typ == 2).all() else g.cl)[0]; idx = [np.where(cl == k)[0] for k in range(cl.max() + 1)]; bs = []
        for _ in range(150):
            k = np.concatenate([idx[j] for j in rng.integers(0, len(idx), len(idx))]); bs.append(np.linalg.lstsq(X[k], y[k], rcond=None)[0])
        bs = np.array(bs); names = ['o_NOAA-20', 'o_NOAA-21', 'h (m per unit tan zenith)'] + (['drift m/h'] if with_v else [])
        out[c] = {nm: f'{co[i]:.1f} ({np.quantile(bs[:, i], .025):.1f} to {np.quantile(bs[:, i], .975):.1f})' for i, nm in enumerate(names)}
        out[c]['_coef'] = co.tolist()
    return out
h = np.radians(np.where(R.dn == 'D', 347.0, 193.0))
R['d_scan'] = R.dE * np.cos(h) - R.dN * np.sin(h); R['d_track'] = R.dE * np.sin(h) + R.dN * np.cos(h)
R['cl'] = R.season.astype(str) + '_' + (R.lonA * 20).round().astype(int).astype(str) + '_' + (R.latA * 20).round().astype(int).astype(str)
for dn in 'DN':
    res[f'static {dn}'] = fitbias(R[sm & (R.typ == 2) & (R.dn == dn)])
    res[f'fires {dn} (joint with drift)'] = fitbias(R[sm & (R.typ == 0) & (R.dn == dn)], with_v=True)
    res[f'fires {dn} (no drift term)'] = fitbias(R[sm & (R.typ == 0) & (R.dn == dn)])
json.dump(res, open(f'{OUT}/geometry_bias.json', 'w'), indent=1); print(json.dumps({k: ({c: {q: w for q, w in v.items() if q != '_coef'} for c, v in d.items()} if isinstance(d, dict) and 'd_scan' in d else d) for k, d in res.items()}, indent=1))
