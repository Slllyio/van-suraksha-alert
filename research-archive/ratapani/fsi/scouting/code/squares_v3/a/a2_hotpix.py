"""A2: matched truth tests with 30 m Sentinel-2 / Landsat hot pixels (Ratapani, ~10:45 IST).
1. Lag regression. For each hot-pixel scene H (>= 3 hot pixels) and EVERY coarse look L of the same fire within
   -27..+27 h (each VIIRS pass, Terra, Aqua separately; nothing merged): p = (centre(L) - centre(H)) . u,
   u = unit(H - E), E = centre of VIIRS detections 2-48 h before min(tL, tH) (never contains L).
   Model: p = o[kind, day/night] + beta * (pixel side of L - 470 m) + vbar * dC(tH -> tL)
     o    = where a coarse look's centre sits relative to the 30 m flaming front at the same moment (edge offset)
     dC   = clock-hours between tH and tL, from the pooled forest diurnal curve (multiplier, mean 1)
     vbar = daily-mean outward speed of the coarse-look centre, in m/h.
   Fire bootstrap (1000).  Also the old two-number test, its power, and a 'bracket' table (scenes with a VIIRS look
   before AND after within 13 h).
2. 30 m front advance between hot-pixel scenes of the same fire on different dates (1-6 days): median distance of the
   later scene's hot pixels to the nearest earlier hot pixel, and centre shift along (H1 - E); per hour of gap.
3. Same-day Sentinel-2 + Landsat scenes (minutes apart): agreement of the two 30 m centres (same-moment noise floor).
Out: results/a2_*.csv/json, fig_a2_lag.png"""
import json, os
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
rng = np.random.default_rng(22)
D = pd.read_csv('/mnt/project-files/research/big-fires/results/detections.csv', parse_dates=['t'])
D['kind'] = D.sensor.map({'Sentinel-2': 'hot', 'Landsat': 'hot', 'S-NPP': 'viirs', 'NOAA-20': 'viirs', 'NOAA-21': 'viirs', 'Terra MODIS': 'terra', 'Aqua MODIS': 'aqua'})
D['pix'] = np.sqrt(D.pix_w_m * D.pix_h_m)
dj = json.load(open('/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/pooled/results/diurnal_fit_noratapani.json'))['forest']
hh = np.array(sorted(float(k) for k in dj['curve'])); rr = np.array([dj['curve'][f'{h:.2f}'] for h in hh]) / dj['daily_mean_m_h']
def clock(t):  # cumulative clock-hours since 2000-01-01 IST, t in pandas Timestamp(s) UTC
    t = pd.to_datetime(t); h = (t - pd.Timestamp('2000-01-01')).total_seconds() / 3600 + 5.5
    day, frac = np.floor(h / 24), h % 24
    cum = np.r_[0, np.cumsum(rr) * 0.25]  # integral on the 15-min grid
    return day * 24 + np.interp(frac, np.r_[hh, 24], cum)

rows = []
for fire, g in D.groupby('fire'):
    hp = g[g.kind == 'hot']
    if not len(hp): continue
    V = g[g.kind == 'viirs']
    for pid, h in hp.groupby('pass_id'):
        if len(h) < 3: continue
        tH = h.t.min(); Hx, Hy = h.x.mean(), h.y.mean()
        C = g[(g.kind != 'hot') & (g.t >= tH - pd.Timedelta(hours=27)) & (g.t <= tH + pd.Timedelta(hours=27))]
        for qid, q in C.groupby('pass_id'):
            tL = q.t.min(); t0 = min(tL, tH)
            e = V[(V.t >= t0 - pd.Timedelta(hours=48)) & (V.t <= t0 - pd.Timedelta(hours=2))]
            if not len(e): continue
            ux, uy = Hx - e.x.mean(), Hy - e.y.mean(); L = np.hypot(ux, uy)
            if L < 100: continue
            ux, uy = ux / L, uy / L
            rows.append(dict(fire=fire, scene=pid, season=tH.year, kind=q.kind.iloc[0], sensor=q.sensor.iloc[0], dn=q.daynight.iloc[0],
                             dt_h=(tL - tH).total_seconds() / 3600, dC=clock(tL) - clock(tH), n=len(q), nH=len(h), pix=q.pix.mean(),
                             frp=q.frp.sum(), u_len=L, p=(q.x.mean() - Hx) * ux + (q.y.mean() - Hy) * uy,
                             perp=-(q.x.mean() - Hx) * uy + (q.y.mean() - Hy) * ux))
P = pd.DataFrame(rows); P['p'] = P.p.clip(-2000, 2000); P.to_csv(f'{OUT}/a2_hotpix_lags.csv', index=False)
print(len(P), P.groupby(['kind', 'dn']).size().to_dict())

def boot_fit(d, cols, y='p', nb=1000):
    X = np.column_stack([d[c].values for c in cols]); Y = d[y].values
    co = np.linalg.lstsq(X, Y, rcond=None)[0]
    fr = pd.factorize(d.fire)[0]; idx = [np.where(fr == k)[0] for k in range(fr.max() + 1)]; bs = []
    for _ in range(nb):
        k = np.concatenate([idx[j] for j in rng.integers(0, len(idx), len(idx))]); bs.append(np.linalg.lstsq(X[k], Y[k], rcond=None)[0])
    bs = np.array(bs)
    return {c: dict(coef=round(float(co[i]), 1), lo=round(float(np.quantile(bs[:, i], .025)), 1), hi=round(float(np.quantile(bs[:, i], .975)), 1)) for i, c in enumerate(cols)}

res = {}
d = P[P.kind.isin(['viirs', 'terra', 'aqua'])].copy()
for k in ['viirs', 'terra', 'aqua']:
    for dn in 'DN': d[f'o_{k}_{dn}'] = ((d.kind == k) & (d.dn == dn)) * 1.0
d['pixc'] = d.pix - 470
ocols = [c for c in d.columns if c.startswith('o_') and d[c].sum() >= 10]
res['n_looks'] = {c: int(d[c].sum()) for c in ocols}; res['n_fires'] = int(d.fire.nunique()); res['n_scenes'] = int(d.groupby(['fire', 'scene']).ngroups)
res['model_clock'] = boot_fit(d, ocols + ['pixc', 'dC'])
res['model_clock_viirs_only'] = boot_fit(d[d.kind == 'viirs'], ['o_viirs_D', 'o_viirs_N', 'pixc', 'dC'])
# separate day and night speeds (piecewise clock: day = 06-18 IST share of dt, night the rest), VIIRS only
def split_hours(r):
    t0 = pd.Timestamp('2000-01-01'); a = min(r.dt_h, 0); b = max(r.dt_h, 0)
    grid = np.arange(a, b, 0.05) + 0.025
    return pd.Series(dict(dday=np.sign(r.dt_h) * np.sum(((r.ist0 + grid) % 24 >= 6) & ((r.ist0 + grid) % 24 < 18)) * 0.05,
                          dnight=np.sign(r.dt_h) * np.sum(~(((r.ist0 + grid) % 24 >= 6) & ((r.ist0 + grid) % 24 < 18))) * 0.05))
d['ist0'] = 10.75
d[['dday', 'dnight']] = d.apply(split_hours, axis=1)
res['model_day_night_viirs_only'] = boot_fit(d[d.kind == 'viirs'], ['o_viirs_D', 'o_viirs_N', 'pixc', 'dday', 'dnight'])
# held-out by season half: fit o and beta on one half, speed from the other half's looks using those offsets
ho = {}
for half in (0, 1):
    tr = d[(d.season % 2 == half) & (d.kind == 'viirs')]; te = d[(d.season % 2 != half) & (d.kind == 'viirs')].copy()
    c = boot_fit(tr, ['o_viirs_D', 'o_viirs_N', 'pixc', 'dC'], nb=1)
    te['q'] = te.p - c['o_viirs_D']['coef'] * te.o_viirs_D - c['o_viirs_N']['coef'] * te.o_viirs_N - c['pixc']['coef'] * te.pixc
    ho[f'test_{"odd" if half == 0 else "even"}'] = boot_fit(te, ['dC'], y='q')
res['held_out_speed'] = ho
# lag-bin means
bins = [-27, -18, -13, -6, -0.6, 0.6, 1, 4.5, 10, 18, 27]
d['lagbin'] = pd.cut(d.dt_h, bins)
lb = []
for (k, b), g in d.groupby(['kind', 'lagbin'], observed=True):
    if len(g) < 8: continue
    fr = pd.factorize(g.fire)[0]; nf = fr.max() + 1; s = np.bincount(fr, g.p.values, nf); c = np.bincount(fr, minlength=nf)
    bs = [s[i].sum() / c[i].sum() for i in (rng.integers(0, nf, nf) for _ in range(1000))]
    lb.append(dict(kind=k, lag=str(b), looks=len(g), fires=nf, mean_dt_h=round(g.dt_h.mean(), 2), mean_dC=round(g.dC.mean(), 2), dn=g.dn.mode()[0],
                   p_m=round(g.p.mean(), 1), lo=round(float(np.quantile(bs, .025)), 1), hi=round(float(np.quantile(bs, .975)), 1), pix=round(g.pix.mean())))
LB = pd.DataFrame(lb); LB.to_csv(f'{OUT}/a2_lag_bins.csv', index=False); print(LB.to_string())
# the old two-number test and its power
old = d[(d.kind == 'viirs') & d.dt_h.between(1, 4.5)]
se = np.std([old.p.values[np.isin(pd.factorize(old.fire)[0], rng.integers(0, old.fire.nunique(), old.fire.nunique()))].mean() for _ in range(500)])
res['old_test_power'] = dict(looks=len(old), fires=int(old.fire.nunique()), se_m=round(float(se), 1), se_m_h=round(float(se / old.dt_h.mean()), 1),
                            power_to_tell_5_from_30_m_h=round(float(1 - __import__('scipy.stats').stats.norm.cdf(1.96 - 25 / (se / old.dt_h.mean()))), 2),
                            note='the old test compares a coarse CENTRE with the 30 m FRONT, so the edge offset o adds to p; it cannot give a speed without o')
# bracket table: scenes with a VIIRS look before (night, 6-13 h) and after (day, 1-4.5 h)
br = []
for (f, s), g in d[d.kind == 'viirs'].groupby(['fire', 'scene']):
    b = g[g.dt_h.between(-13, -6)]; a = g[g.dt_h.between(1, 4.5)]
    if len(b) and len(a): br.append(dict(fire=f, scene=s, p_before=b.p.mean(), dt_before=b.dt_h.mean(), dC_before=b.dC.mean(), p_after=a.p.mean(), dt_after=a.dt_h.mean(), dC_after=a.dC.mean()))
B = pd.DataFrame(br)
if len(B):
    B['viirs_speed_through_bracket'] = (B.p_after - B.p_before) / (B.dt_after - B.dt_before)
    B['frac_clock_before_H'] = -B.dC_before / (B.dC_after - B.dC_before)
    B['frac_pos_H'] = -B.p_before / (B.p_after - B.p_before)
    fr = pd.factorize(B.fire)[0]; nf = fr.max() + 1
    def bmean(v):
        s = np.bincount(fr, v, nf); c = np.bincount(fr, minlength=nf); bs = [s[i].sum() / c[i].sum() for i in (rng.integers(0, nf, nf) for _ in range(1000))]
        return dict(mean=round(float(v.mean()), 1), lo=round(float(np.quantile(bs, .025)), 1), hi=round(float(np.quantile(bs, .975)), 1))
    res['bracket'] = dict(scenes=len(B), fires=int(nf), p_before=bmean(B.p_before.values), p_after=bmean(B.p_after.values),
                          mean_viirs_shift_m=bmean((B.p_after - B.p_before).values), mean_gap_h=round(float((B.dt_after - B.dt_before).mean()), 2),
                          viirs_speed_m_h=bmean(B.viirs_speed_through_bracket.clip(-300, 300).values),
                          clock_fraction_elapsed_at_H=round(float(B.frac_clock_before_H.mean()), 2),
                          median_position_fraction_of_H=round(float(B.frac_pos_H.clip(-3, 4).median()), 2))
    B.to_csv(f'{OUT}/a2_bracket.csv', index=False)
# ---- 2. 30 m front advance between scenes of the same fire on different dates
H = D[D.kind == 'hot']; V = D[D.kind == 'viirs']; adv = []
for fire, g in H.groupby('fire'):
    sc = [(q.t.min(), q) for _, q in g.groupby('pass_id') if len(q) >= 3]
    sc.sort(key=lambda z: z[0])
    for (t1, a), (t2, b) in zip(sc[:-1], sc[1:]):
        gap = (t2 - t1).total_seconds() / 3600
        if gap < 12 or gap > 6 * 24 + 1: continue
        dd, _ = cKDTree(np.c_[a.x, a.y]).query(np.c_[b.x, b.y])
        e = V[(V.fire == fire) & (V.t >= t1 - pd.Timedelta(hours=48)) & (V.t <= t1 - pd.Timedelta(hours=2))]
        ux = uy = np.nan
        if len(e):
            ux, uy = a.x.mean() - e.x.mean(), a.y.mean() - e.y.mean(); L = np.hypot(ux, uy); ux, uy = ux / L, uy / L
        adv.append(dict(fire=fire, season=t1.year, gap_h=gap, n1=len(a), n2=len(b), adv_med_m=float(np.median(dd)), adv_p75_m=float(np.quantile(dd, .75)),
                        share_new_gt_60m=float((dd > 60).mean()), centre_shift_m=float(np.hypot(b.x.mean() - a.x.mean(), b.y.mean() - a.y.mean())),
                        centre_out_m=float((b.x.mean() - a.x.mean()) * ux + (b.y.mean() - a.y.mean()) * uy) if np.isfinite(ux) else np.nan))
A = pd.DataFrame(adv); A.to_csv(f'{OUT}/a2_front_advance_30m.csv', index=False)
fr = pd.factorize(A.fire)[0]; nf = fr.max() + 1
def ratio(num, den):
    ok = np.isfinite(num); num, den, f = num[ok], den[ok], fr[ok]
    sn = np.bincount(f, num, nf); sd = np.bincount(f, den, nf); bs = [sn[i].sum() / sd[i].sum() for i in (rng.integers(0, nf, nf) for _ in range(1000))]
    return dict(m_h=round(float(num.sum() / den.sum()), 1), lo=round(float(np.quantile(bs, .025)), 1), hi=round(float(np.quantile(bs, .975)), 1), n=int(ok.sum()))
res['front_advance_30m'] = dict(pairs=len(A), fires=int(nf), median_gap_h=round(float(A.gap_h.median()), 1),
                                nearest_hot_pixel_advance=ratio(A.adv_med_m.values, A.gap_h.values),
                                centre_outward=ratio(A.centre_out_m.values, A.gap_h.values),
                                by_gap={f'{lo}-{hi} h': ratio(A.adv_med_m.values * ((A.gap_h >= lo) & (A.gap_h < hi)), A.gap_h.values * ((A.gap_h >= lo) & (A.gap_h < hi)))
                                        for lo, hi in [(12, 36), (36, 60), (60, 100), (100, 150)]})
# ---- 3. same-day Sentinel-2 + Landsat
sd = []
for fire, g in H.groupby('fire'):
    g = g.assign(date=g.t.dt.date)
    for dt_, q in g.groupby('date'):
        s2 = q[q.sensor == 'Sentinel-2']; ls = q[q.sensor == 'Landsat']
        if len(s2) >= 3 and len(ls) >= 3:
            d1, _ = cKDTree(np.c_[s2.x, s2.y]).query(np.c_[ls.x, ls.y])
            sd.append(dict(fire=fire, dmin=abs((s2.t.min() - ls.t.min()).total_seconds() / 60), centre_diff_m=float(np.hypot(s2.x.mean() - ls.x.mean(), s2.y.mean() - ls.y.mean())),
                           ls_to_nearest_s2_med_m=float(np.median(d1)), n_s2=len(s2), n_ls=len(ls)))
SD = pd.DataFrame(sd); SD.to_csv(f'{OUT}/a2_same_day_s2_landsat.csv', index=False)
res['same_day_s2_landsat'] = dict(n=len(SD), minutes_apart_median=float(SD.dmin.median()), centre_diff_median_m=round(float(SD.centre_diff_m.median())),
                                  landsat_px_to_nearest_s2_px_median_m=round(float(SD.ls_to_nearest_s2_med_m.median())))
json.dump(res, open(f'{OUT}/a2_hotpix.json', 'w'), indent=1, default=float); print(json.dumps(res, indent=1, default=float))
# ---- figure
fig, ax = plt.subplots(figsize=(8, 4.8))
cols = {'viirs': '#2a6fdb', 'terra': '#d9822b', 'aqua': '#3aa676'}
for k, g in LB.groupby('kind'):
    ax.errorbar(g.mean_dt_h, g.p_m, yerr=[g.p_m - g.lo, g.hi - g.p_m], fmt='o', color=cols[k], label={'viirs': 'VIIRS looks', 'terra': 'Terra MODIS', 'aqua': 'Aqua MODIS'}[k], capsize=3)
m = res['model_clock_viirs_only']; tt = np.linspace(-27, 27, 400)
ts = pd.Timestamp('2024-03-15 05:15') + pd.to_timedelta(tt, 'h'); cc = np.array([clock(x) for x in ts]) - clock(pd.Timestamp('2024-03-15 05:15'))
ist = (10.75 + tt) % 24; day = (ist >= 6) & (ist < 18)
fit = m['dC']['coef'] * cc + np.where(day, m['o_viirs_D']['coef'], m['o_viirs_N']['coef'])
ax.plot(tt, fit, color='#2a6fdb', lw=1, alpha=.6, label=f"fit: offset day {m['o_viirs_D']['coef']:.0f} m / night {m['o_viirs_N']['coef']:.0f} m, mean speed {m['dC']['coef']:.0f} m/h")
ax.axhline(0, color='k', lw=.6); ax.axvline(0, color='k', lw=.6, ls=':')
ax.set_xlabel('hours from the 30 m hot-pixel scene (~10:45 IST)'); ax.set_ylabel('coarse-look centre minus hot-pixel centre,\nalong the outward direction (m)')
ax.set_title('Coarse looks vs 30 m hot pixels, Ratapani (bars: 95% CI by fire)'); ax.legend(fontsize=8, loc='upper left')
fig.tight_layout(); fig.savefig(f'{OUT}/fig_a2_lag.png', dpi=130)
