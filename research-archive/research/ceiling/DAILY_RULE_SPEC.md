# Daily alert list rule: spec for the live alert app

From the thread "Is the project at its limit". Akkshay said "ok go ahead" at 07:42Z on 19 Oct 2026.
The live alerts thread builds this rule into field-system. This file only describes what to build.
Results tables: van-suraksha-alert PR #1, `mp/results/officer/live_*` (the PC pipeline thread, 18 Oct 20:41Z).

## What the rule does

Every day it picks which 500 m squares (mp_grid) go on the officials' "check in the next 2 days" list. It uses the +GIS division model's calibrated % per square.

1. **Daily total for MP.** First set each division's danger-scaled daily count, as used in the PC tests. Add them up to get the statewide total for the day. The workload stays the same as now; only where the flags go changes.
2. **Floor.** Each division keeps at least 50% of its own count. It fills those flags with its highest-% squares.
3. **Quiet-square reserve.** Of the whole day's flags, 35% (25% until 21 Oct 2026) are kept for quiet squares. A quiet square has no VIIRS point within 5 km over the previous 7 days. They are filled by the highest % among quiet squares statewide. The exact order of steps 2-4, and whether quiet squares taken by the floor count toward the 25%, should follow the PC's `live_*` scoring code. Ask the pipeline thread before building.
4. **Statewide pool.** All remaining flags go to the highest-% squares anywhere in MP that are not already flagged.
5. **Calibration.** The % comes from calibration fitted on the previous season only. Refit once a year, before 15 Feb. Never use the current season's outcomes.

Every input is known on the morning it is used: last season's calibration, the season so far, and today's scores. So the same rule can run unchanged in a 2027 shadow trial.

## Measured result

Strict scoring: each fire counted once, with the same daily total and the same ground. Only 2023-24 and 2026 can be scored, because 2022 and 2025 have no earlier season to calibrate from.

| Rule | All fires (2023-24 / 2026) | Brand-new | Beats |
|---|---|---|---|
| Hindsight top 10% per division (yardstick, not usable live) | 72 / 70% | 42 / 36% | 81 / 81% |
| Each division sets its own daily count (the earlier live rule) | about 65% | about 38% | about 79% |
| **This rule** | **71 / 68%** | **46 / 48%** | **83 / 82%** |

- **All fires.** The rule matches the hindsight yardstick within 1-2 points. That wins back the 8-9 points the earlier per-division count lost.
- **Brand-new fires and beats.** The rule catches 4-12 points more brand-new fires and about 2 points more beats than the yardstick.
- **Flags.** Fires caught per 100 flags are the same or better.
- **Burn-scar check.** Against a burn-scar answer key (fires confirmed by a scar), the model catches about 82% of fires on about a fifth of the ground (section 8 of `README.md`).

## Points for the build (my suggestions, not tested)

- **Division floor.** Under a full pool, 14 low-fire divisions lost most of their flags every year: Barwani, Bhind, Datiya, Jhabua, Kanha, Morena, Neemuch, Pench, Rajgarh, Satpura, Shajapur, Sidhi, Tikamgarh and Ujjain. The 50% floor is there to stop that.
  - The PC found a bug where 3-5 tiny divisions still fell below half. Check that no division gets less than half its own count on any day.
- **Tie-break.** When two squares have the same %, use the division model's raw score.
- **Officials' list.** Show why each square is on the list: "division", "quiet square" or "statewide". Officials can then see that a busy division borrowed checks from a quiet one.
- **What does not change.** Guards' beat alerts and the real-time fire alerts stay as they are. This rule only changes the 2-day prediction list.
- **Switch.** Add a setting to fall back to the per-division counts (for example `FS_DAILY_RULE=division`).

## Built (19 Oct 2026, live alerts thread)

Built in field-system as `app/daily_list.py`; the pipeline posts scores to `POST /api/v1/daily_scores` (see field-system/INTEGRATION.md).

The PC's scoring code is not in the repo: commit f04ce30c holds result tables only. The step order was therefore taken from `mp/README.md`, "Live combined rule":
- **Floor:** each division keeps half its count, 25% of it on its quiet squares and 75% on others, with spare slots moving between the two.
- **Pool:** the rest goes statewide by calibrated %, 25% to quiet squares.
- **Counting:** quiet squares taken by the floor do not count toward the pool's 25%.

## Changed 21 Oct 2026: quiet share 35% (Akkshay "35")

The Prithvi thread ran the exact live rule with the quiet share as a parameter (vanagni c04a9e1, `prithvi_finetune/analysis/live_quiet_curve/`): 2026 / held-out 2023-24, same ground.

| Quiet share | All fires | Brand-new | Beats |
|---|---|---|---|
| 25% (before) | 67.5 / 71.1% | 47.6 / 45.8% | 82.3 / 83.2% |
| **35% (now)** | 65.4 / 69.5% | 52.3 / 49.6% | 81.3 / 83.0% |
| 50% | 61.7 / 66.1% | 57.9 / 54.0% | 79.3 / 81.4% |
| 75% | 53.0 / 57.2% | 65.0 / 60.4% | 72.8 / 75.8% |

- One setting drives both the floor split and the pool split (`QF`), so the app's `FS_QUIET_SHARE` (default 0.35) does the same.
- The PC bisects k per rule so the ground stays the same. At 35% the PC's k is **0.58740234375** (bisected on 2026, ground covered 21.9%; its 25% k was 0.60322265625). The app uses it (`FS_DAILY_K`). Before the PC's value arrived the app used 0.5844, fitted on the five 2026 check days; the two differ by 0.5%.
- Check on the same five days against real VIIRS fires on day +1/+2: all fires 57.5% -> 54.5%, fires on quiet squares 36% -> 45%. The direction and size match the PC's curve (all -2 pts, brand-new +4-5 pts); five days are a small sample.
- Found while doing this: the app's own count path had no k (it flagged 10% of squares in the first week, 1/0.6 more than the tested rule). `counts()` now multiplies by k.
