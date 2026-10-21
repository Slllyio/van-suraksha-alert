"""Round 13: spread-out flag selection. Each flagged cell 'covers' its 3x3 block (patrol reach ~1.5 km).
Compare, at equal COVERED area, (a) plain top-k by risk vs (b) greedy coverage: repeatedly pick the cell whose 3x3
block holds the most not-yet-covered risk. Uses r11 calibrated per-cell risk (risk_y). Budgets: covered area = 10/20/30%
of the AOI on average across the season (pooled: more on high-risk days)."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter, uniform_filter

M = Path(r"E:\FIRE\ratapani\model"); OUT = M / "r13"; OUT.mkdir(exist_ok=True)
o = pd.read_parquet(M / "r11" / "calibrated_oof.parquet")
o = o.merge(pd.read_parquet(M / "celldays_v2.parquet", columns=["date", "cell_id", "i", "j"]), on=["date", "cell_id"])
o = o.merge(pd.read_parquet(M / "r8" / "oof_best.parquet", columns=["date", "cell_id", "cls"]), on=["date", "cell_id"])
NI, NJ = o.i.max() + 1, o.j.max() + 1
V = np.zeros((NI, NJ), bool); V[o.i, o.j] = True
NCELL = V.sum()
year = o.date.dt.year.to_numpy()


def greedy(risk, budget_cells):
    """pick cells until the covered (3x3-dilated) area reaches budget_cells; gain = uncovered risk in the 3x3 block."""
    covered = np.zeros_like(V); picked = np.zeros_like(V)
    gain = uniform_filter(risk, 3, mode="constant") * 9
    while covered.sum() < budget_cells:
        g = np.where(V & ~picked, gain, -1)
        k = np.unravel_index(np.argmax(g), g.shape)
        if g[k] <= 0: break
        picked[k] = True
        i0, i1, j0, j1 = max(k[0] - 1, 0), k[0] + 2, max(k[1] - 1, 0), k[1] + 2
        covered[i0:i1, j0:j1] |= V[i0:i1, j0:j1]
        risk = np.where(covered, 0, risk)
        # local gain refresh (only the 5x5 window can change)
        a0, a1, b0, b1 = max(k[0] - 2, 0), k[0] + 3, max(k[1] - 2, 0), k[1] + 3
        gain[a0:a1, b0:b1] = (uniform_filter(risk, 3, mode="constant") * 9)[a0:a1, b0:b1]
    return covered


def topk_cover(risk, budget_cells):
    order = np.argsort(-risk[V]); ii, jj = np.where(V)
    covered = np.zeros_like(V)
    for n in order:
        if covered.sum() >= budget_cells: break
        i, j = ii[n], jj[n]
        covered[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2] |= V[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2]
    return covered


rows = []
for yv in range(2013, 2025):
    sub = o[year == yv]
    days = sub.groupby("date")
    # daily covered-area budget proportional to the day's total risk (pooled), averaging to X% of the AOI
    tot = days.risk_y.sum()
    for X in (0.10, 0.20, 0.30):
        budget = (tot / tot.mean() * X * NCELL).clip(upper=NCELL).round().astype(int)
        res = {"topk": [0, 0, 0, 0], "greedy": [0, 0, 0, 0]}  # caught, pos, caught_new, new
        area = {"topk": 0, "greedy": 0}
        for d, g in days:
            risk = np.zeros((NI, NJ)); risk[g.i, g.j] = g.risk_y
            ymap = np.zeros((NI, NJ), bool); ymap[g.i, g.j] = g.y == 1
            nmap = np.zeros((NI, NJ), bool); nmap[g.i, g.j] = (g.y == 1) & (g.cls == "new")
            for name, fn in (("topk", topk_cover), ("greedy", greedy)):
                cov = fn(risk.copy(), budget[d]) if budget[d] > 0 else np.zeros_like(V)
                r = res[name]; r[0] += (cov & ymap).sum(); r[1] += ymap.sum(); r[2] += (cov & nmap).sum(); r[3] += nmap.sum()
                area[name] += cov.sum()
        for name, r in res.items():
            rows.append(dict(year=yv, covered_target=X, method=name, n_pos=r[1], n_new=r[3],
                             recall=r[0] / max(r[1], 1), recall_new=r[2] / max(r[3], 1),
                             covered_pct=100 * area[name] / (NCELL * len(days))))
    print(yv, flush=True)
R = pd.DataFrame(rows); R.to_csv(OUT / "r13_folds.csv", index=False)
S = R.groupby(["covered_target", "method"]).apply(lambda g: pd.Series(dict(
    covered_pct=g.covered_pct.mean(), recall=np.average(g.recall, weights=g.n_pos),
    recall_new=np.average(g.recall_new, weights=g.n_new))), include_groups=False).round(3)
S.to_csv(OUT / "r13_summary.csv"); print(S.to_string())
