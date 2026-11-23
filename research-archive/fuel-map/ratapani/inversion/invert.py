"""Back-solve per-class fuel load intervals from (1) spread runs vs scar size and (2) VIIRS fire radiative energy.
Classes (20 m): 1 closed teak (S2 cover>=0.4, teak prob>=0.5), 2 closed other deciduous, 3 open forest (cover 0.1-0.4),
4 grass/scrub/sparse. Spread runs: spread thread's final config res_loose_lfi_m2 (loose bed, leaf fall interpolated,
ROS x2, roads as barriers, no wind), forecast area to last detection + 12 h."""
import pandas as pd, numpy as np, json, statsmodels.api as sm, warnings
warnings.filterwarnings('ignore')
N = ['closed teak', 'closed other deciduous', 'open forest', 'grass/scrub/sparse']
d = pd.read_parquet('events_scar_s.parquet')
r = pd.read_parquet('/mnt/project-files/ratapani/spread/results/res_loose_lfi_m2.parquet')
m = r.merge(d[['event', 'scar_ha', 'c1', 'c2', 'c3', 'c4', 'frp_sum']], on='event')
m = m[(m.scar_px >= 25) & (m.area_end > 0)].copy()
X = m[['c1', 'c2', 'c3', 'c4']].fillna(0).values; X = X / np.maximum(X.sum(1, keepdims=True), 1e-6)
rng = np.random.default_rng(1); out = {}
# (1) spread: log(scar/forecast) = sum_k share_k * log(a_k), median regression, bootstrap
y = np.log(m.scar_px / m.area_end).values
fit = lambda Xi, yi: sm.QuantReg(yi, Xi).fit(q=0.5).params
p0 = fit(X, y); Bt = np.array([fit(X[i], y[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(300))])
# Rothermel: area ~ ROS^2 (fire grows as a disc). ROS vs litter load at fixed bulk density (loose bed 2.5 kg/m3)
def ros(w, rho=2.5, M=0.04, Mx=0.25, sav_m=6562):
    w = w * 0.2048; d_ = (w / 0.2048 / rho) * 3.281; s = sav_m / 3.281; rb = w / d_; b = rb / 32; bop = 3.348 * s ** -0.8189; A = 133 * s ** -0.7913
    Gm = s ** 1.5 / (495 + 0.0594 * s ** 1.5); G = Gm * (b / bop) ** A * np.exp(A * (1 - b / bop)); rr = M / Mx; eM = 1 - 2.59 * rr + 5.11 * rr ** 2 - 3.52 * rr ** 3
    IR = G * w * (1 - .0555) * 8000 * eM * 0.174 * .01 ** -0.19; xi = np.exp((0.792 + 0.681 * s ** 0.5) * (b + 0.1)) / (192 + 0.2595 * s)
    return IR * xi / (rb * np.exp(-138 / s) * (250 + 1116 * M)) * 0.3048 * 60
wg = np.linspace(0.01, 3.0, 3000); rg = ros(wg)
def load_for_ros_ratio(w0, k):                                   # load giving k x the ROS at load w0
    return np.interp(k * ros(w0), rg, wg, right=np.nan)
W0 = 0.15                                                       # kg/m2 typical mapped peak litter (map mean ~1.46 t/ha)
sp = {}
for j in range(4):
    a = np.exp(np.r_[p0[j], np.percentile(Bt[:, j], [5, 95])])  # area factor median, 5, 95
    kA = np.sqrt(a); kB = np.sqrt(a) * 2                          # A: keep the fitted ROS x2 as non-fuel; B: put all of it on the load
    sp[N[j]] = dict(n_pure=int((X[:, j] >= 0.6).sum()), area_factor=np.round(a, 2).tolist(),
                    load_tha_keep_x2=np.round([load_for_ros_ratio(W0, k) * 10 for k in kA], 2).tolist(),
                    load_tha_all_on_load=np.round([load_for_ros_ratio(W0, k) * 10 for k in kB], 2).tolist())
out['spread'] = sp
# (2) FRE: mean pass FRP x duration (mid) or x 6 h per pass (low); 0.368 kg/MJ (Wooster 2005)
v = pd.read_parquet('viirs_events_spread.parquet')
pp = v.groupby(['event', 'overpass']).frp.sum().groupby('event').agg(['mean', 'count'])
m = m.join(pp, on='event'); dur = (m.t0 - m.t0).dt.total_seconds()
ev = v.groupby('event').t.agg(['min', 'max']); m = m.join(ev, on='event')
dh = (m['max'] - m['min']).dt.total_seconds() / 3600 + 12
m['low'] = 0.368 * m['mean'] * m['count'] * 6 * 3600 / (m.scar_ha * 1e4) * 10
m['mid'] = 0.368 * m['mean'] * dh * 3600 / (m.scar_ha * 1e4) * 10
fr = {}
for j in range(4):
    s = m[X[:, j] >= 0.6]
    fr[N[j]] = dict(n_pure=len(s), low_tha_median_iqr=np.round([s.low.median(), s.low.quantile(.25), s.low.quantile(.75)], 2).tolist(),
                    mid_tha_median_iqr=np.round([s.mid.median(), s.mid.quantile(.25), s.mid.quantile(.75)], 2).tolist())
out['frp'] = fr; out['n_fires'] = int(len(m))
json.dump(out, open('inversion.json', 'w'), indent=1); print(json.dumps(out, indent=1))
m.to_parquet('inversion_fires.parquet')
