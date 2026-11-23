"""Budget trade-off: can new ignitions and spread both be caught with 5 picks per beat per day?
Uses the per-cell-day rates saved by combined.py (daily_pred_combined.parquet).
  quota k   : k of the 5 picks by ignition rate (all cells), 5-k by spread rate (cells within 3 km of a front)
  dynamic   : same total picks per day (68 beats x 5) but shared between beats in proportion to the beat's summed rate
  budget b  : plain top-b per beat for b in 3, 5, 8, 10 (how recall grows with effort)
"""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import model as M, combined as C

def listed_set(d, rank_col, budget):
    return set(zip(d.season[d[rank_col] <= budget], d.date[d[rank_col] <= budget], d.cell_id[d[rank_col] <= budget]))

def score_set(ls, pc, cw):
    out = {}
    for lab, sub in [("all", pc), ("new", pc[pc.new == 1]), ("spread", pc[pc.new == 0])]:
        hit = n = 0
        for (y, patch), g in sub.groupby(["season", "patch"]):
            s = pd.Timestamp(g.window_start.iloc[0]); mc = g.sort_values("px").cell_id.iloc[-1]
            n += 1; hit += (y, s, mc) in ls
        out[f"strict_{lab}"] = round(hit / n, 4)
    hit = np.array([(y, s, c) in ls for y, s, c in zip(cw.season, cw.s, cw.cell_id)])
    out["cell_recall"] = round(float(hit.mean()), 4); out["area_recall"] = round(float((hit * cw.px).sum() / cw.px.sum()), 4)
    out["picks_per_day"] = round(len(ls) / max(1, len({(a, b) for a, b, _ in ls})), 1)
    return out

def main(data_dir, ign_dir, out_dir, test="2025,2026"):
    test = [int(v) for v in test.split(",")]
    d = pd.read_parquet(os.path.join(out_dir, "daily_pred_combined.parquet"))
    d["exposed"] = (d.two_model != d.ignition_feats).astype(int)
    d["spread_rate"] = np.where(d.exposed == 1, d.two_model, -1.0)
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv")); cells = cells[cells.elig_ha >= 5]
    pc = pd.read_csv(os.path.join(data_dir, "patch_cells.csv")).rename(columns=lambda c: "new" if c.startswith("new_") else c)
    pc = pc[pc.cell_id.isin(cells.cell_id) & pc.season.isin(test)]
    win = pd.read_parquet(os.path.join(data_dir, "cell_windows.parquet"))
    win = win[win.cell_id.isin(cells.cell_id) & win.season.isin(test) & (win.frac_burned_season < 0.9)]
    win["burn"] = ((win.ign == 1) | (win.spread_px > 0)).astype(int)
    cw = win[win.burn == 1][["season", "s", "cell_id"]].copy(); cw["px"] = win.loc[cw.index, "spread_px"].clip(lower=1)
    g = d.groupby(["season", "date", "beat"])
    d["r_ign"] = g.ignition_feats.rank("first", ascending=False)
    d["r_spr"] = g.spread_rate.rank("first", ascending=False)
    d["r_comb"] = g.combined.rank("first", ascending=False)
    res = {}
    for b in [3, 5, 8, 10]:
        res[f"combined_top{b}"] = score_set(listed_set(d, "r_comb", b), pc, cw); print(f"combined_top{b}", res[f"combined_top{b}"], flush=True)
    for k in [1, 2, 3, 4]:
        # k ignition picks, then 5-k spread picks skipping cells already chosen (spread picks only where exposed)
        pick_i = d.r_ign <= k
        rest = d[~pick_i & (d.exposed == 1)]
        rr = rest.groupby(["season", "date", "beat"]).spread_rate.rank("first", ascending=False)
        pick_s = rest[rr <= 5 - k]
        # beats with too few exposed cells: fill from the ignition ranking
        n_s = pick_s.groupby(["season", "date", "beat"]).size()
        ls = set(zip(d.season[pick_i], d.date[pick_i], d.cell_id[pick_i])) | set(zip(pick_s.season, pick_s.date, pick_s.cell_id))
        short = (5 - k - n_s.reindex(d[["season", "date", "beat"]].drop_duplicates().set_index(["season", "date", "beat"]).index, fill_value=0))
        fill = d.merge(short.rename("short").reset_index(), on=["season", "date", "beat"])
        fill = fill[(fill.r_ign > k) & (fill.r_ign <= k + fill["short"])]
        ls |= set(zip(fill.season, fill.date, fill.cell_id))
        res[f"quota_ign{k}_spread{5-k}"] = score_set(ls, pc, cw); print(f"quota_ign{k}_spread{5-k}", res[f"quota_ign{k}_spread{5-k}"], flush=True)
    # dynamic: per day, allocate 5 x n_beats picks across beats in proportion to summed combined rate, min 1 max 15
    for col in ["combined", "ignition_feats"]:
        tot = d.groupby(["season", "date", "beat"])[col].sum().rename("tot").reset_index()
        tot["nb"] = tot.groupby(["season", "date"]).beat.transform("size")
        tot["share"] = tot.tot / tot.groupby(["season", "date"]).tot.transform("sum")
        tot["alloc"] = np.clip(np.round(tot.share * 5 * tot.nb), 1, 15)
        dd = d.merge(tot[["season", "date", "beat", "alloc"]], on=["season", "date", "beat"])
        rk = "r_comb" if col == "combined" else "r_ign"
        sel = dd[dd[rk] <= dd.alloc]
        ls = set(zip(sel.season, sel.date, sel.cell_id))
        res[f"dynamic_{col}"] = score_set(ls, pc, cw); print(f"dynamic_{col}", res[f"dynamic_{col}"], flush=True)
    json.dump(res, open(os.path.join(out_dir, "budget_results.json"), "w"), indent=1)

if __name__ == "__main__":
    main(*sys.argv[1:5])
