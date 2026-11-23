# Big-fire watch list (daily, officials)

Akkshay, 20 Oct 2026: "keep the daily list, and add the big-fire model as a separate short watch list of the top 1-2% of squares."

The list is a short extra layer next to the daily list. It does not replace the daily list. Each issue day it ranks every 500 m square for the chance that a 200 ha+ fire's first look lands in it, or next to it, in the next 2 days. It flags the top 1% and the top 2% of each division's squares.

**Tested on 2025**, the held-out season (`../README.md`, "Fair check"), against the PC's 87 daily models at the same share of each division:

| watch list | 200 ha+ fires caught | 500 ha+ fires caught | PC daily models, 200 ha+ / 500 ha+ |
|---|---|---|---|
| top 1% | 53% | 59% | 40% / 46% |
| top 2% | 68% | 73% | 57% / 57% |

In 2025, about 1 in 95 top-1% square-days and 1 in 120 top-2% square-days got a big-fire start, roughly 20x the average square. So the list is for watchers, readiness and early response, not for sending a crew to every square.

- `big_watch.py DATE [--firms new.csv]` writes `big_watch_<date>.parquet` (`cell`, `division`, `score`, `pct`, `rank_in_division`, `top1`, `top2`) and a per-division count csv. One day takes about 3 minutes on 4 cores, because it rebuilds the season's fire inputs from 1 Jan.
- Replay check: 5 Apr 2025 reproduces the tested scores (max difference 1e-5, float16 rounding). That day flags 4,232 squares at top 1% and 8,422 at top 2%, statewide.
- `pct` is calibrated on 2025 and capped at 3%. In 2025, squares it put at 0.1-0.5% came true 0.22% of the time, 0.5-1% came true 0.67%, 1-2% came true 1.39%, and 2%+ came true 3.0%. The calibration was fitted and checked on the same season, so recheck it on 2026 scars when they exist. If officials see the big-fire points as rank only (Akkshay, 18 Oct), show this list the same way: rank only, no %.
- Model: `big_model.txt` (LightGBM, trained 2018-24). `features.json` lists its inputs. `scar_hist_2025/2026.npz` hold the scar-history inputs, made from earlier seasons only. `squares.npz` holds the square list and each square's home division.
- Live inputs: VIIRS detections. The archive is in `fire-alert-scars/alerts_mp`; pass the season's newer FIRMS VIIRS rows with `--firms`. Also needed: HLS dryness (`ratapani/mp_grid/dryness/mp_dry_<season>.npz`) and `static_gis_v1`. No weather and no Earth Engine. For a new season S, rebuild `scar_hist_S.npz` with `scripts/l9_package.py` once that season's earlier scars exist.

## Size score for ranking new fires (added 20 Oct, Akkshay chose "Use size score" 09:38Z)
**Correction 20 Oct:** use points + size score combined, not size score alone (see ../README.md at-alert correction; live alerts is building it).
`score_day` also returns `size_score` per square: chance a fire starting there reaches 200 ha (`size_model.txt`, SIZE model trained 2018-24, same inputs as `big_model.txt`). Use: when a new fire's first look arrives, take the highest `size_score` of its first-look squares from the previous night's run, and order officials' new fires by it (rank only, no %). Guards' alerts unchanged. 2025 test (../README.md, at-alert section): AUC 0.84 vs 0.70 for big-fire points (200 ha+); day's top 10% of new fires hold 43% vs 28% of 200 ha+ fires; points + size score = size score alone. Replay 5 Apr 2025 matches the tested scores (max diff 2.4e-4, float16 rounding).

## Season cuts (21 Oct): use `top1_cut` / `top2_cut`
`top1`/`top2` rank each day on its own (top 1% of squares every day). On 2026 that caught 46% of 200 ha+ fires against 64% for a fixed per-division cut from the 2025 season (`cuts_2025.json`), on less ground (../README.md, "Late season and the live rule"). The flag count then varies by day: on 5 Apr 2025, a peak day, 9,205 squares against 4,232. Refresh the cuts each June from the season just ended.
