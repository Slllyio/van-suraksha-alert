"""Tune map rules on the owner's Guna reference and test on held-out beats, held-out ranges, and round-2 random points.
Round-2 points are not used for tuning. Usage: e25_guna_tune.py [version]"""
import itertools
import json
import sys

import numpy as np
import pandas as pd
import rasterio

import e8_classify as E
from common import *
from e23_guna_labels import A_H, cluster_ci, flag, wpr
from e14_accuracy import boot, metrics
from zones import zone as zone_of

GT = ROOT / "ground_truth"
Z = [-1.6, -1.4, -1.2, -1.0, -0.8, -0.6, -0.4, -0.2]
DROP = [0.08, 0.10, 0.12, 0.15, 0.20]
PX = [3, 6, 12, 25]
PAD = 200
BASE = dict(grow_px=2, small_z=99, small_tree_drop=9, small_min_px=6, clear_post_tree=.3, clear_tree_drop=.25, rec_fraction=.5)


def rule(z, d, px):
    return dict(BASE, core_z=z, core_tree_drop=d, core_min_px=px, grow_z=z - .4, grow_tree_drop=max(d - .05, .05))


def main_mask(A, zone, th, win=None):
    w = win or (slice(None), slice(None))
    _, cls, _ = E.decide(A["score"][w], A["yod"][w], A["pre"][w], A["post"][w], A["rec"][w], zone[w], th)
    return cls > 0


def weighted_ref(d):
    n = d.stratum.value_counts()
    return d.assign(_w=d.stratum.map(lambda s: A_H[s] / n[s]))


def evaluate(ref, m, tag, out):
    d = ref.assign(m=flag(ref, m, 1))
    d = weighted_ref(d)
    p, r = wpr(d.label.values, d.m.values.astype(int), d._w.values)
    ci = cluster_ci(d, "m")
    print(f"{tag:46s} n {len(d)} real {int(d.label.sum())}  precision {p:.2f} {ci[0]}  recall {r:.2f} {ci[1]}", flush=True)
    out.append(dict(test=tag, n=len(d), real=int(d.label.sum()), precision=round(p, 3), p_ci=ci[0], recall=round(r, 3), r_ci=ci[1]))


def r2_eval(mapped, tag, out, area):
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id")
    k["real"] = k.label.isin(list("LD")).astype(int)
    k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
    k["m"] = mapped[k.row, k.col].astype(int)
    k["forest_zone"] = k.Division.map(zone_of)
    groups = [("ALL", k), ("deciduous", k[k.forest_zone.isin(["teak_belt", "mixed_dry_deciduous"])])] + [(z, g) for z, g in k.groupby("forest_zone")]
    for g, q in groups:
        p, r, f = metrics(q.real.values, q.m.values, q._w.values)
        lo, hi = boot(q, area, "real", "m") if q.real.sum() else ((np.nan,) * 3, (np.nan,) * 3)
        area_ha = float((q.m * q._w).sum())
        print(f"{tag:30s} R2 {g:30s} n {len(q):3d} real {int(q.real.sum()):2d} P {p:.2f} [{lo[0]:.2f},{hi[0]:.2f}] R {r:.2f} [{lo[1]:.2f},{hi[1]:.2f}] flagged_ha {area_ha:9.0f}", flush=True)
        out.append(dict(test=f"round2 {g} | {tag}", n=len(q), real=int(q.real.sum()), precision=round(p, 3), p_ci=[round(lo[0], 3), round(hi[0], 3)], recall=round(r, 3), r_ci=[round(lo[1], 3), round(hi[1], 3)], flagged_ha=round(area_ha)))


def tune(ref, A, zone, win, rr0, cc0):
    """Best rule by weighted F1 on these reference points; masks are cached by the caller."""
    best = (-1, None, None)
    rows = []
    for z, d, px in itertools.product(Z, DROP, PX):
        m = main_mask(A, zone, rule(z, d, px), win)
        q = ref.assign(row=ref.row - rr0, col=ref.col - cc0)
        q = weighted_ref(q.assign(m=flag(q, m, 1)))
        p, r = wpr(q.label.values, q.m.values.astype(int), q._w.values)
        f = 2 * p * r / (p + r) if p == p and r == r and p + r else 0
        rows.append(dict(z=z, drop=d, px=px, p=p, r=r, f1=f))
        if f > best[0]:
            best = (f, (z, d, px), m)
    return best, pd.DataFrame(rows)


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else "v3"
    df = pd.read_csv(GT / "guna_labels.csv")
    ref = df[df.source == "blind_reference"].reset_index(drop=True)
    g, A, missing = E.load_state(ver)
    water = np.load(WORK / "water.npy")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    zone = np.where(water, 0, zb)
    rr = slice(int(df.row.min()) - PAD, int(df.row.max()) + PAD)
    cc = slice(int(df.col.min()) - PAD, int(df.col.max()) + PAD)
    win = (rr, cc)
    out = []
    beats = np.sort(ref.beat.unique())
    rng = np.random.default_rng(42)
    rng.shuffle(beats)
    half = set(beats[: len(beats) // 2])
    tr, te = ref[ref.beat.isin(half)], ref[~ref.beat.isin(half)]
    print("beats", len(beats), "train pts", len(tr), "real", int(tr.label.sum()), "test pts", len(te), "real", int(te.label.sum()), flush=True)
    (f1, best, _), grid = tune(tr, A, zone, win, rr.start, cc.start)
    grid.to_csv(GT / f"guna_rule_grid_{ver}.csv", index=False)
    print("best rule on train beats (z, drop, px)", best, "F1", round(f1, 3), flush=True)
    print(grid.sort_values("f1", ascending=False).head(6).round(3).to_string(index=False), flush=True)
    win_te = te.assign(row=te.row - rr.start, col=te.col - cc.start)
    m = main_mask(A, zone, rule(*best), win)
    evaluate(win_te, m, "held-out beats, tuned on the other half", out)
    # reverse direction, so every beat is tested once
    (_, best2, _), _ = tune(te, A, zone, win, rr.start, cc.start)
    win_tr = tr.assign(row=tr.row - rr.start, col=tr.col - cc.start)
    evaluate(win_tr, main_mask(A, zone, rule(*best2), win), f"reverse split, rule {best2}", out)
    # leave-range-out with a smaller grid is omitted: only 8 ranges with few real points each
    (_, final, _), _ = tune(ref, A, zone, win, rr.start, cc.start)
    print("final Guna rule on all 284", final, flush=True)
    th = rule(*final)
    state = main_mask(A, zone, th)
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    r2_eval(state, f"Guna rule everywhere {final}", out, area)
    b = pd.read_csv(OUT / "beat_lookup.csv")
    b["z"] = b.Division.map(zone_of)
    zmap = np.zeros(int(b.zone_id.max()) + 1, "uint8")
    zmap[b.zone_id.values] = b.z.isin(["mixed_dry_deciduous"]).astype(int).values
    c = np.load(WORK / "classified.npz")
    old = (c["cls"] == 1) | (c["cls"] == 2)
    hybrid = np.where(zmap[zb] == 1, state, old)
    r2_eval(hybrid, "Guna rule in mixed dry only", out, area)
    r2_eval(old, "current map", out, area)
    print("mapped ha: current", round(old.sum() * PX_HA), "Guna rule everywhere", round(state.sum() * PX_HA), "mixed dry only", round(hybrid.sum() * PX_HA), "Guna division", round(state[np.isin(zb, b[b.Division == "Guna"].zone_id.values)].sum() * PX_HA))
    pd.DataFrame(out).to_csv(GT / f"guna_tune_results_{ver}.csv", index=False)
    json.dump(dict(rule=final, th=th), open(GT / f"guna_rule_{ver}.json", "w"))
    np.save(WORK / f"guna_state_{ver}.npy", state)


if __name__ == "__main__":
    main()
