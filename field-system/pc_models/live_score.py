"""Daily live fire flags for MP (floor50_quiet25 rule). Standalone: needs numpy, pandas, lightgbm.

Usage:
  python live_score.py --models pc_models --features <dir> --state season_state.csv --date 2026-04-05 --out <dir>

Inputs
  --models    folder with models/<division>.txt.xz (or .txt), calibration/<division>.json and meta.json
  --features  one parquet per division, <division>.parquet, for the issue day: column `cell` (mp_grid cell =
              row*1829+col), column `quiet` (1 = no type-0 VIIRS detection within 5 km on days t-6..t) and every
              feature listed in meta.json["divisions"][<division>]["features"] (same definitions as the training tables)
  --state     season running state: division, n_days, sum_daily_mean (sum over this season's earlier issue days of the
              division's mean raw score). Missing file or division = start of season.
Outputs (in --out)
  flags_<date>.parquet   cell, division, pct (calibrated %), score (raw), quiet, flag
  counts_<date>.csv      division, squares, quiet_squares, own_count, floor, flags, quiet_flags
  season_state.csv       updated state for the next issue day

Rule (as in the PC research, results/officer/live_*):
  share_div  = 10% x today's mean score / this season's mean daily score up to yesterday, clipped 1-40%
               (10% during the season's first 7 issue days)
  own_count  = round(k x share_div x squares), k from meta.json (0.6032: matched to the 2026 ground of the reference)
  floor      = round(0.5 x own_count) kept by the division: 25% on its quiet squares, the rest on others (best raw score;
               spare slots move between the two groups)
  pool       = sum of own_count - all floors, given statewide to the highest calibrated % squares not yet flagged;
               25% of the pool to quiet squares.
"""
import argparse, json, lzma
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb


def load_model(M, dv):
    """models/<division>.txt.xz (shrunk, xz-compressed) or models/<division>.txt."""
    xz = M / "models" / f"{dv}.txt.xz"
    if xz.exists():
        return lgb.Booster(model_str=lzma.decompress(xz.read_bytes()).decode())
    return lgb.Booster(model_file=str(M / "models" / f"{dv}.txt"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True); ap.add_argument("--features", required=True)
    ap.add_argument("--state", default=None); ap.add_argument("--date", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    M = Path(a.models); meta = json.loads((M / "meta.json").read_text()); rule = meta["live_rule"]
    k, floor_f, quiet_f = rule["k"], rule["floor"], rule["quiet"]
    state = pd.read_csv(a.state).set_index("division") if a.state and Path(a.state).exists() else pd.DataFrame(
        columns=["n_days", "sum_daily_mean"])
    parts, counts, new_state = [], [], []
    for dv in sorted(meta["divisions"]):
        f = Path(a.features) / f"{dv}.parquet"
        if not f.exists():
            continue
        X = pd.read_parquet(f).sort_values("cell").reset_index(drop=True)
        feats = meta["divisions"][dv]["features"]
        s = load_model(M, dv).predict(X.reindex(columns=feats)).astype(np.float32)
        cal = json.loads((M / "calibration" / f"{dv}.json").read_text())
        pct = 100 * np.interp(s, cal["x"], cal["y"])
        n_days = int(state.n_days.get(dv, 0)) if len(state) else 0
        sum_mean = float(state.sum_daily_mean.get(dv, 0.0)) if len(state) else 0.0
        today = float(s.mean())
        share = rule["first_week_share"] if n_days < 7 else float(np.clip(rule["base_share"] * today / (sum_mean / n_days), *rule["share_clip"]))
        own = int(round(k * share * len(X)))
        new_state.append(dict(division=dv, n_days=n_days + 1, sum_daily_mean=sum_mean + today))
        q = X.quiet.to_numpy().astype(bool)
        fl = int(round(floor_f * own))
        nq = min(int(round(quiet_f * fl)), int(q.sum())); no = min(fl - nq, int((~q).sum())); nq = min(fl - no, int(q.sum()))
        flag = np.zeros(len(X), bool)
        for grp, n in ((q, nq), (~q, no)):
            idx = np.flatnonzero(grp)
            if n > 0:
                flag[idx[np.argsort(-s[idx], kind="stable")[:n]]] = True
        parts.append(pd.DataFrame({"cell": X.cell.to_numpy(), "division": dv, "pct": pct.astype(np.float32),
                                   "score": s, "quiet": q.astype(np.uint8), "flag": flag}))
        counts.append(dict(division=dv, squares=len(X), quiet_squares=int(q.sum()), own_count=own, floor=fl))
    D = pd.concat(parts, ignore_index=True)
    total = sum(c["own_count"] for c in counts)
    rest = max(total - int(D.flag.sum()), 0)
    order = np.argsort(-D.pct.to_numpy(), kind="stable")                     # statewide, best calibrated % first
    free_q = (~D.flag.to_numpy()) & (D.quiet.to_numpy() == 1); free_o = (~D.flag.to_numpy()) & (D.quiet.to_numpy() == 0)
    rq = min(int(round(quiet_f * rest)), int(free_q.sum()))
    pick = np.zeros(len(D), bool)
    for grp, n in ((free_q, rq), (free_o, rest - rq)):
        o = order[grp[order]]
        pick[o[:n]] = True
    D["flag"] = (D.flag.to_numpy() | pick).astype(np.uint8)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    D.to_parquet(out / f"flags_{a.date}.parquet", index=False)
    C = pd.DataFrame(counts).merge(D.groupby("division").agg(flags=("flag", "sum"),
                                                             quiet_flags=("quiet", lambda x: int((x * D.loc[x.index, "flag"]).sum()))).reset_index(), on="division")
    C.to_csv(out / f"counts_{a.date}.csv", index=False)
    pd.DataFrame(new_state).to_csv(out / "season_state.csv", index=False)
    print(a.date, "squares", len(D), "flags", int(D.flag.sum()), "quiet share", round(float(D.flag[D.quiet == 1].sum() / max(D.flag.sum(), 1)), 3))


if __name__ == "__main__":
    main()
