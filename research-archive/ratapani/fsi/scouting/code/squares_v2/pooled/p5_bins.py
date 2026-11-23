"""Step 5: what the pooled outward speed depends on, and how many pairs a bin needs.
Bins: time slot (13:30 day / 01:30 night), gap (25/50/75 min), month, forest type (VTM), slope, Ratapani cover class,
fire size (pixels in the two looks), FRP, fire age, distance from earlier detections, season (each season alone: a
held-out-season consistency check). Same bins on the static null. Minimum N per bin for 80% power to see a given speed.
Also: per-pass offsets (do two passes share an offset beyond the global sensor offset?), three-satellite loop closure,
and robust variants (trimmed / sigma-culled means, 1/pixel-area^2 weights, near-duplicate-free looks are not possible
from pair summaries -> see note)."""
import json, os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
rng = np.random.default_rng(3); CLIP = 2000.0
F = pd.read_parquet(f'{SC}/fires_small.parquet'); N0 = pd.read_parquet(f'{SC}/static_small.parquet')
att = pd.read_csv('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_types_data/VegAttributes.csv', encoding='utf-8-sig')
VT = {170: 'agriculture', 26: 'dry deciduous', 25: 'teak (mixed/pure)', 28: 'teak (mixed/pure)', 37: 'teak (mixed/pure)',
      23: 'moist deciduous', 106: 'degraded forest', 36: 'sal', 27: 'sal', 120: 'scrub / savannah / grass', 121: 'scrub / savannah / grass',
      123: 'scrub / savannah / grass', 116: 'scrub / savannah / grass', 117: 'scrub / savannah / grass', 135: 'scrub / savannah / grass',
      40: 'bamboo', 30: 'bamboo'}
COVER = {1: 'deciduous tree', 2: 'green under canopy', 3: 'open + green (crop leak)', 4: 'open grass / low cover', 5: 'sparse / bare'}
for D in (F, N0):
    D['ftype'] = D.vtm.map(VT).fillna(pd.Series(np.where(D.vtm.between(11, 119), 'other forest', 'other non-forest'), index=D.index))
    D['npix'] = D.nA + D.nB; D['frp2'] = D.frpA + D.frpB
    D['gapc'] = pd.cut(D.gap_min, [0, 35, 62, 120], labels=['~25 min', '~50 min', '~75 min'])
def pooled(df, col='p_out', n=400, wcol=None):
    df = df[np.isfinite(df[col])]
    if len(df) < 30: return None
    v = df[col].clip(-CLIP, CLIP).values; w = df[wcol].values if wcol else np.ones(len(v))
    cl = pd.factorize(df.cl)[0]; nc = cl.max() + 1
    sw = np.bincount(cl, w, nc); swv = np.bincount(cl, w * v, nc); m = swv.sum() / sw.sum()
    bs = np.array([swv[k].sum() / sw[k].sum() for k in (rng.integers(0, nc, nc) for _ in range(n))])
    gh = df.gap_h.mean(); sd = v.std(); se_naive = sd / np.sqrt(len(v)); se = bs.std()
    return dict(n=len(v), clusters=int(nc), mean_m=round(m, 1), speed=round(m / gh, 1), lo=round(np.quantile(bs, .025) / gh, 1),
                hi=round(np.quantile(bs, .975) / gh, 1), sd_m=round(sd), deff=round((se / se_naive) ** 2, 2), gap_min=round(gh * 60))
rows = []
def add(dim, key, df, nul=None):
    r = pooled(df)
    if r is None: return
    r.update(dim=dim, bin=str(key))
    if nul is not None:
        q = pooled(nul)
        if q: r.update(null_speed=q['speed'], null_ci=f"{q['lo']} to {q['hi']}", null_n=q['n'])
    rows.append(r)
add('all', 'all', F, N0)
for dn in 'DN':
    lab = '13:30 day' if dn == 'D' else '01:30 night'
    f, s = F[F.dn == dn], N0[N0.dn == dn]
    add('slot', lab, f, s)
    for g, d in f.groupby('gapc', observed=True): add('slot x gap', f'{lab}, {g}', d, s[s.gapc == g])
    for m_, d in f.groupby('month_'): add('slot x month', f'{lab}, month {m_}', d)
    for t_, d in f.groupby('ftype'): add('slot x forest type', f'{lab}, {t_}', d, s[s.ftype == t_] if (s.ftype == t_).sum() > 30 else None)
    for b, d in f.groupby(pd.cut(f.slope, [-1, 2, 5, 10, 90]), observed=True): add('slot x slope deg', f'{lab}, {b}', d)
    for b, d in f.groupby(pd.cut(f.npix, [1, 2, 3, 5, 9, 1e4]), observed=True): add('slot x pixels in both looks', f'{lab}, {b}', d, s[pd.cut(s.npix, [1, 2, 3, 5, 9, 1e4]) == b])
    for b, d in f.groupby(pd.qcut(f.frp2, 5), observed=True): add('slot x FRP (both looks, MW)', f'{lab}, {b}', d)
    for b, d in f.groupby(pd.cut(f.age_h, [-1, 13, 25, 49, 1e4]), observed=True): add('slot x fire age h', f'{lab}, {b}', d)
    for b, d in f.groupby(pd.cut(f.u_len, [0, 300, 700, 1500, 1e5]), observed=True): add('slot x distance from earlier centre m', f'{lab}, {b}', d, s[pd.cut(s.u_len, [0, 300, 700, 1500, 1e5]) == b])
    for y_, d in f.groupby('season'): add('slot x season (each alone)', f'{lab}, {y_}', d, s[s.season == y_])
    fr = f[f.cover > 0]
    for c_, d in fr.groupby('cover'): add('slot x Ratapani cover', f'{lab}, {COVER.get(c_, c_)}', d)
    add('slot x Ratapani box', f'{lab}, Ratapani cover extent', fr)
    fo = f[f.ftype != 'agriculture']
    add('slot, forest only', f'{lab}, all forest+scrub', fo)
    for g, d in fo.groupby('gapc', observed=True): add('slot x gap, forest only', f'{lab}, {g}', d)
B = pd.DataFrame(rows)[['dim', 'bin', 'n', 'clusters', 'gap_min', 'mean_m', 'speed', 'lo', 'hi', 'sd_m', 'deff', 'null_speed', 'null_ci', 'null_n']]
B.to_csv(f'{OUT}/pooled_bins.csv', index=False); pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500); print(B.to_string())
# minimum N per bin: 80% power, two-sided 5%, to see speed v (m/h) at gap 50 min, with the measured SD and design effect
res = {}
for dn in 'DN':
    d = F[F.dn == dn]; sd = d.p_out.clip(-CLIP, CLIP).std(); deff = float(B[(B.dim == 'slot') & (B.bin.str.startswith('13:30' if dn == 'D' else '01:30'))].deff.iloc[0])
    res[dn] = {f'{v} m/h': int(np.ceil(deff * (2.8 * sd / (v * 50 / 60)) ** 2)) for v in [5, 10, 20, 50]}
    res[dn]['sd_m'] = round(sd); res[dn]['deff'] = deff
res['note'] = 'pairs needed per bin to detect a mean outward speed of v (or a difference of v between two bins: x2)'
# robust variants of the headline
var = {}
for dn in 'DN':
    d = F[F.dn == dn].copy(); gh = d.gap_h.mean()
    v = d.p_out.values
    for nm, keep in [('clip 2 km (headline)', np.abs(v) < 1e9), ('trim |p| < 1 km', np.abs(v) < 1000),
                     ('3 sigma then 1.5 sigma cull', None)]:
        if keep is None:
            x = v.copy(); med = np.median(x); s = 1.4826 * np.median(np.abs(x - med)); k = np.abs(x - med) < 3 * s
            med = np.median(x[k]); s = 1.4826 * np.median(np.abs(x[k] - med)); keep = np.abs(x - med) < 1.5 * s
        r = pooled(d[keep]); var[f'{dn} {nm}'] = f"{r['speed']} m/h ({r['lo']} to {r['hi']}), n {r['n']}"
    d['w2'] = 1 / ((d.scanA * d.trackA) ** 2 + (d.scanB * d.trackB) ** 2)
    r = pooled(d, wcol='w2'); var[f'{dn} weights 1/pixel-area^2'] = f"{r['speed']} m/h ({r['lo']} to {r['hi']})"
    r = pooled(d, wcol='w'); var[f'{dn} inverse-variance weights'] = f"{r['speed']} m/h ({r['lo']} to {r['hi']})"
    r = pooled(d, col='p_out_w'); var[f'{dn} FRP-weighted centres'] = f"{r['speed']} m/h ({r['lo']} to {r['hi']})"
    r = pooled(d, col='p_out_perp'); var[f'{dn} perpendicular component'] = f"{r['speed']} m/h ({r['lo']} to {r['hi']})"
    md = np.median(v); var[f'{dn} median projection'] = f'{md / gh:.1f} m/h'
res['robust_variants'] = var
# per-pass offsets: static groups sharing the same pass pair -- is there a common offset beyond the global one?
S = N0.copy(); S['pp'] = S.sA + S.sB + S.tA.dt.floor('15min').astype(str)
k = S.groupby('pp').cE.transform('size') >= 3; S = S[k]
pp = {}
for c in ['cE', 'cN']:
    x = S[c].clip(-CLIP, CLIP); m = x.groupby(S.pp).transform('mean'); nn = S.groupby('pp')[c].transform('size')
    within = ((x - m) ** 2).sum() / (len(x) - S.pp.nunique())
    gm = x.groupby(S.pp).mean(); gn = S.groupby('pp').size()
    between = (((gm - x.mean()) ** 2) * gn).sum() / (len(gm) - 1)
    n0 = (gn.sum() - (gn ** 2).sum() / gn.sum()) / (len(gm) - 1)
    pp[c] = dict(pass_pairs=int(len(gm)), groups=int(len(x)), within_sd=round(np.sqrt(within)), shared_offset_sd=round(np.sqrt(max((between - within) / n0, 0)), 1))
res['per_pass_shared_offset (static, ANOVA)'] = pp
json.dump(res, open(f'{OUT}/pooled_bins_summary.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
