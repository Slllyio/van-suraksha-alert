"""Miss analysis, time-series precision filter and recall levers on the Guna reference, from the pixel table. No Earth Engine.
Filter thresholds are tuned on half the beats and scored on the other half, then swapped. Usage: e49_ts.py miss | filter | levers"""
import json
import sys
from itertools import product

import numpy as np
import pandas as pd

from common import *
from e23_guna_labels import A_H, cluster_ci, wpr
from e32_enetra10m import FOREST_MIN, NDVI_DROP, TREE_DROP, WOODY_MIN
from e48_tests import GT, YS, by_point, load, rule, s2f_flags, split

MARGIN = .05
REPORT = OUT / "interim" / "report"
FG = list(product((0, .03, .05, .08, .1, .15), (0, .05, .1, .15), (0, 1, 2, 3), (9, .1, .07, .05)))


def series_feats(p):
    """Per pixel, from yearly leaf-on values: best single downward break (two-level fit on NDVI), drop in NDVI and NBR, seasons staying low, scatter before it."""
    n = p[[f"ln{y}" for y in YS]].values
    r = p[[f"lr{y}" for y in YS]].values
    best, brk = np.full(len(p), np.inf), np.zeros(len(p), int)
    with np.errstate(all="ignore"):
        for k in range(2, len(YS) - 1):          # post segment starts at YS[k]; at least 2 seasons before and 2 after
            a, b = n[:, :k], n[:, k:]
            sse = np.nansum((a - np.nanmean(a, axis=1, keepdims=True)) ** 2, axis=1) + np.nansum((b - np.nanmean(b, axis=1, keepdims=True)) ** 2, axis=1)
            sse = np.where(np.nanmean(a, axis=1) > np.nanmean(b, axis=1), sse, np.inf)
            u = sse < best
            best, brk = np.where(u, sse, best), np.where(u, k, brk)
        out = {k: np.full(len(p), np.nan) for k in ("drop_n", "drop_r", "pre_sd")}
        out["persist"], out["back"] = np.zeros(len(p), int), np.zeros(len(p), bool)
        for k in np.unique(brk[np.isfinite(best)]):
            i = np.flatnonzero((brk == k) & np.isfinite(best))
            pre, post = n[i, :k], n[i, k:]
            lev = np.nanmean(pre, axis=1)
            out["drop_n"][i] = lev - np.nanmean(post, axis=1)
            out["drop_r"][i] = np.nanmean(r[i, :k], axis=1) - np.nanmean(r[i, k:], axis=1)
            out["pre_sd"][i] = np.nanstd(pre, axis=1)
            low = post < (lev - MARGIN)[:, None]
            out["persist"][i] = np.where(low.all(axis=1), low.shape[1], (~low).argmax(axis=1))
            out["back"][i] = post[:, -1] >= lev - MARGIN / 2
    out["break_year"] = np.where(np.isfinite(best), np.array(YS)[brk], 0)
    return pd.DataFrame(out, index=p.index)


def guna_ref(have):
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    r = g[(g.source == "blind_reference") & g.pid.isin(have)].copy()
    n = r.stratum.value_counts()
    r["_w"] = r.stratum.map(lambda s: A_H[s] / n[s])
    return r.set_index("pid", drop=False)


def score_ref(r, m, name):
    r = r.assign(m=m.reindex(r.pid).fillna(False).astype(int).values)
    pr, re = wpr(r.label.values, r.m.values, r._w.values)
    ci = cluster_ci(r, "m")
    return dict(variant=name, flagged=int(r.m.sum()), real=int((r.m & r.label).sum()), false=int((r.m & (1 - r.label)).sum()), precision=round(pr, 3), p_ci=ci[0], recall=round(re, 3), r_ci=ci[1])


def ts_pass(sf, g):
    dn, dr, ps, sd = g
    return (sf.drop_n >= dn) & (sf.drop_r >= dr) & (sf.persist >= ps) & (sf.pre_sd <= sd)


def rolling(p, td, nd):
    """Forest before, then trees and leaf-on NDVI both fall between neighbouring 2-year pairs anywhere in 2017-25."""
    out = np.zeros(len(p), bool)
    for y in YS[:-3]:
        t0, t1 = p[[f"t{y}", f"t{y + 1}"]].mean(axis=1), p[[f"t{y + 2}", f"t{y + 3}"]].mean(axis=1)
        n0, n1 = p[[f"ln{y}", f"ln{y + 1}"]].mean(axis=1), p[[f"ln{y + 2}", f"ln{y + 3}"]].mean(axis=1)
        out |= ((t0 >= FOREST_MIN) & (t0 - t1 >= td) & (n0 - n1 >= nd)).values
    return pd.Series(out, index=p.index)


def held_out(p, r, m, sf, min_px=(1,)):
    """Thresholds chosen on half the beats: best precision with recall within 5 points of that half's unfiltered recall. Scored on the other half, then swapped."""
    a = split(r.beat)
    hold, picks = pd.Series(False, index=r.pid), []
    for tr, te in ((r[r.beat.isin(a)], r[~r.beat.isin(a)]), (r[~r.beat.isin(a)], r[r.beat.isin(a)])):
        base = wpr(tr.label.values, by_point(p, m, 1).reindex(tr.pid).fillna(False).astype(int).values, tr._w.values)
        best = None
        for g in FG:
            ok = m & ts_pass(sf, g)
            for mp in min_px:
                f = by_point(p, ok, mp).reindex(tr.pid).fillna(False).astype(int).values
                if f.sum():
                    pr, re = wpr(tr.label.values, f, tr._w.values)
                    if re >= base[1] - .05 and (best is None or pr > best[0]):
                        best = (pr, g, mp)
        picks.append(best[1:])
        hold[te.pid] = by_point(p, m & ts_pass(sf, best[1]), best[2]).reindex(te.pid).fillna(False).values
    return hold, picks


def filt():
    p = load()
    r = guna_ref(set(p.pid))
    p = p[p.pid.isin(r.pid)].reset_index(drop=True)
    fl = rule(p)[0]
    sf = series_feats(p)
    res = [score_ref(r, by_point(p, fl, 1), "rule as mapped")]
    hold, picks = held_out(p, r, fl, sf)
    res.append(score_ref(r, hold, "tuned filter, held out"))
    for name, g in (("seasons low >=1", (0, 0, 1, 9)), ("seasons low >=2", (0, 0, 2, 9)), ("seasons low >=3", (0, 0, 3, 9)), ("drop >=.05, seasons >=2", (.05, 0, 2, 9)), ("drop >=.08, seasons >=2", (.08, 0, 2, 9)), ("drop >=.10, seasons >=2", (.1, 0, 2, 9)), ("seasons >=2, stable before", (0, 0, 2, .07))):
        res.append(score_ref(r, by_point(p, fl & ts_pass(sf, g), 1), name + " (fixed)"))
    t = pd.DataFrame(res)
    print(t.to_string())
    print("thresholds per half ((drop_ndvi, drop_nbr, seasons, max_sd), min_px)", picks)
    t.to_csv(REPORT / "ts_precision_filter.csv", index=False)


def miss():
    """Why each real loss is missed, judged across the 50 m box."""
    p = load()
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    hit = by_point(p, rule(p)[0], 1)
    sets = [("Guna reference losses", g[(g.source == "blind_reference") & (g.label == 1)]), ("Bamori polygons", g[g.source == "bamori_validated"])]
    roll = rolling(p, TREE_DROP, NDVI_DROP)
    near_t, near_n = TREE_DROP - .04, NDVI_DROP - .03
    cls = g.set_index("pid").cls
    out = []
    for name, q in sets:
        for pid in q.pid[q.pid.isin(p.pid)]:
            if hit.get(pid, False):
                continue
            i = p.pid == pid
            x = p[i]
            ft = np.maximum(x.ea_t, x.eb_t) >= FOREST_MIN
            dt = np.maximum(x.ea_t - x.la_t, x.eb_t - x.lb_t)
            dn = np.maximum(x.nea - x.nla, x.neb - x.nlb)
            if (x.water >= 5).all():
                why = "e water mask"
            elif not ft.any():
                why = "g open before: trees under 0.30, woody at least 0.40" if (x.ea_t + x.ea_s >= WOODY_MIN).any() else "a trees under 0.30, woody under 0.40"
            elif roll[i].any():
                why = "d passes in another 2-year pair, fixed periods miss it"
            elif ((dt >= TREE_DROP) & ft).any():
                why = "c tree drop ok, NDVI drop under 0.08"
            elif ((dn >= NDVI_DROP) & ft).any():
                why = "b NDVI drop ok, tree drop under 0.12"
            elif ((dt >= near_t) & (dn >= near_n) & ft).any():
                why = "f near miss on both, small or mixed pixel possible"
            else:
                why = "h forest, no drop in either signal"
            out.append(dict(set=name, pid=pid, cls=cls[pid], why=why))
    m = pd.DataFrame(out)
    m.to_csv(REPORT / "miss_reasons_points.csv", index=False)
    t = m.groupby(["set", "why"]).size().rename("n").reset_index()
    print(t.to_string())
    t.to_csv(REPORT / "miss_reasons.csv", index=False)
    print(pd.crosstab(m.cls, m.why).to_string())
    print("hits and totals", {n: (int(hit.reindex(q.pid).fillna(False).sum()), int(q.pid.isin(p.pid).sum())) for n, q in sets})


def levers():
    p = load()
    r = guna_ref(set(p.pid))
    p = p[p.pid.isin(r.pid)].reset_index(drop=True)
    fl = rule(p)[0]
    sf = series_feats(p)
    nda, ndb, nw = p.nea - p.nla, p.neb - p.nlb, p.water < 5

    def td(x):
        return (((p.ea_t >= FOREST_MIN) & (p.ea_t - p.la_t >= x) & (nda >= NDVI_DROP)) | ((p.eb_t >= FOREST_MIN) & (p.eb_t - p.lb_t >= x) & (ndb >= NDVI_DROP))) & nw
    wood = (((p.ea_t + p.ea_s >= WOODY_MIN) & (p.ea_t - p.la_t >= TREE_DROP) & (nda >= NDVI_DROP)) | ((p.eb_t + p.eb_s >= WOODY_MIN) & (p.eb_t - p.lb_t >= TREE_DROP) & (ndb >= NDVI_DROP))) & nw
    forest = (p.ea_t >= FOREST_MIN) | (p.eb_t >= FOREST_MIN)
    bsi = forest & (p[["lb2023", "lb2024"]].mean(axis=1) - p[["lb2018", "lb2019"]].mean(axis=1) >= .05) & nw
    nbr = forest & (sf.drop_r >= .15) & nw
    roll = rolling(p, TREE_DROP, NDVI_DROP) & nw
    s2 = s2f_flags(p, *json.load(open(WORK / "s2f_chosen.json"))["chosen"][0][:4])
    lv = {"rule as mapped": fl, "woody >=0.40 instead of trees >=0.30": fl | wood, "tree drop 0.10": fl | td(.10), "tree drop 0.08": fl | td(.08), "rolling 2-year pairs": fl | roll,
          "BSI rise trigger": fl | bsi, "NBR drop trigger": fl | nbr, "scrub-to-farm class": fl | s2, "all together": fl | wood | td(.08) | roll | bsi | nbr | s2}
    rows = []
    for name, m in lv.items():
        rows.append(score_ref(r, by_point(p, m, 1), name))
        rows.append(score_ref(r, held_out(p, r, m, sf, (1, 3, 5))[0], name + " + filter, held out"))
        print(rows[-2:], flush=True)
    t = pd.DataFrame(rows)
    print(t.to_string())
    t.to_csv(REPORT / "recall_levers.csv", index=False)


if __name__ == "__main__":
    {"miss": miss, "filter": filt, "levers": levers}[sys.argv[1]]()
