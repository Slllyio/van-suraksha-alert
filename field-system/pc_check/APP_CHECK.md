# App vs PC, daily rule at 35% quiet squares (21 Oct 2026)

The app's `daily_list.select` was run on the PC's own scores, divisions, quiet flags and counts (PC dumps in `E:\FIRE\prithvi_ft\pc_check_q35\`, k = 0.58740234375).

| Day | PC flags | App flags | Same squares | Quiet flags PC / app | Quiet share (PC) |
|---|---|---|---|---|---|
| 12 Mar | 86,325 | 86,325 | 99.93% | 30,226 / 30,229 | 35.0% |
| 5 Apr | 23,233 | 23,233 | 99.81% | 8,193 / 8,197 | 35.3% |
| 10 May | 10,442 | 10,442 | 99.63% | 3,656 / 3,657 | 35.0% |

- The same total is flagged each day. The few differences are squares with the same calibrated %, where the app breaks the tie by raw score.
- This run uses the PC's quiet flags. The 19 Oct check at 25% (five days, quiet worked out by the app from its own points) matched 99.8-99.9% and the quiet squares exactly.
- 17 Mar and 22 Apr were not re-dumped at 35%, so their 25% files were removed.

Files: `app_vs_pc.csv`.
