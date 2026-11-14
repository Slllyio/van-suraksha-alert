"""Running quality report for verified labels of one division: proof-of-sight pass count per batch file, label mix, duplicates, and agreement with the blind 10% re-label.
A batch with any guard failure is flagged HALT. Usage: e122_label_monitor.py <Division>"""
import glob
import sys

import pandas as pd

sys.path.insert(0, "E:/FIRE/.claude/worktrees/dreamy-dijkstra-133d15/forest_loss_monitor/scripts")
from e121_label_check import check

DIV = sys.argv[1]
V = "E:/FIRE/forest_loss_monitor/outputs/verified_labels/"
STRIPS = f"E:/FIRE/forest_loss_monitor/work/beat_blind_{DIV}_strips"


def main():
    rows, good = [], []
    for f in sorted(glob.glob(V + f"{DIV}_[0-9]*_[0-9]*.csv")):
        if f.endswith("_checked.csv"):
            continue
        c = check(STRIPS, f)
        c.to_csv(f.replace(".csv", "_checked.csv"), index=False)
        mix = c[c.seen].label.value_counts().to_dict()
        rows.append(dict(batch=f.replace("\\", "/").split("/")[-1], written=len(c), pass_guard=int(c.seen.sum()), fail_guard=int((~c.seen).sum()),
                         **{k: mix.get(k, 0) for k in "FUNAC"}, status="HALT" if (~c.seen).any() else "ok"))
        good.append(c[c.seen])
    t = pd.DataFrame(rows)
    g = pd.concat(good)
    print(t.to_string(index=False))
    print("verified spots", g.code.nunique(), "| duplicate codes", int(g.code.duplicated().sum()))
    rl = glob.glob(V + f"{DIV}_relabel10_*.csv")
    for f in rl:
        if f.endswith("_checked.csv"):
            continue
        r = check(STRIPS, f)
        m = r[r.seen].merge(g[["code", "label"]], on="code", suffixes=("_re", "_main"))
        yes = {"F": 1, "U": .5}
        print(f"re-label {f.split('_relabel10_')[1]}: {len(m)} spots, exact agreement {(m.label_re == m.label_main).mean():.0%}, "
              f"new-field score difference {abs(m.label_re.map(yes).fillna(0).mean() - m.label_main.map(yes).fillna(0).mean()):.2f}")
    g.drop_duplicates("code").to_csv(V + f"{DIV}_verified_all.csv", index=False)


if __name__ == "__main__":
    main()
