"""Two ways of detecting loss: sudden, and small or gradual. Each reference point gets a shape (does a one-time step or a slow ramp fit its strongest pixels better) and a size
(largest patch of yearly-break pixels touching the 50 m box). Each kind then gets its own detector, with bars set as percentiles of random forest land so no label sets them:
  sudden    = patch of yearly-break pixels of at least 0.5 ha
  small     = strongest pixel of the box above the bar, no patch needed
  gradual   = straight-line trend or start-to-end change above the bar where the yearly break is not
Reports what each detector catches of each kind of loss, and the false alarms it raises. Offline. Usage: e102_cc_twoway.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
sys.argv = [sys.argv[0], "logistic", "10"]

import numpy as np
import pandas as pd

from e23_guna_labels import wpr
from e76_cc_train import REPORT, WORK, YS, load, ref_w
from e101_cc_cumtest import grids, patch_ha

warnings.filterwarnings("ignore")
T = len(YS)


def shapes(d, A):
    """Step vs ramp at the 5 pixels of each box that a step explains best."""
    r = A[(d.set == "random").values].mean(axis=0)
    sh = r - r.mean(axis=0)
    pos = {c: i for i, c in enumerate(d.cid)}
    tc = np.arange(T) - (T - 1) / 2
    out = np.full((len(d), 2), np.nan)
    for l in open(WORK / "cc_emb_px.jsonl"):
        q = json.loads(l)
        i = pos.get(q.pop("cid"))
        if i is None:
            continue
        X = np.array([[q[f"y{y}_{b:02d}"] for b in range(64)] for y in YS], "float64").transpose(2, 0, 1)
        X = X / np.linalg.norm(X, axis=2, keepdims=True) - sh
        tot = ((X - X.mean(1, keepdims=True)) ** 2).sum((1, 2))
        best = np.full(len(X), np.inf)
        for b in range(1, T):
            best = np.minimum(best, ((X[:, :b] - X[:, :b].mean(1, keepdims=True)) ** 2).sum((1, 2)) + ((X[:, b:] - X[:, b:].mean(1, keepdims=True)) ** 2).sum((1, 2)))
        slope = (X * tc[None, :, None]).sum(1) / (tc ** 2).sum()
        line = ((X - X.mean(1, keepdims=True) - slope[:, None, :] * tc[None, :, None]) ** 2).sum((1, 2))
        k = np.argsort(best / tot)[:5]
        out[i] = np.median(1 - best[k] / tot[k]), np.median(1 - line[k] / tot[k])
    return out


def main():
    d, A = load()
    n = len(d)
    G = grids(d)
    S = shapes(d, A)
    rnd = (d.set == "random").values
    bar = {}
    for s in ("t", "tr", "e3"):
        allv = np.concatenate([G[i][s][np.isfinite(G[i][s])] for i in np.flatnonzero(rnd)])
        bar[s] = {p: np.percentile(allv, p) for p in (90, 95)}
    bk = lambda s: "box_t" if s == "t" else "box_c"
    boxmax = {s: np.array([np.nanmax(G[i][s][G[i][bk(s)]]) for i in range(n)]) for s in ("t", "tr", "e3")}
    patch = {s: np.array([patch_ha(G[i][s], G[i][bk(s)], bar[s][90]) for i in range(n)]) for s in ("t", "tr", "e3")}
    rb = {s: np.percentile(boxmax[s][rnd], 95) for s in boxmax}          # bar for a single box: top 5% of random boxes
    det = {"sudden: yearly-break patch of 0.5 ha or more": patch["t"] >= .5,
           "small: strong yearly break in the box, no patch needed": (boxmax["t"] >= rb["t"]) & (patch["t"] < .5),
           "gradual: trend or start-to-end change, yearly break weak": ((boxmax["tr"] >= rb["tr"]) | (boxmax["e3"] >= rb["e3"])) & (boxmax["t"] < rb["t"]) & (patch["t"] < .5)}
    any_ = np.any(list(det.values()), axis=0)
    y = np.where(d.y.values == 1, 1, 0)
    w, k = ref_w(d), (d.set == "reference").values
    shape = np.where(S[:, 1] > S[:, 0], "gradual", "sudden")
    size = np.where(patch["t"] >= .5, "0.5 ha or more", "under 0.5 ha")
    kind = pd.Series(shape + ", " + size)
    L = k & (y == 1)
    rows = []
    for kd, q in kind[L].groupby(kind[L]):
        i = q.index.values
        row = dict(kind_of_loss=kd, losses=len(i), share_of_loss_by_area_pct=round(100 * w[i].sum() / w[L].sum(), 1), background=int((d.stratum.values[i] == "background").sum()))
        for nm, f in det.items():
            row[nm.split(":")[0]] = int(f[i].sum())
        row["any"] = int(any_[i].sum())
        rows.append(row)
    a = pd.DataFrame(rows)
    a.loc[len(a)] = dict(kind_of_loss="all losses", losses=int(L.sum()), share_of_loss_by_area_pct=100.0, background=6, **{nm.split(":")[0]: int(f[L].sum()) for nm, f in det.items()}, any=int(any_[L].sum()))
    a.to_csv(REPORT / "cc_twoway_losses.csv", index=False)
    pd.set_option("display.width", 260, "display.max_columns", 30)
    print(a.to_string())
    res = []
    for nm, f in list(det.items()) + [("all three together", any_), ("sudden + small", det[list(det)[0]] | det[list(det)[1]])]:
        p, r = wpr(y[k], f[k].astype(int), w[k])
        tp, fp = int((f[k] & (y[k] == 1)).sum()), int((f[k] & (y[k] == 0)).sum())
        res.append(dict(detector=nm, real=tp, false_alarms=fp, point_precision=round(tp / max(tp + fp, 1), 3), area_precision=round(p, 3), area_recall=round(r, 3), background_false=int((f & k & (d.stratum == "background").values & (y == 0)).sum()),
                        background_losses=f"{int((f & k & (d.stratum == 'background').values & (y == 1)).sum())}/6", random_flag_pct=round(100 * f[rnd].mean(), 1),
                        fellings=f"{int(f[(d.set == 'felling').values & (y == 1)].sum())}/51", bamori_conversions=f"{int(f[(d.set == 'bamori_tp').values & (d.y.values == 1)].sum())}/170", bamori_rejected=f"{int(f[(d.set == 'bamori_fp').values].sum())}/112"))
    r = pd.DataFrame(res)
    r.to_csv(REPORT / "cc_twoway_detectors.csv", index=False)
    print(r.to_string())
    print("random forest land by shape:", pd.Series(shape[rnd]).value_counts().to_dict(), "| all reference non-loss:", pd.Series(shape[k & (y == 0)]).value_counts().to_dict())
    print("missed by all three:", d.id[L & ~any_].tolist())
    out = d[["cid", "set", "id", "y", "stratum", "beat"]].assign(shape=shape, yearly_break_patch_ha=patch["t"].round(2), sudden=det[list(det)[0]], small=det[list(det)[1]], gradual=det[list(det)[2]])
    out.to_csv(REPORT / "cc_twoway_points.csv", index=False)


if __name__ == "__main__":
    main()
