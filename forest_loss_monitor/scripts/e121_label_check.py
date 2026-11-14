"""Proof-of-sight check for blind labels. Each labeller must copy, per spot, the box NDVI printed under the ON 2017 frame and under the JF 2025 frame.
Those two numbers are recomputed here from the strip arrays; a label counts only if both match within 0.01, which shows the image was actually seen.
Usage: e121_label_check.py <strips_dir> <labels_csv> [id_map_csv]   (labels_csv columns: code or adj_id, label, ndvi_on2017, ndvi_jf2025)"""
import sys

import numpy as np
import pandas as pd


def box_ndvi(a, frame):
    c = a.shape[1] // 2
    n, r = a[frame, c - 2:c + 3, c - 2:c + 3, 0].astype(float), a[frame, c - 2:c + 3, c - 2:c + 3, 1].astype(float)
    ok = (n + r) > 0
    return np.nan if not ok.any() else float(np.nanmean(np.where(ok, (n - r) / np.maximum(n + r, 1), np.nan)))


def check(strips, labels, id_map=None):
    d = pd.read_csv(labels)
    if id_map:
        d = d.merge(pd.read_csv(id_map), on="adj_id")
    rows = []
    for r in d.itertuples():
        a = np.load(f"{strips}/{int(r.code)}.npy")
        t17, t25 = box_ndvi(a, 0), box_ndvi(a, 11)
        ok = abs(t17 - float(r.ndvi_on2017)) <= .011 and abs(t25 - float(r.ndvi_jf2025)) <= .011
        rows.append(dict(code=int(r.code), label=r.label, seen=ok, true_on2017=round(t17, 2), true_jf2025=round(t25, 2)))
    out = pd.DataFrame(rows)
    print(f"{out.seen.sum()} of {len(out)} labels pass the proof-of-sight check")
    return out


if __name__ == "__main__":
    check(*sys.argv[1:]).to_csv(sys.argv[2].replace(".csv", "_checked.csv"), index=False)
