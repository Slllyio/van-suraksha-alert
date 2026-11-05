"""'Woody before' gate on the stage-1 flags: Dynamic World 2017-19 trees >= 0.30, or trees + shrub >= 0.40, no water. The thresholds are e_Netra's own, not tuned here.
Reads the per-point table from e86. Offline. Usage: e87_cc_gate.py"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd

from e23_guna_labels import A_H, wpr
from e76_cc_train import REPORT

SEED = 20261106


def ci(ref, f, n=1000):
    rng = np.random.default_rng(SEED)
    idx = {b: np.flatnonzero(ref.beat.values == b) for b in ref.beat.unique()}
    P, R = [], []
    for _ in range(n):
        i = np.concatenate([idx[b] for b in rng.choice(list(idx), len(idx))])
        p, r = wpr(ref.y.values[i], f[i].astype(int), ref.w.values[i])
        if np.isfinite(p):
            P.append(p)
        R.append(r)
    return f"{np.quantile(P, .025):.2f}-{np.quantile(P, .975):.2f}", f"{np.quantile(R, .025):.2f}-{np.quantile(R, .975):.2f}"


def main():
    c = pd.read_csv(REPORT / "cc_cases.csv", keep_default_na=False, na_values=[""])
    s1 = c.stage1.isin(["caught", "false alarm"]).values
    woody = c.before.isin(["tree cover", "scrub"]).values
    ts2, ts5 = (c.ts_pixels_passing >= 2).values, (c.ts_pixels_passing >= 5).values
    k = (c.set == "reference").values
    n = c[k].stratum.value_counts()
    c["w"] = np.where(k, c.stratum.map(lambda s: A_H.get(s, 0) / n.get(s, 1)), 0.)
    ref = c[k].reset_index(drop=True)
    rnd, bf = (c.set == "random").values, (c.set == "bamori_fp").values
    rows = []
    for nm, f in {"stage 1": s1, "stage 1 + woody gate": s1 & woody, "stage 1 + falls on 2 px": s1 & ts2, "stage 1 + woody gate + falls on 2 px": s1 & woody & ts2,
                  "stage 1 + falls on 5 px": s1 & ts5, "stage 1 + woody gate + falls on 5 px": s1 & woody & ts5}.items():
        p, r = wpr(ref.y.values, f[k].astype(int), ref.w.values)
        pc, rc = ci(ref, f[k])
        row = dict(method=nm, precision=round(p, 3), p_range=pc, recall=round(r, 3), r_range=rc, ref_real=int((f[k] & (ref.y.values == 1)).sum()), ref_false=int((f[k] & (ref.y.values == 0)).sum()),
                   random_flag_pct=round(100 * f[rnd].mean(), 1), random_woody_flag_pct=round(100 * f[rnd & woody].sum() / (rnd & woody).sum(), 1), bamori_rejected=f"{int(f[bf].sum())}/112")
        for cls in ("forest_to_crop", "shrub_to_crop"):
            q = ((c.set == "bamori_tp") & (c.cls == cls)).values
            row[cls] = f"{int(f[q].sum())}/{int(q.sum())}"
        q = ((c.set == "felling") & (c.y == 1)).values
        row["fellings"] = f"{int(f[q].sum())}/{int(q.sum())}"
        rows.append(row)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_gate.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30)
    print(t.to_string())
    bt = c[(c.set == "bamori_tp") & (c.y == 1)]
    print(pd.crosstab(bt.cls, bt.before))
    print("reference by land type\n", pd.crosstab(ref.before, [ref.stratum, ref.y]))
    print("gate removes from reference:", pd.crosstab(ref.stage1[~woody[k]], ref.stratum[~woody[k]]).to_string())
    print(bt[~bt.before.isin(["tree cover", "scrub"])][["id", "cls", "before", "trees_early", "shrub_early", "crops_early", "water", "ha"]].round(2).to_string())


if __name__ == "__main__":
    main()
