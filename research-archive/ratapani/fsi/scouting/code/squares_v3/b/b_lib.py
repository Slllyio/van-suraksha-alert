"""Shared settings for squares v3 part B (per-fire spread speed and growth by partial pooling).

Inputs are read-only: the pooled run's scratch (r19_pool), the tracking run's scratch (r19_track), round-17 scars/photos,
and the squares_v2 result tables. Nothing here writes outside squares_v3/b/ and the r20_b scratch folder.

DROP-IN FOR CORRECTED SPEEDS (sibling part A, squares_v3_speed_truth.md):
  * class_correction(): if squares_v3/a/results/class_speed_correction.json exists, its day/night factors (or absolute
    day_m_h / night_m_h, turned into factors against the v2 headline 30.7 / 5.2 m/h) multiply every class mean.
  * edge_term(): if squares_v3/a/results/edge_term_by_pair.parquet exists (column pair_row = ctx.parquet row index, column edge_m),
    that edge-reach artefact is subtracted from each pair's outward move before anything is fitted.
  * diurnal(): the clock (multiplier of the daily mean by IST hour). Default = v2 forest fit (diurnal_fit.json);
    a file squares_v3/a/results/diurnal_fit.json with the same layout replaces it.
  Set B_IGNORE_A=1 to force the v2 numbers.
"""
import json, os
import numpy as np, pandas as pd
ROOT = '/mnt/project-files'
SCR = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad'
POOL = f'{SCR}/r19_pool'; TRACK = f'{SCR}/r19_track'; R17 = f'{SCR}/r17_exp_code'
SC = os.environ.get('B_SCRATCH', f'{SCR}/r20_b'); os.makedirs(SC, exist_ok=True)
V2 = f'{ROOT}/ratapani/fsi/scouting/code/squares_v2'
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'; os.makedirs(OUT, exist_ok=True)
A_RES = f'{ROOT}/ratapani/fsi/scouting/code/squares_v3/a/results'
V2_HEADLINE = {'D': 30.7, 'N': 5.2}          # squares_v2_pooled.md headline outward speeds (m/h)
VIIRS = ('S-NPP', 'NOAA-20', 'NOAA-21')
VT = {170: 'agriculture', 26: 'dry deciduous', 25: 'teak', 28: 'teak', 37: 'teak', 23: 'moist deciduous',
      106: 'degraded forest', 36: 'sal', 27: 'sal', 120: 'scrub/grass', 121: 'scrub/grass', 123: 'scrub/grass',
      116: 'scrub/grass', 117: 'scrub/grass', 135: 'scrub/grass', 40: 'bamboo', 30: 'bamboo'}

def ftype(vtm):
    vtm = pd.Series(vtm)
    return vtm.map(VT).fillna(pd.Series(np.where(vtm.between(11, 119), 'other forest', 'other non-forest'), index=vtm.index)).values

def use_a():
    return not os.environ.get('B_IGNORE_A')

def class_correction():
    """Multipliers {'D': f, 'N': f} for the class means, and a label saying where they came from.
    Part A's factors are the SAME correction as its per-pair edge term, so they are used only when the per-pair file is
    absent (otherwise the correction would be counted twice)."""
    fn = f'{A_RES}/class_speed_correction.json'
    if use_a() and os.path.exists(f'{A_RES}/edge_term_by_pair.parquet'):
        return {'D': 1.0, 'N': 1.0}, 'part A per-pair edge term (factors not applied on top)'
    if use_a() and os.path.exists(fn):
        j = json.load(open(fn)); f = {}
        for dn, kf, ka in [('D', 'day_factor', 'day_m_h'), ('N', 'night_factor', 'night_m_h')]:
            if kf in j: f[dn] = float(j[kf])
            elif ka in j: f[dn] = float(j[ka]) / V2_HEADLINE[dn]
            else: f[dn] = 1.0
        return f, f'part A ({fn})'
    return {'D': 1.0, 'N': 1.0}, 'v2 pooled (no correction file from part A)'

def edge_term(index):
    fn = f'{A_RES}/edge_term_by_pair.parquet'
    if use_a() and os.path.exists(fn):
        e = pd.read_parquet(fn)
        e = e.set_index('pair_row')['edge_m'] if 'pair_row' in e.columns else e['edge_m']
        return e.reindex(np.asarray(index)).fillna(0.0).values, f'part A edge term ({int(e.notna().sum())} pairs, file of {pd.Timestamp(os.path.getmtime(fn), unit="s"):%d %b %H:%M} UTC)'
    return np.zeros(len(index)), 'none'

_CLK = {}
def diurnal():
    """multiplier m(h) of the daily-mean speed at IST hour h (mean over 24 h = 1), on a 0.25 h grid"""
    if not _CLK:
        fn = f'{A_RES}/diurnal_fit.json'
        src = fn if (use_a() and os.path.exists(fn)) else f'{V2}/pooled/results/diurnal_fit.json'
        c = json.load(open(src))['forest']['curve']
        hh = np.array([float(h) for h in c]); r = np.array(list(c.values()), float); r = r / r.mean()
        _CLK.update(h=hh, m=r, src=src)
    return _CLK

def clock_hours(ist0, gap_h, n=48):
    """integral of m(h) over [ist0, ist0 + gap_h] (hours of 'average-day' spreading); vectorised"""
    C = diurnal(); ist0 = np.asarray(ist0, float); gap_h = np.asarray(gap_h, float)
    s = np.linspace(0, 1, n)[None, :]
    hh = (ist0[:, None] + s * gap_h[:, None]) % 24
    m = np.interp(hh, np.r_[C['h'], 24.0], np.r_[C['m'], C['m'][0]])
    return np.trapezoid(m, s, axis=1) * gap_h

def clock_between(t0_ist_abs, t1_ist_abs):
    """clock hours between two absolute times given as hours (IST, any origin)"""
    t0 = np.asarray(t0_ist_abs, float); t1 = np.asarray(t1_ist_abs, float)
    return clock_hours(t0 % 24, t1 - t0)

def boot_ci(values, groups, stat=np.mean, n=1000, seed=0, weights=None):
    """95% bootstrap range resampling groups (fire clusters)"""
    rng = np.random.default_rng(seed); v = np.asarray(values, float); g = pd.factorize(np.asarray(groups))[0]
    w = np.ones(len(v)) if weights is None else np.asarray(weights, float)
    ng = g.max() + 1; sw = np.bincount(g, w, ng); swv = np.bincount(g, w * v, ng)
    bs = [swv[k].sum() / sw[k].sum() for k in (rng.integers(0, ng, ng) for _ in range(n))]
    return float(swv.sum() / sw.sum()), float(np.quantile(bs, .025)), float(np.quantile(bs, .975))
