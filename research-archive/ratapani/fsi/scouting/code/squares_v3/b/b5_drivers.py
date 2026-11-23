"""B step 5: which fires are fast? Drivers of the fire-specific factor f (b1), with held-out R2 that is corrected for noise.

Target: a fire's f_hat (its own estimate, noise variance DE x s^2 from b1). Model: weighted least squares of (f_hat - 1) on
standardised drivers, weights 1 / (tau^2 + noise), fitted on the other seasons and scored on the held-out season.
Noise-corrected held-out R2 (share of the TRUE between-fire variance explained):
    R2 = (SSE_null - SSE_model) / (SSE_null - sum w x noise)      (SSE_null = sum w (f_hat - 1)^2)
so a driver that only fits noise scores ~0. 95% ranges by bootstrap over fires.
Tier 1, all MP (92k fires; fire = linked pairs): slope, elevation, latitude, longitude, season, fire extent (number of
  pairs, largest look), share of night pairs, distance from earlier detections, plus the class-model inputs again
  (forest type, month, FRP, pixels, age) to check the class model leaves nothing behind.
Tier 2, Ratapani fires (big-fires ids): fuel load (season peak map), grass share (cover class 'open grass / low cover'),
  canopy cover, teak probability, burns in earlier seasons (burn frequency), slope (20 m grid), and dryness and weather on
  the start day (NASA POWER daily: RH, temperature, wind, days since >= 2 mm rain; to 2024).
Out: results/b5_drivers.json/csv, fig_b5_drivers.png"""
import sys, os, json, pickle
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
from b1_hier import load, fit_class, class_mean, nuisance, per_fire, design_effect
from b_post import models, de_of
rng = np.random.default_rng(41)

def fire_targets(O, key):
    """per fire: f_hat, noise s2e, season-held-out class model (each season's fires use the model fitted without it)"""
    M = models(); out = []
    for s, g in O.groupby('season'):
        cm = M[s]['cm']; mu = class_mean(g, cm); g = g.assign(yc=g.y - nuisance(g, cm))
        fo = per_fire(g, mu, key=key, col='yc'); fo['s2e'] = fo.s2 * de_of(fo.n.values, M[s]['de']); fo['tau2'] = M[s]['tau2']; fo['season'] = s
        out.append(fo)
    return pd.concat(out)

def score(df, cols, n_boot=300):
    """season-held-out WLS; returns noise-corrected R2 and its bootstrap range"""
    df = df.dropna(subset=cols).copy(); y = df.f_hat.values - 1; w = 1 / (df.tau2.values + df.s2e.values)
    X = df[cols].values.astype(float); X = (X - np.average(X, 0, w)) / np.sqrt(np.average((X - np.average(X, 0, w)) ** 2, 0, w) + 1e-12)
    pred = np.zeros(len(df))
    for s in df.season.unique():
        tr = (df.season != s).values; Z = np.c_[np.ones(tr.sum()), X[tr]]; sw = np.sqrt(w[tr])
        b = np.linalg.lstsq(Z * sw[:, None], y[tr] * sw, rcond=None)[0]; pred[~tr] = np.c_[np.ones((~tr).sum()), X[~tr]] @ b
    Z = np.c_[np.ones(len(df)), X]; sw = np.sqrt(w); bfull = np.linalg.lstsq(Z * sw[:, None], y * sw, rcond=None)[0]
    a = w * y ** 2; c = w * (y - pred) ** 2; nz = w * df.s2e.values
    def r2(k): return (a[k].sum() - c[k].sum()) / (a[k].sum() - nz[k].sum())
    k0 = np.arange(len(df)); bs = [r2(rng.integers(0, len(df), len(df))) for _ in range(n_boot)]
    return dict(fires=len(df), heldout_r2_true=round(float(r2(k0)), 3), ci=[round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)],
                coef_per_sd={c_: round(float(v), 3) for c_, v in zip(cols, bfull[1:])}, mean_reliability=round(float(np.mean(df.tau2 / (df.tau2 + df.s2e))), 4))

if __name__ == '__main__':
    O, _ = load(); res = {}
    # ---------------- tier 1: all MP
    T = fire_targets(O, 'fire_mp')
    g = O.groupby('fire_mp')
    X = pd.DataFrame(dict(slope=g.slope.mean(), elev=g.elev.mean(), lat=g.latA.mean(), lon=g.lonA.mean(), n_pairs=np.log(g.size()),
                          max_pix=np.log(g.npix.max()), night_share=g.dn0.apply(lambda v: (v == 'N').mean()), u_len=g.u_len.mean(),
                          month=g.month.mean(), frp=np.log1p(g.frp2.mean()), age=g.age_h.mean(),
                          forest=g.ft.apply(lambda v: (~v.isin(['agriculture', 'other non-forest'])).mean()),
                          farm=g.ft.apply(lambda v: (v == 'agriculture').mean()), grass=g.ft.apply(lambda v: (v == 'scrub/grass').mean())))
    D1 = T.join(X); D1 = D1[np.isfinite(D1.f_hat) & (D1.s2e < 1e4)]
    t1 = {}
    groups = {'terrain (slope, elevation)': ['slope', 'elev'], 'place (lat, lon)': ['lat', 'lon'], 'fire extent (pairs, largest look)': ['n_pairs', 'max_pix'],
              'timing (night share, month)': ['night_share', 'month'], 'class inputs again (forest/farm/grass share, FRP, age)': ['forest', 'farm', 'grass', 'frp', 'age'],
              'distance from earlier detections': ['u_len']}
    for nm, cols in groups.items(): t1[nm] = score(D1, cols)
    t1['all together'] = score(D1, sum(groups.values(), []))
    res['tier1_all_MP'] = t1; print(json.dumps(t1, indent=1))
    # ---------------- tier 2: Ratapani
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    Pr = O[O.fire_rt >= 0]; T2 = fire_targets(Pr, 'fire_rt')
    S = pickle.load(open(f'{R17}/scars.pkl', 'rb')); FR = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv').set_index('fire')
    FM = f'{ROOT}/fuel-map/ratapani'
    G20 = np.load(f'{ROOT}/ratapani/spread/data_shared/grid20.npz'); E = G20['elev'].astype(float); GT = G20['transform']
    gy, gx = np.gradient(E, 20.0); SLOPE = np.degrees(np.arctan(np.hypot(gx, gy)))
    W = pd.read_parquet(f'{ROOT}/ratapani/weather_power_daily.parquet').set_index('date').sort_index()
    W['rain'] = W.precip_mm >= 2; last = None; dsr = []
    for d_, r in W.iterrows():
        last = d_ if r.rain else last; dsr.append((d_ - last).days if last is not None else 60)
    W['days_since_rain'] = np.minimum(dsr, 120)
    rows = []
    rs = {k: rasterio.open(f'{FM}/{k}.tif') for k in ['cover_phenology_10m', 'canopy_cover_10m', 'teak_probability_10m', 'burn_frequency_2017_2026_10m', 'fuel_continuous_peak_10m']}
    for f in T2.index:
        if f not in S: continue
        poly = S[f]; b = poly.bounds; xs = np.arange(b[0] + 20, b[2], 40); ys = np.arange(b[1] + 20, b[3], 40)
        P = np.array([(x, y) for x in xs for y in ys]);
        if not len(P): P = np.array([[poly.centroid.x, poly.centroid.y]])
        from shapely import contains_xy
        P = P[contains_xy(poly, P[:, 0], P[:, 1])] if len(P) > 1 else P
        if not len(P): P = np.array([[poly.centroid.x, poly.centroid.y]])
        if len(P) > 1500: P = P[rng.choice(len(P), 1500, replace=False)]
        season = int(FR.season[f]); fs = f'{FM}/fuel_season_{season}_peak_10m.tif'
        def samp(r, nod=None):
            v = np.array([q[0] for q in r.sample(P)], float)
            if nod is not None: v[v == nod] = np.nan
            return v
        cov = samp(rs['cover_phenology_10m'], 0)
        fuel = samp(rasterio.open(fs), 65535) if os.path.exists(fs) else samp(rs['fuel_continuous_peak_10m'], 65535)
        rr = ((GT[5] - P[:, 1]) / 20).astype(int); cc = ((P[:, 0] - GT[2]) / 20).astype(int)
        ok = (rr >= 0) & (rr < SLOPE.shape[0]) & (cc >= 0) & (cc < SLOPE.shape[1])
        d0 = pd.Timestamp(FR.date0[f])
        w = W.loc[d0 - pd.Timedelta(days=0): d0].tail(1)
        rows.append(dict(fire=f, fuel=np.nanmean(fuel) * .1, grass=np.nanmean(cov == 4) if np.isfinite(cov).any() else np.nan,
                         canopy=np.nanmean(np.where(samp(rs['canopy_cover_10m'], 65535) > 1000, np.nan, samp(rs['canopy_cover_10m'], 65535))) * .1,
                         teak=np.nanmean(samp(rs['teak_probability_10m'], 255)), burn_freq=np.nanmean(samp(rs['burn_frequency_2017_2026_10m'], 65535)),
                         slope20=np.nanmean(SLOPE[rr[ok], cc[ok]]) if ok.any() else np.nan, area_log=np.log(FR.area_ha[f]),
                         rh=float(w.rh_pct.iloc[0]) if len(w) else np.nan, temp=float(w.temp_c.iloc[0]) if len(w) else np.nan,
                         wind=float(w.wind_kmh.iloc[0]) if len(w) else np.nan, days_since_rain=float(w.days_since_rain.iloc[0]) if len(w) else np.nan))
    X2 = pd.DataFrame(rows).set_index('fire'); D2 = T2.join(X2, how='inner'); D2 = D2[np.isfinite(D2.f_hat) & (D2.s2e < 1e4)]
    D2.to_csv(f'{OUT}/b5_ratapani_fires.csv')
    t2 = {}
    g2 = {'fuel load': ['fuel'], 'grass share': ['grass'], 'canopy cover': ['canopy'], 'teak probability': ['teak'], 'earlier burns': ['burn_freq'],
          'slope (20 m)': ['slope20'], 'dryness (days since rain, RH)': ['days_since_rain', 'rh'], 'weather (temperature, wind)': ['temp', 'wind'],
          'final scar size': ['area_log']}
    for nm, cols in g2.items(): t2[nm] = score(D2, cols)
    t2['fuel + grass + terrain'] = score(D2, ['fuel', 'grass', 'canopy', 'teak', 'burn_freq', 'slope20'])
    t2['all together (to 2024, weather)'] = score(D2, sum(g2.values(), []))
    res['tier2_ratapani'] = t2
    # ranked list of the clearly fastest Ratapani fires (posterior lower 95% bound of f above 1)
    B = D2.tau2 / (D2.tau2 + D2.s2e); D2['f_post'] = 1 + B * (D2.f_hat - 1); D2['sd'] = np.sqrt(B * D2.s2e)
    fast = D2[(D2.f_post - 1.96 * D2.sd) > 1].sort_values('f_post', ascending=False)
    res['ratapani_fires_clearly_fast'] = fast[['f_post', 'sd', 'n', 'fuel', 'grass', 'slope20']].round(3).head(15).reset_index().to_dict('records')
    res['ratapani_fires_clearly_slow'] = int(((D2.f_post + 1.96 * D2.sd) < 1).sum())
    json.dump(res, open(f'{OUT}/b5_drivers.json', 'w'), indent=1, default=float); print(json.dumps(t2, indent=1, default=float))
    rows = [dict(tier='all MP', driver=k, **{q: v for q, v in d.items() if q != 'coef_per_sd'}) for k, d in t1.items()] + \
           [dict(tier='Ratapani', driver=k, **{q: v for q, v in d.items() if q != 'coef_per_sd'}) for k, d in t2.items()]
    pd.DataFrame(rows).to_csv(f'{OUT}/b5_drivers.csv', index=False)
