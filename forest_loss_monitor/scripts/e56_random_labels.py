"""My visual labels of the 300 random forest points, made from blind S2 sheets, scored against each scrub-to-farm setting. Usage: e56_random_labels.py
N forest unchanged, S open or scrub unchanged, A farmland already there in 2018-19, C changed to crop after 2018-19, W water, U unclear."""
import pandas as pd

from common import *
from e48_tests import by_point, load, s2f_flags
from e50_s2f_rate import SET, wilson
from e46_s2f import RAND_BASE
from e48_tests import GT

L = """S N N S S N S N N N N N S N S N N N S N
N S S A S N S S S S S N W N N C N A N N
N U S N S S N S N W N S S N A S N N S N
S A N A U N N S N N S S N N S N S N S N
N S W N S S S S S N S S S S N W S S A S
S S S N S S S W N S S S S S S N N N S N
N S N S N N S S N S N A N A S S N N S N
S N S N N N N N N A A C A A N N S N N S
A S S S C S N S A N W S N S N S S S A S
S S S N S S S N S S S S S N S N S N S S
S N N N N A S N N N S S S A N N S S S N
S N S N N A N S N N N S N S S N S A W S
N S N N A S N N S S N N A A N N N S N A
A A S S N N N S S N N S C N S S S N S N
S N N A N N A A S S N A S S A N N N N S
"""


def main():
    lab = L.split()
    assert len(lab) == 300, len(lab)
    t = pd.DataFrame(dict(pid=RAND_BASE + pd.RangeIndex(300), label=lab))
    t.to_csv(GT / "s2f_random300_labels.csv", index=False)
    p = load()
    p = p[p.pid >= RAND_BASE]
    print(t.label.value_counts().to_dict())
    forest = 9317460
    rows = []
    for name, g in SET.items():
        f = by_point(p, s2f_flags(p, *g[:4]), g[4]).reindex(t.pid).fillna(False).values
        q = t[f]
        true, false = int((q.label == "C").sum()), int((~q.label.isin(["C", "U"])).sum())
        stable = int((~t.label.isin(["C", "U"])).sum())
        rows.append(dict(setting=name, flagged=int(f.sum()), real_C=true, false=false, unclear=int((q.label == "U").sum()), labels=str(q.label.value_counts().to_dict()), missed_C=int((t.label == "C").sum()) - true,
                         false_rate_pct=round(100 * false / stable, 1), false_ci=wilson(false, stable), false_ha_per_1000=round(1000 * false / stable, 1), flag_pct=round(100 * f.mean(), 1), flag_ci=wilson(int(f.sum()), 300), implied_state_flag_ha=round(forest * f.mean()), implied_false_ha=round(forest * false / 300), pids=[int(i) - RAND_BASE for i in q.pid]))
    r = pd.DataFrame(rows)
    print(r.T.to_string())
    r.to_csv(OUT / "interim" / "report" / "s2f_false_alarm.csv", index=False)
    k = int((t.label == "C").sum())
    print("real conversions seen", k, "pct", round(100 * k / 300, 1), wilson(k, 300), "implied ha", round(forest * k / 300))


if __name__ == "__main__":
    main()
