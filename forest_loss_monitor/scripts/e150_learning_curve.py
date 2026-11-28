"""PREREG_LEARNING_CURVE.md: label learning curve on the 155 Bamori 2022 polygons (3 classes), cv2022 folds and test px fixed.
  subsets:        class-stratified whole-polygon subsets of each training pool, 25/50/75/100 %, seeds 0-2 at 25/50, seed 0 at 75/100.
  cpu:            LightGBM HLS 2022, AlphaEarth RF 2022, AlphaEarth MLP 2022 on every subset.
  prithvi <arm>:  b223cPT (T0 DW pre-train init) or b223c (no pre-train), e117/e121 b22 recipe; per-fold results cached, so a rerun resumes.
  table:          metrics per (model, fraction), gaps, decision rule, log2 extrapolation.
Writes outputs/final/survey_model/lc_*. Runs against the pipeline in E:/FIRE/forest_loss_monitor/scripts.
Usage: e150_learning_curve.py subsets | cpu | prithvi b223cPT|b223c | table"""
import json
import os
import sys
import time

sys.path.insert(0, r"E:\FIRE\forest_loss_monitor\scripts")
os.chdir(r"E:\FIRE\forest_loss_monitor\scripts")

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from e106_survey_data import SM
from e107_survey_states import OD, SEED
from e116_lab2022 import NF, TO3, get, load, train_px

RUNS = [(0.25, 0), (0.25, 1), (0.25, 2), (0.5, 0), (0.5, 1), (0.5, 2), (0.75, 0), (1.0, 0)]
PRITHVI_ORDER = [(1.0, 0), (0.25, 0), (0.25, 1), (0.25, 2), (0.5, 0), (0.5, 1), (0.5, 2), (0.75, 0)]   # decision-critical runs first
SUB = OD / "lc_subsets.json"
PRED = SM / "lc_pred"
LCD = OD / "lc_runs"


def poly_class():
    pid, k = load()
    cls = np.zeros(pid.max(), int)
    r, c = np.nonzero(pid)
    cls[pid[r, c] - 1] = TO3[k[r, c]]
    return cls


def key(frac, seed, f):
    return f"{frac:.2f}_s{seed}_f{f}"


def subsets():
    _, fold = get()
    cls = poly_class()
    out = {}
    for seed in (0, 1, 2):
        for f in range(NF):
            rs = np.random.default_rng(1000 * seed + f)
            perm = {c: rs.permutation(np.nonzero((fold != f) & (cls == c))[0] + 1) for c in (1, 2, 3)}
            for frac in (0.25, 0.5, 0.75, 1.0):
                if (frac, seed) in RUNS:
                    out[key(frac, seed, f)] = sorted(int(p) for c in (1, 2, 3) for p in perm[c][:max(1, round(frac * len(perm[c])))])
    json.dump(out, open(SUB, "w"))
    for frac, seed in RUNS:
        n = [len(out[key(frac, seed, f)]) for f in range(NF)]
        print(frac, seed, "polys per fold", n, "class counts f0", np.bincount(cls[np.array(out[key(frac, seed, 0)]) - 1], minlength=4)[1:].tolist())


def score(d, p):
    y = d.k.values
    return dict(acc=float((p == y).mean()), macroF1=float(f1_score(y, p, average="macro")),
                F1_bare=float(f1_score(y, p, labels=[2], average="macro")))


def save_run(model, frac, seed, d, pred, fold_acc, extra=None):
    LCD.mkdir(parents=True, exist_ok=True)
    r = dict(model=model, frac=frac, seed=seed, **score(d, pred), fold_macroF1=fold_acc, **(extra or {}))
    json.dump(r, open(LCD / f"{model}_{frac:.2f}_s{seed}.json", "w"))
    print(model, frac, seed, {k: round(v, 3) for k, v in r.items() if isinstance(v, float)}, flush=True)


def cpu():
    from sklearn.ensemble import RandomForestClassifier

    from e106_survey_data import emb, hls, zone30
    from e107_survey_states import feats, model
    pid, k5 = load()
    k = TO3[k5]
    d, _ = get()
    d = d.assign(k=TO3[d.k.values])
    S = json.load(open(SUB))
    F = feats(hls(2022))
    R, Cc, V = emb(2022, zone30())
    lut = -np.ones(pid.shape, "int64")
    lut[R, Cc] = np.arange(len(R))

    def E(r, c):
        i = lut[r, c]
        o = np.full((len(r), 64), np.nan, "float32")
        o[i >= 0] = V[i[i >= 0]] / 127.
        return o

    models = (("LightGBM", lambda r, c: F[:, r, c].T, lambda: model("C"), False),
              ("AlphaEarthRF", E, lambda: RandomForestClassifier(500, class_weight="balanced", n_jobs=-1, random_state=SEED), True),
              ("AlphaEarthMLP", E, lambda: model("B"), True))
    for nm, X, mk, nan0 in models:
        for frac, seed in RUNS:
            pred, fa = np.zeros(len(d), int), []
            rs = np.random.default_rng(SEED)          # same px-sampling stream as e122.base, so 100 % reproduces cv2022_3c
            for f in range(NF):
                tr_r, tr_c, tr_y = train_px(pid, k, np.array(S[key(frac, seed, f)]), rs)
                Xt = X(tr_r, tr_c)
                ok = ~np.isnan(Xt).all(1)
                m = mk().fit(np.nan_to_num(Xt[ok]) if nan0 else Xt[ok], tr_y[ok])
                te = d.fold.values == f
                Xe = X(d.r.values[te], d.c.values[te])
                pred[te] = m.predict(np.nan_to_num(Xe) if nan0 else Xe)
                fa.append(score(d[te], pred[te])["macroF1"])
            save_run(nm, frac, seed, d, pred, fa)


def init_from_pt():
    import torch

    import e117_prithvi_2022 as P
    ck = torch.load(SM / "prithvi_dwpt.pt", weights_only=False, map_location="cpu")    # own checkpoint (DirectML tensors)
    ck = {kk: {n: v.cpu() for n, v in dd.items()} for kk, dd in ck.items()}
    orig = P.build

    def build(K):
        enc, head, tp = orig(K)
        enc.load_state_dict(ck["enc"], strict=False)
        head.load_state_dict(ck["head"])
        return enc, head, tp
    P.build = build


def prithvi(arm):
    import e121_prithvi_2022_3c as E          # sets P.NCLS = 3 and the 3-class P.load
    import e117_prithvi_2022 as P
    assert arm in ("b223cPT", "b223c")
    if arm == "b223cPT":
        init_from_pt()
    pid, k = P.load()
    d, fold = E.get3()
    org = [tuple(v) for v in pd.read_csv(P.C22 / "origins.csv").values]
    S = json.load(open(SUB))
    PRED.mkdir(parents=True, exist_ok=True)
    for frac, seed in PRITHVI_ORDER:
        if (LCD / f"{arm}_{frac:.2f}_s{seed}.json").exists():
            continue
        pred, fa, eps = np.zeros(len(d), int), [], []
        for f in range(NF):
            te = d.fold.values == f
            fp = PRED / f"{arm}_{key(frac, seed, f)}.npz"
            if not fp.exists():
                t0 = time.time()
                sub = np.array(S[key(frac, seed, f)])
                vf = (f + 1) % NF
                polys = sub[fold[sub - 1] != vf]
                val = d[(d.fold == vf) & d.pid.isin(sub)]
                enc, head, ep = P.train("b22", pid, k, polys, org, val=val)
                st = P.predict(enc, head, org, 20, pid.shape)
                np.savez(fp, pred=st[d.r.values[te], d.c.values[te]], ep=ep)
                print(f"{arm} {key(frac, seed, f)} train polys {len(polys)} val px {len(val)} stop {ep} "
                      f"acc {float((st[d.r.values[te], d.c.values[te]] == d.k.values[te]).mean()):.3f} {int(time.time() - t0)} s", flush=True)
                del enc, head
            z = np.load(fp)
            pred[te] = z["pred"]
            eps.append(int(z["ep"]))
            fa.append(score(d[te], pred[te])["macroF1"])
        save_run(arm, frac, seed, d, pred, fa, dict(stop_epochs=eps))


def table():
    S = json.load(open(SUB))
    r = pd.DataFrame([json.load(open(p)) for p in sorted(LCD.glob("*.json"))])
    r["n_polys"] = [np.mean([len(S[key(a, b, f)]) for f in range(NF)]) for a, b in zip(r.frac, r.seed)]
    r.drop(columns=["fold_macroF1"]).to_csv(OD / "lc_runs.csv", index=False)
    rows = []
    for (m, fr), g in r.groupby(["model", "frac"]):
        row = dict(model=m, frac=fr, n_seeds=len(g), n_polys=g.n_polys.mean())
        for x in ("acc", "macroF1", "F1_bare"):
            row[x], row[x + "_sd"] = g[x].mean(), g[x].std(ddof=1) if len(g) > 1 else np.nan
            row[x + "_min"], row[x + "_max"] = g[x].min(), g[x].max()
        row["fold_sd_macroF1"] = float(np.std(g.fold_macroF1.iloc[0], ddof=1)) if len(g) == 1 else np.nan
        rows.append(row)
    t = pd.DataFrame(rows)
    t.to_csv(OD / "lc_table.csv", index=False)
    pd.set_option("display.width", 300)
    print(t.round(3).to_string())
    out = []
    for ref in ("LightGBM", "AlphaEarthRF"):
        for pr in ("b223cPT", "b223c"):
            for x in ("macroF1", "acc", "F1_bare"):
                a = r[r.model == ref].set_index(["frac", "seed"])[x]
                b = r[r.model == pr].set_index(["frac", "seed"])[x]
                gap = (a - b).dropna() * 100
                if 0.25 not in gap.index.get_level_values(0) or (1.0, 0) not in gap.index:
                    continue
                g25 = gap.loc[0.25]
                nar = g25.mean() - gap.loc[(1.0, 0)]
                thr = 2.0 + (g25.std(ddof=1) if len(g25) > 1 else 0)
                gm = gap.groupby(level=0).mean()
                out.append(dict(ref=ref, prithvi=pr, metric=x, **{f"gap_{int(f * 100)}": gm.get(f, np.nan) for f in (0.25, 0.5, 0.75, 1.0)},
                                gap25_sd=g25.std(ddof=1), narrowing=nar, threshold=thr,
                                verdict="closing" if nar > thr else "not closing"))
    dr = pd.DataFrame(out)
    dr.to_csv(OD / "lc_decision.csv", index=False)
    print(dr.round(2).to_string())
    ex = []
    for x in ("macroF1", "acc"):
        fit = {}
        for m, g in t.groupby("model"):
            b, a = np.polyfit(np.log2(g.n_polys), g[x] * 100, 1)
            fit[m] = (a, b)
            ex.append(dict(metric=x, model=m, intercept=a, slope_per_doubling=b))
        for ref in ("LightGBM", "AlphaEarthRF"):
            for pr in ("b223cPT", "b223c"):
                if ref in fit and pr in fit:
                    (a1, b1), (a2, b2) = fit[ref], fit[pr]
                    cross = 2 ** ((a1 - a2) / (b2 - b1)) if b2 > b1 else np.inf
                    ex.append(dict(metric=x, model=f"{pr} vs {ref}", cross_polys=cross))
    e = pd.DataFrame(ex)
    e.to_csv(OD / "lc_extrapolation.csv", index=False)
    print(e.round(3).to_string())


if __name__ == "__main__":
    {"subsets": subsets, "cpu": cpu, "prithvi": lambda: prithvi(sys.argv[2]), "table": table}[sys.argv[1]]()
