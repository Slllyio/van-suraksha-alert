"""Exhaustive hand-rule sweep on the pixel table, no GEE. Space: forest test x tree drop x NDVI drop x recent path x rolling pairs x NDVI fall x NBR fall x passing pixels.
Fronts are in-sample and optimistic. Held-out scores: settings chosen on training beats only, repeated 5-fold by beat, with bootstrap ranges by beat. Usage: e69_rule_sweep.py"""
import warnings
from itertools import product

import matplotlib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e48_tests import load
from e49_ts import rolling, series_feats
from e63_cascade import labels

warnings.filterwarnings("ignore")
REPORT = OUT / "interim" / "report"
TD, ND = (.12, .10, .08, .06), (.08, .05, .03)
FALLS = (0, .05, .1, .15, .2)
NPIX = (1, 2, 3, 5, 9)
REPEATS = 3
SETS = ("guna", "state")


def trig(p, forest, td, nd, recent, roll_on, roll):
    nda, ndb = p.nea - p.nla, p.neb - p.nlb
    if forest == "trees":
        fa, fb = p.ea_t >= .30, p.eb_t >= .30
    else:
        fa, fb = p.ea_t + p.ea_s >= .40, p.eb_t + p.eb_s >= .40
    a = fa & (p.ea_t - p.la_t >= td) & (nda >= nd)
    b = fb & (p.eb_t - p.lb_t >= td) & (ndb >= nd)
    m = a | b
    if recent:
        m = m | (fa & (nda >= nd) & (p.mon0 - p.mon24 >= .17))
    m = m | (((p.ea_t + p.ea_s >= .40) & (p.ea_t < .30) & (p.la_c - p.ea_c >= .15) & (nda >= .08)) | ((p.eb_t + p.eb_s >= .40) & (p.eb_t < .30) & (p.lb_c - p.eb_c >= .15) & (ndb >= .08)))     # the shrub-to-crop path stays in every setting
    if roll_on:
        m = m | roll
    return (m & (p.water < 5)).values


def pr(f, y, w):
    """f: configs x points; returns precision, recall."""
    fw = f * w
    tp = (fw * y).sum(axis=1)
    return tp / np.maximum(fw.sum(axis=1), 1e-9), tp / max((w * y).sum(), 1e-9)


def f1(p, r):
    return 2 * p * r / np.maximum(p + r, 1e-9)


def front(p, r):
    o = np.argsort(-r)
    keep, best = [], -1
    for i in o:
        if p[i] > best + 1e-9:
            keep.append(i)
            best = p[i]
    return keep


def boot(y, w, f, g, n=400):
    rng = np.random.default_rng(3)
    ug = np.unique(g)
    idx = {b: np.flatnonzero(g == b) for b in ug}
    P, R = [], []
    for _ in range(n):
        i = np.concatenate([idx[b] for b in rng.choice(ug, len(ug))])
        tp = (f[i] * w[i] * y[i]).sum()
        d = (f[i] * w[i]).sum()
        if d > 0:
            P.append(tp / d)
        R.append(tp / max((w[i] * y[i]).sum(), 1e-9))
    return [round(float(np.quantile(P, q)), 2) for q in (.025, .975)], [round(float(np.quantile(R, q)), 2) for q in (.025, .975)]


def main():
    p = load()
    L = labels().set_index("pid")
    L = L[L.set.isin(["blind_reference", "round1", "round2"]) & L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    sf = series_feats(p)
    roll = rolling(p, .12, .08) & (p.water < 5)
    pos = pd.Series(np.arange(len(L)), index=L.index)
    pi = pos[p.pid].values
    dn, dr = sf.drop_n.values, sf.drop_r.values
    cfg, flags = [], []
    trigs = list(product(("trees", "woody"), TD, ND, (True, False), (False, True)))
    for t in trigs:
        m = trig(p, *t, roll)
        for fn, fr in product(FALLS, FALLS):
            k = m & (dn >= fn if fn else True) & (dr >= fr if fr else True)
            c = np.bincount(pi, weights=k, minlength=len(L))
            for n in NPIX:
                cfg.append(t + (fn, fr, n))
                flags.append(c >= n)
    F = np.array(flags, dtype=bool)
    C = pd.DataFrame(cfg, columns=["forest", "tree_drop", "ndvi_drop", "recent", "rolling", "ndvi_fall", "nbr_fall", "npix"])
    print("configs", len(C), "points", F.shape[1], flush=True)
    y = L.y.values.astype(float)
    w = L.eval_w.values.astype(float)
    groups = L.group.values
    guna, state = (L.set == "blind_reference").values, L.set.isin(["round1", "round2"]).values
    zones = L.zone.values
    base = C[(C.forest == "trees") & (C.tree_drop == .12) & (C.ndvi_drop == .08) & C.recent & (~C["rolling"]) & (C.ndvi_fall == .15) & (C.nbr_fall == .15) & (C.npix == 2)].index[0]
    rule = C[(C.forest == "trees") & (C.tree_drop == .12) & (C.ndvi_drop == .08) & C.recent & (~C["rolling"]) & (C.ndvi_fall == 0) & (C.nbr_fall == 0) & (C.npix == 1)].index[0]
    # in-sample fronts
    fronts = []
    groupsets = [("Guna (owner labels)", guna), ("Statewide (my labels)", state)] + [(f"Statewide {z}", state & (zones == z)) for z in sorted(set(zones[state]))]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for ax, (nm, mk) in zip(axes.ravel(), groupsets):
        pp, rr = pr(F[:, mk], y[mk], w[mk])
        ok = np.flatnonzero(F[:, mk].any(axis=1))
        ke = ok[front(pp[ok], rr[ok])]
        fronts.append(C.iloc[ke].assign(set=nm, precision=pp[ke].round(3), recall=rr[ke].round(3)))
        ax.scatter(rr[ok], pp[ok], s=2, c="#cbd5e1")
        ax.plot(rr[ke], pp[ke], "-o", ms=3, c="#b91c1c", label="best in-sample")
        ax.scatter([rr[base]], [pp[base]], c="#1d4ed8", s=60, zorder=5, label="filter + 2 px")
        ax.scatter([rr[rule]], [pp[rule]], c="#65a30d", s=60, zorder=5, label="rule, no filter")
        ax.set_title(f"{nm}: {int(y[mk].sum())} real of {int(mk.sum())}", fontsize=10)
        ax.set_xlabel("Recall")
        ax.set_ylabel("Precision")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(REPORT / "rule_sweep_fronts.png", dpi=120)
    pd.concat(fronts).to_csv(REPORT / "rule_sweep_fronts.csv", index=False)
    # held-out selection
    OBJ = ["guna recall at P>=.75", "guna F1", "statewide F1", "mean of guna and statewide F1", "zone-aware F1"]
    oof = {o: np.zeros((REPEATS, len(L)), bool) for o in OBJ}
    picks, folds = [], []
    strat = np.where(guna, 0, 1) * 2 + y
    for rep in range(REPEATS):
        for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=rep).split(F.T[:, :1], strat, groups):
            folds.append(dict(rep=rep, guna_real=int(y[te][guna[te]].sum()), guna_background_real=int(((L.stratum.values[te] == "background") & (y[te] == 1)).sum()), statewide_real=int(y[te][state[te]].sum()), **{f"state_{z[:5]}": int(y[te][state[te] & (zones[te] == z)].sum()) for z in sorted(set(zones[state]))}))
            mg, ms = np.intersect1d(tr, np.flatnonzero(guna)), np.intersect1d(tr, np.flatnonzero(state))
            pg, rg = pr(F[:, mg], y[mg], w[mg])
            ps, rs = pr(F[:, ms], y[ms], w[ms])
            fg, fs = f1(pg, rg), f1(ps, rs)
            sel = {"guna recall at P>=.75": np.where(pg >= .75, rg, -1), "guna F1": fg, "statewide F1": fs, "mean of guna and statewide F1": (fg + fs) / 2}
            for o, v in sel.items():
                i = int(np.argmax(v))
                picks.append(dict(obj=o, rep=rep, cfg=i))
                oof[o][rep, te] = F[i, te]
            for z in set(zones[state]):
                mz = np.intersect1d(ms, np.flatnonzero(zones == z))
                pz, rz = pr(F[:, mz], y[mz], w[mz])
                v = f1(pz, rz) + (fg if z == "mixed_dry_deciduous" else 0)
                i = int(np.argmax(v))
                picks.append(dict(obj="zone-aware F1", rep=rep, zone=z, cfg=i))
                tz = te[zones[te] == z]
                oof["zone-aware F1"][rep, tz] = F[i, tz]
    res = []
    rows = [("rule, no filter", np.tile(F[rule], (REPEATS, 1))), ("filter + 2 px", np.tile(F[base], (REPEATS, 1)))] + list(oof.items())
    for nm, fl in rows:
        for sn, mk in groupsets:
            a, b = pr(fl[:, mk], y[mk], w[mk])
            maj = fl.mean(axis=0)[mk] >= .5
            ci = boot(y[mk], w[mk], maj, groups[mk])
            res.append(dict(setting=nm, points=sn, real=int(y[mk].sum()), precision=round(float(np.mean(a)), 3), p_range=ci[0], recall=round(float(np.mean(b)), 3), r_range=ci[1], flagged=int(maj.sum()), true=int((maj * y[mk]).sum()), p_sd_repeats=round(float(np.std(a)), 3), r_sd_repeats=round(float(np.std(b)), 3)))
    t = pd.DataFrame(res)
    t.to_csv(REPORT / "rule_sweep_heldout.csv", index=False)
    print(t[t.points.isin(["Guna (owner labels)", "Statewide (my labels)"])].to_string())
    print(t[~t.points.isin(["Guna (owner labels)", "Statewide (my labels)"]) & t.setting.isin(["filter + 2 px", "mean of guna and statewide F1", "zone-aware F1"])].drop(columns=["p_sd_repeats", "r_sd_repeats"]).to_string())
    print(pd.DataFrame(folds).describe().loc[["min", "50%", "max"]].round(1).to_string())
    k = pd.DataFrame(picks).merge(C, left_on="cfg", right_index=True)
    k.to_csv(REPORT / "rule_sweep_picks.csv", index=False)
    print(k.groupby("obj")[["tree_drop", "ndvi_drop", "ndvi_fall", "nbr_fall", "npix"]].agg(lambda s: s.value_counts().to_dict()).to_string())
    print(k.groupby("obj")[["forest", "recent", "rolling"]].agg(lambda s: s.value_counts().to_dict()).to_string())
    z = k[k.obj == "zone-aware F1"]
    print(z.groupby("zone")[["tree_drop", "ndvi_fall", "nbr_fall", "npix", "rolling"]].agg(lambda s: s.value_counts().index[0]).to_string())


if __name__ == "__main__":
    main()
