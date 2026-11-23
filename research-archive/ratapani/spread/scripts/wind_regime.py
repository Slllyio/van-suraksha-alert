"""Audit item 5: wind by regime. The physics with ERA5-Land wind (ms_wind) against the wind-free final model (ms), both scored on the grown
outlines by barrier_phys.py, split by the 10 m wind speed at the first detection (terciles), fire size (outline terciles) and fuel class
(grass share / canopy of the outline, event_classes.py). Shape = Sorensen at the outline's area; also free-run area at 26 h and later-pass
hits. Differences with 95% intervals from 500 fire bootstraps.
  python3 wind_regime.py 'data/barrier_phys_[0-3].parquet' out.json
"""
import numpy as np, pandas as pd, sys, json, glob
import sim
rng = np.random.default_rng(5); NB = 500


def wind_at_first(events):
    v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.event.isin(events)]
    rows = []
    for s, g in v.groupby('season'):
        W, P = sim.load_weather(int(s))
        for e, ev in g.groupby('event'):
            pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]; w = W[pid]
            th = ev.t.min().floor('h'); w24 = w.loc[th: th + pd.Timedelta(hours=23)]
            rows.append(dict(event=int(e), ws0=float(w.loc[th].ws) if th in w.index else np.nan, ws24=float(w24.ws.mean()) if len(w24) else np.nan,
                             ws24_max=float(w24.ws.max()) if len(w24) else np.nan))
    return pd.DataFrame(rows)


def ci_diff(a, b):
    d = a - b; vals = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(NB)]
    return float(d.mean()), [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def main(pat, out):
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(pat))], ignore_index=True); d = d[d.scar_px >= 25]
    a = d[d.variant == 'ms'].set_index('event'); b = d[d.variant == 'ms_wind'].set_index('event'); ix = a.index.intersection(b.index)
    a, b = a.loc[ix], b.loc[ix]
    cls = pd.read_parquet(f'{sim.DATA}/event_classes.parquet').set_index('event')
    w = wind_at_first(ix).set_index('event')
    t = pd.DataFrame(dict(sor_nowind=a.sor, sor_wind=b.sor, sor26_nowind=a.sor26, sor26_wind=b.sor26, area26_nowind=a.area26, area26_wind=b.area26,
                          hit_nowind=a.hit, hit_wind=b.hit, n_later=a.n_later, scar_px=a.scar_px, season=a.season))
    t = t.join(cls[['grass_share', 'canopy_mean']]).join(w)
    t['fuel'] = np.where(t.grass_share >= 0.5, 'grass/scrub', np.where((t.grass_share < 0.1) & (t.canopy_mean >= 40), 'closed forest', 'open/mixed'))
    t['ws_bin'] = pd.qcut(t.ws24, 3, labels=['calm', 'mid', 'windy']); t['size_bin'] = pd.qcut(t.scar_px, 3, labels=['small', 'medium', 'large'])
    res = dict(n=len(t), ws24_terciles_ms=[float(x) for x in t.ws24.quantile([1 / 3, 2 / 3])], size_terciles_ha=[float(x * 0.04) for x in t.scar_px.quantile([1 / 3, 2 / 3])])
    m, ci = ci_diff(t.sor_wind.values, t.sor_nowind.values)
    res['all'] = dict(sor_nowind=float(t.sor_nowind.mean()), sor_wind=float(t.sor_wind.mean()), diff=m, diff_ci=ci, wind_better_share=float((t.sor_wind > t.sor_nowind).mean()),
                      sor26_nowind=float(t.sor26_nowind.mean()), sor26_wind=float(t.sor26_wind.mean()), area26_ratio=float(t.area26_wind.median() / max(t.area26_nowind.median(), 1)),
                      hit_nowind=float(t.hit_nowind.sum() / max(t.n_later.sum(), 1)), hit_wind=float(t.hit_wind.sum() / max(t.n_later.sum(), 1)))
    for key in ['ws_bin', 'size_bin', 'fuel', 'season']:
        res[key] = {}
        for k, g in t.groupby(key, observed=True):
            m, ci = ci_diff(g.sor_wind.values, g.sor_nowind.values)
            res[key][str(k)] = dict(n=len(g), sor_nowind=float(g.sor_nowind.mean()), sor_wind=float(g.sor_wind.mean()), diff=m, diff_ci=ci, wind_better_share=float((g.sor_wind > g.sor_nowind).mean()),
                                    hit_nowind=float(g.hit_nowind.sum() / max(g.n_later.sum(), 1)), hit_wind=float(g.hit_wind.sum() / max(g.n_later.sum(), 1)))
    # windy and large, the regime where wind should matter most
    g = t[(t.ws_bin == 'windy') & (t.size_bin == 'large')]
    if len(g) > 10:
        m, ci = ci_diff(g.sor_wind.values, g.sor_nowind.values); res['windy_large'] = dict(n=len(g), sor_nowind=float(g.sor_nowind.mean()), sor_wind=float(g.sor_wind.mean()), diff=m, diff_ci=ci)
    json.dump(res, open(out, 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ['n', 'all', 'ws_bin', 'size_bin', 'fuel']}, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
