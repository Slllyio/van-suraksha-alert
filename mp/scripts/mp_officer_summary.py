"""Combine officer-style results: rules (without = all Jan-May fires; with = seasonal rules) x label set x model view."""
from pathlib import Path
import numpy as np
import pandas as pd

D = Path(r"E:\FIRE\mp\results_officer")
frames = []
for rules, prefix in (("without (Jan-May, all fires)", "officer"), ("with (15 Feb-31 May, early input, no control burns)", "seasonal")):
    for tag, lab in (("3sat", "S-NPP+NOAA-20+NOAA-21"), ("s20", "S-NPP+NOAA-20")):
        x = pd.read_csv(D / f"{prefix}_{tag}.csv").assign(rules=rules, labels=lab)
        frames.append(x)
R = pd.concat(frames, ignore_index=True)


def wavg(g, c, w):
    g = g.dropna(subset=[c])
    return np.average(g[c], weights=g[w]) if len(g) and g[w].sum() else np.nan


views = {"recommended (own; borrow if weak)": lambda g: g[g.recommended == True],
         "own model": lambda g: g[g.model == "own"],
         "neighbour borrowing": lambda g: g[g.model == "borrow"],
         "weak divisions only: own": lambda g: g[(g.model == "own") & g.weak],
         "weak divisions only: borrow": lambda g: g[(g.model == "borrow") & g.weak]}
rows = []
for (rules, lab), g0 in R.groupby(["rules", "labels"], sort=False):
    for vname, f in views.items():
        g = f(g0)
        rows.append(dict(rules=rules, labels=lab, view=vname, divisions=g.division.nunique(),
                         fire_celldays=int(g.n_pos.sum()), fires=int(g.n_events.sum()),
                         fires_caught_strict=wavg(g, "event_recall_first", "n_events"),
                         fires_caught_loose=wavg(g, "event_recall_any", "n_events"),
                         beat_episodes=int(g.n_beat_episodes.sum()),
                         beats_caught_strict=wavg(g, "beat_recall_first", "n_beat_episodes"),
                         beats_caught_loose=wavg(g, "beat_recall_any", "n_beat_episodes"),
                         cell_days_caught=wavg(g, "cell_recall", "n_pos"),
                         ground_flagged_pct=g.flagged_pct.mean(), ground_flagged_or_next_pct=g.covered_pct.mean(),
                         beats_flagged_pct=g.beat_share_flagged.mean(),
                         flagged_beats_per_range_day=g.beats_flagged_per_range_day.mean()))
S = pd.DataFrame(rows)
S.to_csv(D / "combined_summary.csv", index=False)
pd.set_option("display.width", 250)
print(S[S.view.str.startswith(("recommended", "weak"))].round(3).to_string(index=False))
# per-division table for the headline setting
per = R[(R.recommended == True)][["rules", "labels", "division", "weak", "model", "n_events", "event_recall_first", "event_recall_any",
                                  "beat_recall_first", "beat_recall_any", "flagged_pct", "covered_pct", "beats_flagged_per_range_day"]]
per.to_csv(D / "per_division_recommended.csv", index=False)
w = per[(per.labels == "S-NPP+NOAA-20+NOAA-21") & per.rules.str.startswith("with")].sort_values("event_recall_first")
print("\nweakest 6 (3 satellites, with rules):\n", w.head(6).round(3).to_string(index=False))
print("weak divisions:", int(per[per.rules.str.startswith("with") & (per.labels == "S-NPP+NOAA-20+NOAA-21")].weak.sum()))
print("covered_pct range:", per.covered_pct.min().round(1), per.covered_pct.max().round(1))
