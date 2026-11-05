"""Offline tests on the 50 m pixel table from e47_px.py, no Earth Engine. Usage: e48_tests.py check | s2f"""
import json
import sys
from itertools import product

import numpy as np
import pandas as pd

from common import *
from e23_guna_labels import A_H, cluster_ci, wpr
from e32_enetra10m import FOREST_MIN, TREE_DROP, NDVI_DROP, RECENT_DROP, WOODY_MIN, CROP_RISE
from e46_s2f import RAND

F = WORK / "s2f_px.jsonl"
GT = ROOT / "ground_truth"
YS = list(range(2017, 2026))
SEED = 20261105


def load():
    """Long table, one row per pixel of each box; -9 becomes NaN."""
    rows = []
    for l in open(F):
        r = json.loads(l)
        pid = r.pop("pid")
        n = max(len(v) for v in r.values())
        if n == 0 or any(len(v) != n for v in r.values()):
            continue
        d = pd.DataFrame(r)
        d.insert(0, "pid", pid)
        rows.append(d)
    return pd.concat(rows, ignore_index=True).replace(-9, np.nan)


def rule(p):
    """The running rule at pixel level: class flags exactly as on the map."""
    nda, ndb = p.nea - p.nla, p.neb - p.nlb
    cur = (p.ea_t >= FOREST_MIN) & (p.ea_t - p.la_t >= TREE_DROP) & (nda >= NDVI_DROP)
    a = cur | ((p.ea_t >= FOREST_MIN) & (nda >= NDVI_DROP) & (p.mon0 - p.mon24 >= RECENT_DROP))
    b = (p.eb_t >= FOREST_MIN) & (p.eb_t - p.lb_t >= TREE_DROP) & (ndb >= NDVI_DROP)
    s_a = (p.ea_t + p.ea_s >= WOODY_MIN) & (p.ea_t < FOREST_MIN) & (p.la_c - p.ea_c >= CROP_RISE) & (nda >= NDVI_DROP)
    s_b = (p.eb_t + p.eb_s >= WOODY_MIN) & (p.eb_t < FOREST_MIN) & (p.lb_c - p.eb_c >= CROP_RISE) & (ndb >= NDVI_DROP)
    return (a | b | s_a | s_b) & (p.water < 5), a, b, s_a | s_b


def cycle(p, amp, rabi):
    """Crop cycle per year: rabi green and well above the dry-season floor. NaN years count as no cycle here and are tracked separately."""
    return pd.DataFrame({y: (p[f"r{y}"] - p[f"d{y}"] >= amp) & (p[f"r{y}"] >= rabi) for y in YS})


def s2f_flags(p, floor, amp, rabi, k):
    c = cycle(p, amp, rabi)
    was_open = (p.ea_t < FOREST_MIN) & (p.ea_t + p.ea_s >= floor)
    none_early = ~c[[2017, 2018, 2019]].any(axis=1)
    v = c[[2020, 2021, 2022, 2023, 2024, 2025]].values.astype(int)
    run = np.zeros(len(p), int)
    best = np.zeros(len(p), int)
    for j in range(v.shape[1]):
        run = (run + 1) * v[:, j]
        best = np.maximum(best, run)
    return was_open & none_early & (best >= k) & (p.water < 5)


def by_point(p, m, min_px):
    return m.groupby(p.pid).sum().ge(min_px)


def split(beats):
    b = sorted(set(beats))
    rng = np.random.default_rng(SEED)
    rng.shuffle(b)
    return set(b[: len(b) // 2])


GRID = list(product((.1, .2, .3, .4), (.1, .15, .2, .25, .3), (.3, .35, .4, .45), (2, 3), (1, 5, 13)))
MAX_FA = .01


def s2f():
    p = load()
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    pos = g[(g.source == "bamori_validated") & g.cls.isin(["shrub_to_crop", "bare_to_crop", "forest_to_crop"])]
    neg = g[(g.source == "blind_reference") & (g.label == 0)]
    have = set(p.pid)
    pos, neg = pos[pos.pid.isin(have)], neg[neg.pid.isin(have)]
    print("Bamori polygons", len(pos), "beats", pos.beat.nunique(), "| Guna no-loss", len(neg), "beats", neg.beat.nunique(), flush=True)
    tab = {}
    for gp in GRID:
        floor, amp, rabi, k, mp = gp
        key = (floor, amp, rabi, k)
        if key not in tab:
            tab[key] = s2f_flags(p, floor, amp, rabi, k)
    pa, na = split(pos.beat), split(neg.beat)
    folds = [("A", pos[pos.beat.isin(pa)], pos[~pos.beat.isin(pa)], neg[neg.beat.isin(na)], neg[~neg.beat.isin(na)]),
             ("B", pos[~pos.beat.isin(pa)], pos[pos.beat.isin(pa)], neg[~neg.beat.isin(na)], neg[neg.beat.isin(na)])]
    res, chosen = [], []
    for name, ptr, pte, ntr, nte in folds:
        best = None
        for gp in GRID:
            f = by_point(p, tab[gp[:4]], gp[4])
            rec = f.reindex(ptr.pid).fillna(False).mean()
            fa = f.reindex(ntr.pid).fillna(False).mean()
            if fa <= MAX_FA and (best is None or rec > best[0]):
                best = (rec, fa, gp)
        rec, fa, gp = best
        f = by_point(p, tab[gp[:4]], gp[4])
        hp = f.reindex(pte.pid).fillna(False)
        hn = f.reindex(nte.pid).fillna(False)
        row = dict(fold=name, floor=gp[0], amp=gp[1], rabi=gp[2], seasons=gp[3], min_px=gp[4], train_recall=round(rec, 3), train_false=round(fa, 3), test_caught=int(hp.sum()), test_polygons=len(pte), test_recall=round(hp.mean(), 3), test_false=int(hn.sum()), test_noloss=len(nte))
        for c, q in pte.groupby("cls"):
            row[c] = f"{int(hp.reindex(q.pid).sum())}/{len(q)}"
        res.append(row)
        chosen.append(gp)
    r = pd.DataFrame(res)
    print(r.T.to_string())
    r.to_csv(OUT / "interim" / "report" / "s2f_clean_test.csv", index=False)
    json.dump(dict(chosen=[list(c) for c in chosen]), open(WORK / "s2f_chosen.json", "w"))
    # how the existing classes do on the same polygons, for comparison
    fl, a, b, s = rule(p)
    old = by_point(p, fl, 1)
    print("running rule on the same polygons:", int(old.reindex(pos.pid).fillna(False).sum()), "of", len(pos), "| no-loss flagged", int(old.reindex(neg.pid).fillna(False).sum()), "of", len(neg))
    print(pos.assign(hit=old.reindex(pos.pid).fillna(False).values).groupby("cls").hit.agg(["sum", "size"]).to_string())


def check():
    """The pixel table must reproduce the flags stored at the same points by the run's own rule."""
    p = load()
    fl, a, b, s = rule(p)
    t = pd.read_csv(GT / "enetra10m_points.csv").set_index("pid")
    o = pd.DataFrame(dict(mine=by_point(p, fl, 1))).join(t, how="inner")
    st = (o[["e_recent", "late", "s2c_a", "s2c_b"]].fillna(0).max(axis=1) > 0) & (o.water.fillna(0) == 0)
    print("points", len(o), "agree", int((o.mine == st).sum()), "mine only", int((o.mine & ~st).sum()), "stored only", int((~o.mine & st).sum()))


if __name__ == "__main__":
    {"check": check, "s2f": s2f}[sys.argv[1]]()
