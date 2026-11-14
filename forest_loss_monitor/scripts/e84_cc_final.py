"""Stress test of the pixel-level embedding model, then the final fit. Holds out 5 km blocks, 10 km blocks and whole forest ranges; trains with and without Bamori; shows run-to-run spread, not only the majority vote.
Saves the final models and thresholds chosen on out-of-fold scores of all data. Usage: e84_cc_final.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import OUT
from e76_cc_train import REPORT, load, ref_w, thr_for, wpr
from e77_cc_local import design, wide
from e79_cc_fusion import boot, cv_view, flags_at
from e83_cc_pxmodel import px_features

warnings.filterwarnings("ignore")
REPEATS = 10
VIEWS = {"scalars": ("step",), "all": ("step", "change", "local change", "before", "after")}
TARGETS = (.9, .8, .7, .6, .5)


def main():
    d, A = load()
    scal, chg, lchg, pre, post = px_features(d, A, wide(d))
    B = {"step": scal, "change": chg, "local change": lchg, "before": pre, "after": post}
    y, w = d.y.values, ref_w(d)
    k = (d.set == "reference").values
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == "Guna"].drop_duplicates("Beat").set_index("Beat").Range
    tests = {"5 km blocks": d.block, "10 km blocks": (d.x // 10000).astype(int).astype(str) + "_" + (d.y_m // 10000).astype(int).astype(str),
             "whole ranges": d.beat.map(lk).fillna(d.block)}
    rows = []
    for tname, g in tests.items():
        q = d.assign(block=g.values)
        for vn, parts in VIEWS.items():
            X, sc, ve = design(B, parts)
            runs = [cv_view(X, q, y, sc, ve, r) for r in range(REPEATS)]
            for tg in TARGETS:
                fl = [flags_at(a, b, y, w, k, tg) for a, b in runs]
                pr = [wpr(y[k], f[k].astype(int), w[k]) for f in fl]
                maj = np.mean(fl, axis=0) >= .5
                p, r = wpr(y[k], maj[k].astype(int), w[k])
                ci = boot(d, maj)
                rows.append(dict(holdout=tname, view=vn, target=tg, precision=round(p, 3), p_ci=ci[0], recall=round(r, 3), r_ci=ci[1], p_mean=round(float(np.nanmean([a for a, _ in pr])), 3), p_sd=round(float(np.nanstd([a for a, _ in pr])), 3), r_mean=round(float(np.mean([b for _, b in pr])), 3), r_sd=round(float(np.std([b for _, b in pr])), 3),
                                 flagged=int(maj[k].sum()), real=int((maj[k] & (y[k] == 1)).sum()), background_false=int((maj & k & (d.stratum == "background").values & (y == 0)).sum()), random_flag_pct=round(100 * maj[(d.set == "random").values].mean(), 1)))
                print(json.dumps(rows[-1]), flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_stress.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30)
    print(t.to_string())
    out = {}
    use = y >= 0
    for vn, parts in VIEWS.items():
        X, sc, ve = design(B, parts)
        tf = [("s", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), sc)] + [(f"v{i}", make_pipeline(StandardScaler(), PCA(8, random_state=0)), v) for i, v in enumerate(ve)]
        m = make_pipeline(ColumnTransformer(tf), LogisticRegression(C=.05, max_iter=3000, class_weight="balanced")).fit(X[use], y[use])
        oof = np.nanmean([cv_view(X, d, y, sc, ve, r)[0] for r in range(REPEATS)], axis=0)
        out[vn] = dict(model=m, parts=parts, thresholds={tg: float(thr_for(oof[k], y[k], w[k], tg)) for tg in TARGETS})
        print(vn, out[vn]["thresholds"])
    joblib.dump(out, OUT / "interim" / "report" / "guna_cc_model.joblib")


if __name__ == "__main__":
    main()
