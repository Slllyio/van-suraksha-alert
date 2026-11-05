"""Rescue rule: keep a stage-1 flag if the Oct-Nov falls pass on enough pixels, or if radar shows a break stronger than in most unlabelled forest land.
The radar bar is a percentile of the 400 random points, so no label sets it. Offline. Usage: e90_cc_rescue.py"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd

from e23_guna_labels import A_H, wpr
from e76_cc_train import REPORT, load
from e87_cc_gate import ci
from e89_cc_second import new_feats


def main():
    d, _ = load()
    N = new_feats(d)
    c = pd.read_csv(REPORT / "cc_cases.csv", keep_default_na=False, na_values=[""])
    assert (c.cid.values == d.cid.values).all()
    s1 = c.stage1.isin(["caught", "false alarm"]).values
    k, rnd = (c.set == "reference").values, (c.set == "random").values
    n = c[k].stratum.value_counts()
    c["w"] = np.where(k, c.stratum.map(lambda s: A_H.get(s, 0) / n.get(s, 1)), 0.)
    ref = c[k].reset_index(drop=True)
    radar = {"leaf-on VH": N["leaf_vh:t_any"].values, "dry VH": N["dry_vh:t_any"].values, "either VH": np.maximum(N["leaf_vh:t_any"].values, N["dry_vh:t_any"].values)}
    rows = []
    for px in (2, 5):
        ts = (c.ts_pixels_passing >= px).values
        cases = {f"falls on {px} px": s1 & ts}
        for nm, v in radar.items():
            for q in (90, 95, 98):
                cases[f"falls on {px} px, or {nm} above {q}% of random land"] = s1 & (ts | (v >= np.nanpercentile(v[rnd], q)))
        for nm, f in cases.items():
            p, r = wpr(ref.y.values, f[k].astype(int), ref.w.values)
            pc, rc = ci(ref, f[k])
            bgp = (ref.stratum == "background") & (ref.y == 1)
            row = dict(method=nm, precision=round(p, 3), p_range=pc, recall=round(r, 3), r_range=rc, real=int((f[k] & (ref.y.values == 1)).sum()), false=int((f[k] & (ref.y.values == 0)).sum()), background_losses=f"{int(f[k][bgp.values].sum())}/6", random_flag_pct=round(100 * f[rnd].mean(), 1))
            for cls in ("forest_to_crop", "shrub_to_crop"):
                m = ((c.set == "bamori_tp") & (c.cls == cls)).values
                row[cls] = f"{int(f[m].sum())}/{int(m.sum())}"
            row["bamori_rejected"] = f"{int(f[(c.set == 'bamori_fp').values].sum())}/112"
            rows.append(row)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_rescue.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30, "display.max_colwidth", 60)
    print(t.to_string())


if __name__ == "__main__":
    main()
