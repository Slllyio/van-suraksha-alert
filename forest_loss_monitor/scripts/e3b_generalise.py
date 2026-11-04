"""Do embeddings generalise to unseen landscapes? Change-only features, spatial block CV, more label-source checks."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier as RF, HistGradientBoostingClassifier as HGB
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut, StratifiedKFold

from e3_train_eval import A_BANDS, D, cv_scores, labelled_points, logit, rf, summary

d = labelled_points()
m = d.merge(pd.read_parquet(D / "features.parquet"), on="sample_id").dropna().reset_index(drop=True)
y = m.label.isin(list("LD")).astype(int).values
p, c, n = (m[[f"{k}_{b}" for b in A_BANDS]].values for k in "pcn")
dist = lambda a, b: 1 - (a * b).sum(1, keepdims=True)
F = {
    "all (t-1,t,diff,next)": np.hstack([p, c, c - p, n - p, dist(p, c), dist(p, n)]),
    "change only (diff, next-diff, dist)": np.hstack([c - p, n - p, dist(p, c), dist(p, n)]),
    "next-diff + dist only": np.hstack([n - p, dist(p, n), dist(p, c)]),
    "distances only": np.hstack([dist(p, c), dist(p, n), dist(c, n)]),
}
blocks = (m.x // 30000).astype(int).astype(str) + "_" + (m.y // 30000).astype(int).astype(str)
print("blocks", blocks.nunique(), "real by tile", m.groupby("area").apply(lambda g: int(g.label.isin(list("LD")).sum())).to_dict())
loto = list(LeaveOneGroupOut().split(p, y, m.tile))
blk = list(GroupKFold(5).split(p, y, blocks))
kf = list(StratifiedKFold(5, shuffle=True, random_state=1).split(p, y))
for name, X in F.items():
    for mk, mn in ((rf, "RF"), (logit, "Logit")):
        for sp, sn in ((loto, "leave-tile"), (blk, "30km-blocks"), (kf, "random")):
            summary(y, cv_scores(mk, X, y, sp), f"{name[:26]:26s} {mn:5s} {sn}")
# which tile is worst
X = F["change only (diff, next-diff, dist)"]
s = cv_scores(logit, X, y, loto)
from sklearn.metrics import average_precision_score as ap
print({a: round(ap(y[m.area == a], s[m.area == a]), 2) for a in m.area.unique()})
