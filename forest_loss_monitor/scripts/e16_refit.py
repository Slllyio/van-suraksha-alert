"""Refit the change model on every labelled candidate point, including the first validation round, and pick the operating threshold
from held-out-tile scores. The first validation sample cannot be reused to test this model; e12_validation.py draws a new one."""
import json
import shutil

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve as prc
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from common import *
from e15_stage2 import F, design

MODEL = ROOT / "scripts" / "model_loss.json"


def fit(X, y):
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=0.03, max_iter=4000, class_weight="balanced").fit(sc.transform(X), y)
    w = lr.coef_[0] / sc.scale_
    b = float(lr.intercept_[0] - (lr.coef_[0] * sc.mean_ / sc.scale_).sum())
    assert np.allclose(X @ w + b, lr.decision_function(sc.transform(X)), atol=1e-4)
    return w, b


d = pd.read_parquet(F)
y = d.label.isin(list("LD")).astype(int).values
X = design(d, "change")
z = np.zeros(len(y))
for a, b_ in GroupKFold(5).split(X, y, d.tile):
    w, b = fit(X[a], y[a])
    z[b_] = X[b_] @ w + b
P, R, T = prc(y, z)
r = pd.DataFrame(dict(z=T, precision=P[:-1], recall=R[:-1]))
r["f1"] = 2 * r.precision * r.recall / (r.precision + r.recall + 1e-9)
print(r.iloc[np.linspace(0, len(r) - 1, 22).astype(int)].round(2).to_string(index=False))
print("best f1", r.loc[r.f1.idxmax()].round(2).to_dict())
shutil.copy(MODEL, ROOT / "scripts" / "model_loss_round1.json")
w, b = fit(X, y)
json.dump(dict(intercept=b, change_c=w[:64].tolist(), change_n=w[64:128].tolist(), dist_pc=float(w[128]), dist_pn=float(w[129]), n=len(y), positives=int(y.sum())), open(MODEL, "w"))
r.to_csv(OUT / "calibration" / "threshold_tile_holdout.csv", index=False)
