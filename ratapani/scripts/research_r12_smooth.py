"""Round 12: spatial post-processing of the risk map (r8 best LOYO OOF). Same flagged area (top 10% of season
cell-days), but rank cells by a smoothed score: 3x3 mean, 3x3 max, Gaussian sigma 1, or blend raw+smoothed."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter, uniform_filter, gaussian_filter

M = Path(r"E:\FIRE\ratapani\model"); OUT = M / "r12"; OUT.mkdir(exist_ok=True)
o = pd.read_parquet(M / "r8" / "oof_best.parquet")
o = o.merge(pd.read_parquet(M / "celldays_v2.parquet", columns=["date", "cell_id", "i", "j"]), on=["date", "cell_id"])
NI, NJ = o.i.max() + 1, o.j.max() + 1
V = np.zeros((NI, NJ), bool); V[o.i, o.j] = True
FILTERS = {
    "raw": lambda r: r,
    "mean3x3": lambda r: uniform_filter(r, 3, mode="constant") / np.maximum(uniform_filter(V.astype(float), 3, mode="constant"), 1e-9),
    "max3x3": lambda r: maximum_filter(r, 3),
    "gauss_s1": lambda r: gaussian_filter(r, 1) / np.maximum(gaussian_filter(V.astype(float), 1), 1e-9),
    "raw50_gauss50": lambda r: 0.5 * r + 0.5 * gaussian_filter(r, 1) / np.maximum(gaussian_filter(V.astype(float), 1), 1e-9),
}
year = o.date.dt.year.to_numpy()
rows = []
for yv in range(2013, 2025):
    sub = o[year == yv].reset_index(drop=True)
    groups = sub.groupby("date").indices
    for name, f in FILTERS.items():
        s = np.zeros(len(sub))
        for _, idx in groups.items():
            g = sub.iloc[idx]; r = np.zeros((NI, NJ)); r[g.i, g.j] = g.q_best
            s[idx] = f(r)[g.i, g.j]
        flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
        for _, idx in groups.items():
            g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
            c[idx] = maximum_filter(r, 3)[g.i, g.j]
        p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
        rows.append(dict(exp=name, fold=yv, n_pos=int(p.sum()), n_new=int(new.sum()), recall=c[p].mean(),
                         recall_new=c[new].mean() if new.any() else np.nan, recall_strict=flag[p].mean()))
R = pd.DataFrame(rows); R.to_csv(OUT / "r12_folds.csv", index=False)
S = R.groupby("exp").apply(lambda g: pd.Series(dict(recall=np.average(g.recall, weights=g.n_pos),
        recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new),
        recall_exact_cell=np.average(g.recall_strict, weights=g.n_pos))), include_groups=False).round(3)
S.to_csv(OUT / "r12_summary.csv"); print(S.to_string())
