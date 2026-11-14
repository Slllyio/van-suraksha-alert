"""Partial beat-label export for one division: first-pass verified labels, second-pass labels, third reads, and the final label.
Final = agreed label; for a dispute, the third read if it matches either labeller, else U. Status: single_pass / double_labelled / third_read / disputed_pending.
Usage: e124_export_partial.py <Division>  (run e121 on third_read files first)"""
import glob
import sys

import pandas as pd

O = "E:/FIRE/forest_loss_monitor/outputs/"


def seen(pattern, col):
    fs = glob.glob(O + pattern)
    if not fs:
        return pd.DataFrame(columns=["code", col])
    c = pd.concat([pd.read_csv(f) for f in fs])
    return c[c.seen][["code", "label"]].drop_duplicates("code").rename(columns={"label": col})


def main(div):
    v = pd.read_csv(O + f"verified_labels/{div}_verified_all.csv")[["code", "label"]].rename(columns={"label": "label_first"})
    o = v.merge(seen(f"second_pass/{div}_[0-9]*_[0-9]*_checked.csv", "label_second"), on="code", how="left")
    o = o.merge(seen(f"third_read/{div}_[0-9]*_[0-9]*_checked.csv", "label_third"), on="code", how="left")
    single, agree = o.label_second.isna(), o.label_first == o.label_second
    third_ok = o.label_third.notna() & ~single & ~agree
    o["final"] = o.label_first.where(single | agree, None)
    o.loc[third_ok, "final"] = [t if t in (a, b) else "U" for a, b, t in o.loc[third_ok, ["label_first", "label_second", "label_third"]].values]
    o["status"] = "disputed_pending"
    o.loc[single, "status"], o.loc[agree, "status"], o.loc[third_ok, "status"] = "single_pass", "double_labelled", "third_read"
    o.to_csv(O + f"beat_estimation_inputs/6_{div.lower()}_beat_labels_partial.csv", index=False)
    print(o.status.value_counts().to_string())


if __name__ == "__main__":
    main(sys.argv[1])
