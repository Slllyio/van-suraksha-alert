"""Rule and time-series inputs for the change/no-change points that the pixel table does not yet hold: same 50 m box and bands as e47_px.py. One thread, resumable. Usage: e78_cc_px.py"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import pandas as pd

from common import *
from e33_map10m import init_retry
from e47_px import BATCH, run

GT = ROOT / "ground_truth"
F = WORK / "cc_px.jsonl"
PID0 = 700000


def main():
    init_retry()
    d = pd.read_csv(GT / "guna_cc_labels.csv")
    d = d[d.set.isin(["bamori_fp", "recall_kit", "recent_new", "random", "new_flag"])].assign(pid=lambda q: q.cid + PID0, ry=lambda q: (q.y_m // 10000).astype(int)).rename(columns={"y": "label", "y_m": "y"})
    seen = {json.loads(l)["pid"] for l in open(F)} if F.exists() else set()
    d = d[~d.pid.isin(seen)].sort_values(["ry", "x"])
    n = 0
    with open(F, "a") as out:
        for i in range(0, len(d), BATCH):
            for row in run(d.iloc[i:i + BATCH]):
                out.write(json.dumps({k: ([round(x, 3) for x in v] if isinstance(v, list) else v) for k, v in row.items()}) + "\n")
                n += 1
            out.flush()
            print(n, "of", len(d), flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
