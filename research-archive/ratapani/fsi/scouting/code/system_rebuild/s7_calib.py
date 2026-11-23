"""Layer 3: calibration and reliability. Target = a type-0 detection (control burns dropped, 15 Feb-31 May) in the square on
t+1 or t+2. The saved cube of a variant gives the model probability for every square-day of the test seasons.
Isotonic map fitted on the first test season (2022 / 2025), applied to the later ones (2023-24 / 2026), as an operational
system would recalibrate on last season. Reliability table by predicted-probability bin, raw and calibrated.
Usage: python3 s7_calib.py VARIANT period. Out: out/s7_reliability_{variant}_{period}.csv, fig4_reliability.png"""
import sys, pickle, numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression
import common as C, features as Fe
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt

def labels(y, U):
    V = C.load_det([y]); v = V[(V.type == 0) & ~V.ctrl]; md = v.ld.dt.month * 100 + v.ld.dt.day; v = v[(md >= 215) & (md <= 531)]
    days = pd.date_range(f'{y}-01-01', f'{y}-06-02'); di = pd.Series(np.arange(len(days)), index=days)
    f = v.row.values * C.W + v.col.values; idx = np.searchsorted(U, f); ok = (idx < len(U)) & (U[np.minimum(idx, len(U) - 1)] == f)
    FT = np.zeros((len(days), len(U)), bool); FT[di[v.ld.values[ok]].values, idx[ok]] = True
    iss = np.where((days.month * 100 + days.day >= 213) & (days.month * 100 + days.day <= 530))[0]
    return np.stack([FT[t + 1] | FT[t + 2] for t in iss])

if __name__ == '__main__':
    var, per = sys.argv[1], sys.argv[2]; U = Fe.base()['U']
    cube = pickle.load(open(C.SC + f'cube_{var}_{per}{C.TAG}.pkl', 'rb')); ys = sorted(cube)
    Y = {y: labels(y, U) for y in ys}
    fit_y, app = ys[0], ys[1:]
    p0 = cube[fit_y].ravel(); y0 = Y[fit_y].ravel()
    rng = np.random.default_rng(0); sub = rng.random(len(p0)) < 0.2
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(p0[sub], y0[sub])
    p = np.concatenate([cube[y].ravel() for y in app]); yy = np.concatenate([Y[y].ravel() for y in app]); pc = iso.predict(p)
    bins = [0, .001, .002, .005, .01, .02, .05, .1, .2, .5, 1]
    rows = []
    for nm, pp in (('raw', p), ('isotonic', pc)):
        b = pd.cut(pp, bins, include_lowest=True)
        g = pd.DataFrame(dict(b=b, p=pp, y=yy)).groupby('b', observed=True).agg(n=('y', 'size'), mean_pred=('p', 'mean'), observed=('y', 'mean'))
        g['kind'] = nm; g['share'] = g.n / len(pp); rows.append(g.reset_index())
    T = pd.concat(rows); T['b'] = T.b.astype(str); T.to_csv(C.OUT + f's7_reliability_{var}_{per}{C.TAG}.csv', index=False); print(T.round(5).to_string())
    base = yy.mean()
    br = lambda q: np.mean((q - yy) ** 2); bss = lambda q: 1 - br(q) / br(np.full_like(q, base))
    top = np.quantile(p, 0.99); print('base rate', base, 'Brier skill raw', bss(p), 'iso', bss(pc), 'top1% observed', yy[p >= top].mean(), 'x base', yy[p >= top].mean() / base)
    fig, ax = plt.subplots(figsize=(5, 5))
    for nm, mk in (('raw', 'o-'), ('isotonic', 's-')):
        t = T[T.kind == nm]; ax.loglog(t.mean_pred, t.observed, mk, label=nm)
    ax.plot([1e-4, 1], [1e-4, 1], 'k:'); ax.set_xlabel('predicted chance of a detected fire on day +1/+2'); ax.set_ylabel('observed share')
    ax.set_title(f'Reliability, {var}, {"2023-24" if per == "held" else "2026"} (iso fitted on {fit_y})'); ax.legend(); plt.tight_layout()
    plt.savefig(C.OUT + ('fig4_reliability.png' if per == 'held' else 'fig4b_reliability_fwd.png'), dpi=110)
