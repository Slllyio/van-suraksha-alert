"""Pixel-level change model. Per 10 m pixel: best-break statistic on the embedding series, on its own and against the surrounding 500 m. Per point: how strong the strongest pixels are, and the before, after and change vectors of those pixels.
Reference scores use the same area weights and whole 5 km blocks; thresholds come from inner folds. Also fused with the time-series model, with a shuffled-label control. Usage: e83_cc_pxmodel.py [repeats]"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd

from e76_cc_train import REPORT, WORK, YS, load, ref_w, step_feats, wpr
from e77_cc_local import BOX, WIDE, curve, design, wide
from e79_cc_fusion import boot, cv_view, flags_at, line, px_table
from e48_tests import rule
from e49_ts import series_feats, ts_pass
from e63_cascade import NETS, feats, triggers

warnings.filterwarnings("ignore")
REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
TOP = 3                      # strongest pixels of the 25 in the box, about 0.03 ha
CACHE = WORK / "cc_px_feats.npz"
TARGETS = (.9, .8, .7, .6, .5)
SEED = 20261106


def px_features(d, A, W):
    """Series of each pixel, year-wide shift removed; summarised to fixed-size blocks per point."""
    if CACHE.exists():
        z = np.load(CACHE)
        return z["scal"], z["chg"], z["lchg"], z["pre"], z["post"]
    rnd = A[(d.set == "random").values].mean(axis=0)
    wr = W[(d.set == "random").values].mean(axis=0)
    shift, wshift = rnd - rnd.mean(axis=0), wr - wr.mean(axis=0)
    pos = {c: i for i, c in enumerate(d.cid)}
    n = len(d)
    scal, chg, lchg, pre_, post_ = np.full((n, 22), np.nan), np.zeros((n, 64)), np.zeros((n, 64)), np.zeros((n, 64)), np.zeros((n, 64))
    for l in open(WORK / "cc_emb_px.jsonl"):
        r = json.loads(l)
        i = pos.get(r.pop("cid"))
        if i is None:
            continue
        X = np.array([[r[f"y{y}_{b:02d}"] for b in range(64)] for y in YS], "float64").transpose(2, 0, 1)
        X = X / np.linalg.norm(X, axis=2, keepdims=True) - shift
        ring = (W[i] - wshift)
        L = X - ring[None]
        s, a, b = step_feats(X)
        ls, la, lb = step_feats(L)
        o = np.argsort(-s.t.values)[:TOP]
        lo = np.argsort(-ls.t.values)[:TOP]
        q = lambda v: [np.median(v), np.quantile(v, .75), np.quantile(v, .9), v.max()]
        scal[i] = q(s.t.values) + q(ls.t.values) + q(s.step.values) + q(ls.step.values) + [(s.t.values > 3).mean(), (s.t.values > 4).mean(), (s.t.values > 5).mean(), (ls.t.values > 3).mean(), np.median(s.brk.values[o]), s.noise.values[o].mean()]
        chg[i], lchg[i], pre_[i], post_[i] = (b[o] - a[o]).mean(axis=0), (lb[lo] - la[lo]).mean(axis=0), a[o].mean(axis=0), b[o].mean(axis=0)
    np.savez(CACHE, scal=scal, chg=chg, lchg=lchg, pre=pre_, post=post_)
    return scal, chg, lchg, pre_, post_


def maj(fs):
    return np.mean(fs, axis=0) >= .5


def main():
    d, A = load()
    scal, chg, lchg, pre, post = px_features(d, A, wide(d))
    ok = ~np.isnan(scal).any(axis=1)
    print("points with pixels", int(ok.sum()), "of", len(d), flush=True)
    d, scal, chg, lchg, pre, post = d[ok].reset_index(drop=True), scal[ok], chg[ok], lchg[ok], pre[ok], post[ok]
    y, w = d.y.values, ref_w(d)
    k = (d.set == "reference").values
    res = []
    B = {"step": scal, "change": chg, "local change": lchg, "before": pre, "after": post}
    runs = {}
    for name, parts in (("strongest pixels, scalars", ("step",)), ("+ change vector", ("step", "change", "local change")), ("+ before and after", ("step", "before", "after")), ("+ all", ("step", "change", "local change", "before", "after"))):
        X, sc, ve = design(B, parts)
        runs[name] = [cv_view(X, d, y, sc, ve, r) for r in range(REPEATS)]
        s = np.nanmean([a for a, _ in runs[name]], axis=0)
        print(name, "curve", curve(s[k], y[k], w[k]), flush=True)
    for name, r in runs.items():
        for tg in TARGETS:
            res.append(line(f"{name}, target {tg}", d, maj([flags_at(a, b, y, w, k, tg) for a, b in r]), y, w, k))
    p = px_table(d)
    sf = series_feats(p)
    t = triggers(p, sf)
    Fx = feats(p, sf, t).reindex(d.cid).values
    base = (t["rule"] & ts_pass(sf, (.15, .15, 0, 9))).groupby(p.pid).sum().reindex(d.cid).fillna(0).ge(2).values
    net = t[NETS["+ scrub tight"]].any(axis=1).groupby(p.pid).any().reindex(d.cid).fillna(False).values
    res.append(line("rule: filter + 2 px", d, base, y, w, k))
    res.append(line("rule net, no filter", d, net, y, w, k))
    best = runs["strongest pixels, scalars"]
    ts = [cv_view(Fx, d, y, list(range(Fx.shape[1])), [], r) for r in range(REPEATS)]
    both = [((a + c) / 2, [(x[0], x[1], (x[2] + z[2]) / 2) for x, z in zip(b, f)]) for (a, b), (c, f) in zip(best, ts)]
    for tg in TARGETS:
        res.append(line(f"time series, target {tg}", d, maj([flags_at(a, b, y, w, k, tg) for a, b in ts]), y, w, k))
        res.append(line(f"strongest pixels + time series, target {tg}", d, maj([flags_at(a, b, y, w, k, tg) for a, b in both]), y, w, k))
    # Cascade the user asked for: stage 1 at 90% recall on embeddings, then the time-series model inside it
    s1 = [flags_at(a, b, y, w, k, .9) for a, b in best]
    res.append(line("stage 1: embeddings at 0.9", d, maj(s1), y, w, k))
    for tg in (.85, .8, .7, .6):
        res.append(line(f"stage 1 at 0.9, then fused stage 2 at {tg}", d, maj([flags_at(a, b, y, w, k, tg, g) for (a, b), g in zip(both, s1)]), y, w, k))
    rng = np.random.default_rng(SEED)
    X, sc, ve = design(B, ("step",))
    shuf = []
    for rep in range(5):
        yy = y.copy()
        u = y >= 0
        yy[u] = rng.permutation(y[u])
        a, f = cv_view(X, d, yy, sc, ve, rep)
        shuf.append(wpr(y[k], flags_at(a, f, yy, w, k, .5)[k].astype(int), w[k]))
    res.append(dict(method="shuffled labels, target 0.5", precision=round(float(np.nanmean([a for a, _ in shuf])), 3), recall=round(float(np.mean([b for _, b in shuf])), 3)))
    print(json.dumps(res[-1]), flush=True)
    mean_b = np.nanmean([a for a, _ in best], axis=0)
    mean_f = np.nanmean([a for a, _ in both], axis=0)
    print("fused curve", curve(mean_f[k], y[k], w[k]))
    q = d[(d.stratum == "background") & (d.y == 1)].index
    rnd = (d.set == "random").values
    print(pd.DataFrame(dict(id=d.id[q], beat=d.beat[q], in_rule_net=net[q], pct_random_below=[round(100 * (mean_b[rnd] < mean_b[i]).mean()) for i in q])).to_string())
    r = pd.DataFrame(res)
    r.to_csv(REPORT / "cc_px_model.csv", index=False)
    d.assign(px_logit=mean_b, fused_logit=mean_f, rule_net=net, rule_filter=base).drop(columns=["x", "y_m"]).to_csv(REPORT / "cc_px_points_scored.csv", index=False)
    pd.set_option("display.width", 320, "display.max_columns", 30, "display.max_colwidth", 60)
    print(r.to_string())


if __name__ == "__main__":
    main()
