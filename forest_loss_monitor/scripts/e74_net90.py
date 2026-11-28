"""90% net design, offline: ladder of candidate nets (all window based, so they can be computed locally from stored window statistics), then the filter sweep on the widest useful net, deciduous points only.
Compares window falls (2017-19 vs 2022-24 Oct-Nov) with fitted-break falls. Patch-size costs come from polygons and from the old map. Usage: e74_net90.py net | filter | size"""
import sys
import warnings
from itertools import product

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage
from sklearn.model_selection import StratifiedGroupKFold

from common import *
from e23_guna_labels import wpr
from e48_tests import GT, load, s2f_flags
from e49_ts import rolling, series_feats
from e63_cascade import labels
from e69_rule_sweep import boot, pr

warnings.filterwarnings("ignore")
REPORT = OUT / "interim" / "report"
DEC = ("mixed_dry_deciduous", "teak_belt")


def windows(p):
    w = pd.DataFrame(index=p.index)
    for b, nm in (("ln", "n"), ("lr", "r"), ("lb", "b")):
        w[nm + "_e"] = p[[f"{b}{y}" for y in (2017, 2018, 2019)]].mean(axis=1)
        w[nm + "_l"] = p[[f"{b}{y}" for y in (2022, 2023, 2024)]].mean(axis=1)
    w["wn"], w["wr"], w["wb"] = w.n_e - w.n_l, w.r_e - w.r_l, w.b_l - w.b_e
    return w


def nets(p, w, sf):
    nda, ndb, nw = p.nea - p.nla, p.neb - p.nlb, p.water < 5
    woa, wob = p.ea_t + p.ea_s, p.eb_t + p.eb_s

    def core(fm, td, nd):
        return (((woa >= fm) & (p.ea_t - p.la_t >= td) & (nda >= nd)) | ((wob >= fm) & (p.eb_t - p.lb_t >= td) & (ndb >= nd))) | ((woa >= fm) & (nda >= nd) & (p.mon0 - p.mon24 >= .17))
    s2c = ((woa >= .4) & (p.ea_t < .3) & (p.la_c - p.ea_c >= .15) & (nda >= .08)) | ((wob >= .4) & (p.eb_t < .3) & (p.lb_c - p.eb_c >= .15) & (ndb >= .08))
    s2f = s2f_flags(p, .1, .15, .3, 2)
    base = core(.4, .06, .05) | s2c | s2f
    wood = (woa >= .3) | (wob >= .3)
    o = {"wide net + scrub": base}
    o["+ NBR window fall >= .15"] = base | (wood & (w.wr >= .15))
    o["+ NBR window fall >= .10"] = base | (wood & (w.wr >= .10))
    o["+ NBR >= .10, BSI rise >= .05"] = o["+ NBR window fall >= .10"] | (wood & (w.wb >= .05))
    o["+ NBR >= .10, BSI rise >= .03"] = o["+ NBR window fall >= .10"] | (wood & (w.wb >= .03))
    o["+ NBR >= .05, BSI rise >= .03"] = base | (wood & ((w.wr >= .05) | (w.wb >= .03)))
    o["+ NBR >= .05, NDVI >= .05, BSI >= .02"] = base | (wood & ((w.wr >= .05) | (w.wn >= .05) | (w.wb >= .02)))
    o["+ the same, any woody"] = base | ((woa >= .15) & ((w.wr >= .05) | (w.wn >= .05) | (w.wb >= .02)))
    o["reference: rolling added (needs yearly data)"] = base | (rolling(p, .12, .08)) | (wood & (w.wr >= .10)) | (wood & (w.wb >= .05))
    return {k: (v & nw).values for k, v in o.items()}


def data():
    p = load()
    L = labels().set_index("pid")
    L = L[L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    return p, L, pd.Series(np.arange(len(L)), index=L.index)[p.pid].values


def net():
    p, L, pi = data()
    w, sf = windows(p), series_feats(p)
    y, wt = L.y.values.astype(float), L.eval_w.values.astype(float)
    ref, rnd = (L.set == "blind_reference").values, (L.set == "random300").values
    state = L.set.isin(["round1", "round2"]).values & L.zone.isin(DEC).values
    rd = rnd & L.zone.isin(DEC).values
    rows = []
    for nm, m in nets(p, w, sf).items():
        f = np.bincount(pi, weights=m, minlength=len(L)) >= 1
        a, b = wpr(y[ref], f[ref].astype(int), wt[ref])
        s = pr(f[None, state], y[state], wt[state])
        d = dict(net=nm, guna_recall=round(b, 3), guna_precision=round(a, 3), guna=f"{int((f & ref & (y == 1)).sum())}/{int(y[ref].sum())}", background=f"{int((f[ref] & (L.stratum.values[ref] == 'background') & (y[ref] == 1)).sum())}/6", statewide_recall=round(float(s[1][0]), 3), statewide_precision=round(float(s[0][0]), 3), random_pct=round(100 * f[rnd].mean(), 1), random_deciduous_pct=round(100 * f[rd].mean(), 1), n_rd=int(rd.sum()), px_pct=round(100 * pd.Series(m).groupby(p.pid.values).mean().reindex(L.index[rnd]).mean(), 1))
        for sn, lab in (("bamori_validated", "bamori"), ("felling_alert_verdict", "fellings")):
            q = (L.set == sn).values & (y == 1)
            d[lab] = f"{int(f[q].sum())}/{int(q.sum())}"
        rows.append(d)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(t.to_string())
    t.to_csv(REPORT / "net90_ladder.csv", index=False)


def filt(net_name="+ NBR >= .10, BSI rise >= .03"):
    p, L, pi = data()
    w, sf = windows(p), series_feats(p)
    m = nets(p, w, sf)[net_name]
    keep = L.set.isin(["blind_reference", "round1", "round2"]).values & (L.zone.isin(DEC).values | (L.set == "blind_reference").values)
    y, wt, g = L.y.values.astype(float), L.eval_w.values.astype(float), L.group.values
    FG = list(product(("window", "break"), (0, .05, .1, .15, .2, .25), (0, .05, .1, .15, .2, .25), (0, 2), (1, 2, 3, 5, 9, 13, 25)))
    flags = []
    for kind, fn, fr, ps, n in FG:
        a, b = (w.wn.values, w.wr.values) if kind == "window" else (sf.drop_n.values, sf.drop_r.values)
        k = m & (a >= fn if fn else True) & (b >= fr if fr else True) & (sf.persist.values >= ps if ps else True)
        flags.append(np.bincount(pi, weights=k, minlength=len(L)) >= n)
    F = np.array(flags, bool)
    C = pd.DataFrame(FG, columns=["fall_type", "ndvi_fall", "nbr_fall", "seasons", "npix"])
    guna, state = (L.set == "blind_reference").values, L.set.isin(["round1", "round2"]).values & L.zone.isin(DEC).values
    for kind in ("window", "break"):
        k = (C.fall_type == kind).values
        pp, rr = pr(F[k][:, guna], y[guna], wt[guna])
        print(kind, "in-sample Guna best precision at recall >=", {t: round(float(pp[rr >= t].max()), 3) if (rr >= t).any() else None for t in (.5, .6, .7, .8, .9)})
    res, picks = [], []
    strat = np.where(guna, 0, 1) * 2 + y
    idx = np.flatnonzero(keep)
    for tg in (.5, .6, .7, .8, .9):
        for kind in ("window", "break"):
            k = np.flatnonzero((C.fall_type == kind).values)
            oof = np.zeros((3, len(L)), bool)
            for rep in range(3):
                for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=rep).split(idx[:, None], strat[idx], g[idx]):
                    tr, te = idx[tr], idx[te]
                    mk = np.intersect1d(tr, np.flatnonzero(guna))
                    pp, rr = pr(F[k][:, mk], y[mk], wt[mk])
                    v = np.where(rr >= tg, pp, -1)
                    i = k[int(np.argmax(v))]
                    picks.append(dict(target=tg, **C.iloc[i].to_dict()))
                    oof[rep, te] = F[i, te]
            for sn, q in (("Guna", guna), ("Statewide deciduous", state)):
                a, b = pr(oof[:, q], y[q], wt[q])
                r = boot(y[q], wt[q], oof.mean(axis=0)[q] >= .5, g[q])
                res.append(dict(target_recall=tg, fall_type=kind, points=sn, precision=round(float(a.mean()), 3), p_range=r[0], recall=round(float(b.mean()), 3), r_range=r[1]))
    t = pd.DataFrame(res)
    print(t.to_string())
    t.to_csv(REPORT / "net90_filter_heldout.csv", index=False)
    print(pd.DataFrame(picks).groupby(["target", "fall_type"]).agg(lambda s: s.value_counts().index[0]).to_string())
    for lab, c in (("window .15/.15, 5 px", ("window", .15, .15, 0, 5)), ("window .2/.15 5 px", ("window", .2, .15, 0, 5)), ("window .1/.1, 13 px", ("window", .1, .1, 0, 13)), ("break .2/.15, 5 px", ("break", .2, .15, 0, 5))):
        i = FG.index(c)
        for sn, q in (("Guna", guna), ("Statewide deciduous", state)):
            a, b = pr(F[i][None, q], y[q], wt[q])
            print(lab, sn, round(float(a[0]), 3), round(float(b[0]), 3))


def size():
    b = gpd.read_file("E:/e_Netra/outputs/bamori_alphaearth_v2/FINAL_LABELS/bamori_validated_change_2017_2024.geojson")
    f = gpd.read_file("E:/e_Netra/outputs/local_detector/felling_kit/felling_alerts_tiered.geojson").to_crs(PROJ4)
    f = f[f.verdict == "TP"]
    fa = f.geometry.area / 1e4
    print("Bamori under .5 ha", int((b.area_ha < .5).sum()), "of", len(b), "median", round(b.area_ha.median(), 2))
    print("fellings under .5 ha", int((fa < .5).sum()), "of", len(fa), "median", round(fa.median(), 2), fa.quantile([.1, .25, .75]).round(2).to_dict())
    # owner's reference points have no polygons: the size of the old-map patch at each caught point is the best available estimate
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    q = g[(g.source == "blind_reference") & (g.label == 1)]
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    out = []
    for z in q.itertuples():
        s = t[(t.x0 <= z.x) & (t.x0 + t.w * RES > z.x) & (t.y1 >= z.y) & (t.y1 - t.h * RES < z.y)]
        if s.empty:
            continue
        s = s.iloc[0]
        r, c = int((s.y1 - z.y) // 10), int((z.x - s.x0) // 10)
        p = WORK / "map10m" / f"{s.tile}_{r // 900 * 900:05d}_{c // 900 * 900:05d}.npz"
        if not p.exists():
            continue
        a = np.load(p)["cls"] > 0
        lab, _ = ndimage.label(a, structure=np.ones((3, 3), bool))
        rr, cc = r % 900, c % 900
        box = lab[max(rr - 2, 0):rr + 3, max(cc - 2, 0):cc + 3]
        ids = box[box > 0]
        out.append(dict(pid=z.pid, stratum=z.stratum, w=(13 if z.stratum == "flagged" else 72), ha=(np.bincount(lab.ravel())[np.unique(ids)].max() * .01 if len(ids) else 0)))
    d = pd.DataFrame(out)
    print("Guna losses with a chunk", len(d), "not on the old map", int((d.ha == 0).sum()), "on the map under .5 ha", int(((d.ha > 0) & (d.ha < .5)).sum()), "at least .5 ha", int((d.ha >= .5).sum()))
    print("patch size at caught points", d[d.ha > 0].ha.describe().round(2).to_dict())
    print(d[d.stratum == "background"].to_string())


if __name__ == "__main__":
    {"net": net, "filter": filt, "size": size}[sys.argv[1]]()
