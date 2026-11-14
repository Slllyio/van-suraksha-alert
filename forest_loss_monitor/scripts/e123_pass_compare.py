"""Compare a second-pass label batch with the first pass for one division: guard check, agreement, kappa, and hectares each disagreement moves.
Writes <batch>_vs_first.csv and <batch>_disagree_codes.csv next to the batch. Usage: e123_pass_compare.py <Division> <second_pass_csv>"""
import glob
import sys

import pandas as pd
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, "E:/FIRE/.claude/worktrees/dreamy-dijkstra-133d15/forest_loss_monitor/scripts")
from e121_label_check import check

R = "E:/FIRE/forest_loss_monitor/"
SCORE = {"F": 1, "U": .5}


def spot_weights(div):
    key = pd.read_csv(glob.glob(R + f"ground_truth/beat_blind_{div}_key*.csv")[0])
    a = pd.read_csv(R + "outputs/beat_estimation_inputs/2_ring1_beat_map_areas.csv")
    a = a[a.Division == div]
    n = key.groupby(["group", "beat"]).size().rename("n").reset_index()
    w = n.merge(a, left_on=["group", "beat"], right_on=["Range", "Beat"], how="left")  # beat names repeat across ranges
    w["ha_per_spot"] = w.new_farmland_ha / w.n
    return key[["code", "group", "beat"]].merge(w[["group", "beat", "ha_per_spot"]], on=["group", "beat"])


def main(div, path):
    s = check(R + f"work/beat_blind_{div}_strips", path)
    s.to_csv(path.replace(".csv", "_checked.csv"), index=False)
    first = pd.concat([pd.read_csv(f) for f in glob.glob(R + f"outputs/verified_labels/{div}_[0-9]*_[0-9]*_checked.csv")]).drop_duplicates("code")
    m = s[s.seen].merge(first[first.seen][["code", "label"]], on="code", suffixes=("_2", "_1")).merge(spot_weights(div), on="code", how="left")
    assert m.code.is_unique and m.ha_per_spot.notna().all(), "weight join broke"
    m["moved"] = (m.label_2.map(SCORE).fillna(0) - m.label_1.map(SCORE).fillna(0)) * m.ha_per_spot
    d = m[m.label_1 != m.label_2]
    print(f"guard {int(s.seen.sum())}/{len(s)} | compared {len(m)} | agreement {(m.label_1 == m.label_2).mean():.0%} | kappa {cohen_kappa_score(m.label_1, m.label_2):.2f}"
          f" | U share {(m.label_1 == 'U').mean():.0%} / {(m.label_2 == 'U').mean():.0%} | disagree {len(d)} | ha moved net {d.moved.sum():+.1f} abs {d.moved.abs().sum():.1f}"
          f" | est first {(m.label_1.map(SCORE).fillna(0) * m.ha_per_spot).sum():.1f} second {(m.label_2.map(SCORE).fillna(0) * m.ha_per_spot).sum():.1f} of {m.ha_per_spot.sum():.1f} ha")
    print(pd.crosstab(m.label_1, m.label_2))
    m.to_csv(path.replace(".csv", "_vs_first.csv"), index=False)
    d[["code"]].to_csv(path.replace(".csv", "_disagree_codes.csv"), index=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
