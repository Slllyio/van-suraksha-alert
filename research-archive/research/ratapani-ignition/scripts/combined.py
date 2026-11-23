"""One ranking per beat per day for ALL burning (new ignitions + spread), so the research thread's
numbers can be set beside the pipeline thread's 27.5 % (burnt cells caught at 5 checks per beat per day).

Models (Poisson rate of burning per cell-day, fit on every cell window):
  ignition_feats : landscape + fuel + weather + calendar + activity + terrain sunshine + satellite dryness
  combined       : ignition_feats + exposure to last-week fronts (NaN when no front within 3 km)
  two_model      : spread model where a front is within 3 km, ignition model elsewhere (rates are on the same scale)
Scores on 2025-26: patches caught (all / new / spread, main cell, strict day) and burnt cell-windows caught
(cell listed in its beat on the window's start day), which is the closest thing to the pipeline's cell-day recall.
"""
import os, sys, json
import numpy as np, pandas as pd, lightgbm as lgb
sys.path.insert(0, os.path.dirname(__file__))
import model as M, spread as S

FEATS_IGN = M.ALL + M.TERRAIN_WX + M.S2
FEATS_COMB = FEATS_IGN + S.EXPO + ["exposed"]
FEATS_SPR = S.EXPO + S.LOCAL + S.WX + M.S2


def score_all(daily, pc, pred_col, burnt_cw):
    d = daily.copy()
    d["rank"] = d.groupby(["season", "date", "beat"])[pred_col].rank("first", ascending=False)
    listed = d[d["rank"] <= M.BUDGET]
    ls = set(zip(listed.season, listed.date, listed.cell_id))
    out = {}
    for lab, sub in [("all", pc), ("new", pc[pc.new == 1]), ("spread", pc[pc.new == 0])]:
        hit = n = 0
        for (y, patch), g in sub.groupby(["season", "patch"]):
            s = pd.Timestamp(g.window_start.iloc[0]); mc = g.sort_values("px").cell_id.iloc[-1]
            n += 1; hit += (y, s, mc) in ls
        out[f"patches_{lab}"] = n; out[f"strict_{lab}"] = round(hit / n, 4)
    # burnt cell-windows, weighted equally (pipeline-like) and by burnt pixels (area)
    cw = burnt_cw
    hit = np.array([(y, s, c) in ls for y, s, c in zip(cw.season, cw.s, cw.cell_id)])
    out["cellwindows"] = int(len(cw)); out["cell_recall"] = round(float(hit.mean()), 4)
    out["area_recall"] = round(float((hit * cw.px).sum() / cw.px.sum()), 4)
    return out


def main(data_dir, ign_dir, out_dir, test="2025,2026"):
    test = [int(v) for v in test.split(",")]
    win = pd.read_parquet(os.path.join(data_dir, "cell_windows.parquet"))
    drivers = pd.read_csv(os.path.join(data_dir, "daily_drivers.csv"), parse_dates=["date"])
    wx = pd.read_csv(os.path.join(ign_dir, "weather_power_2017_2026.csv"), parse_dates=["date"]).set_index("date")
    if "ws_pm" not in drivers:
        drivers = drivers.merge(wx[["ws_pm"]], left_on="date", right_index=True, how="left")
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv")); cells = cells[cells.elig_ha >= 5]
    fuel = pd.read_csv(os.path.join(ign_dir, "fuel_age.csv"))
    patches = pd.read_csv(os.path.join(ign_dir, "patches.csv")).rename(columns={"new_1000": "new"})
    pc = pd.read_csv(os.path.join(data_dir, "patch_cells.csv")).rename(columns=lambda c: "new" if c.startswith("new_") else c)
    pc = pc[pc.cell_id.isin(cells.cell_id)]
    xy = S.cell_xy(ign_dir).set_index("cell_id").join(cells.set_index("cell_id")[["northness", "eastness"]].rename(columns={"northness": "north", "eastness": "east"}))
    cell_px = np.load(os.path.join(ign_dir, "cell_px.npy"))
    sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts"); import fetch
    full = np.full(fetch.INSIDE.shape, -1, np.int32); full[fetch.INSIDE] = cell_px
    patches["cell_id"] = full[patches.row.values, patches.col.values]
    elev = cells.set_index("cell_id").elev
    s2 = pd.read_parquet(os.path.join(ign_dir, "s2_cells.parquet"))
    s2_mean = s2[~s2.season.isin(test)].groupby("cell_id").ndmi.mean()

    win = win[win.cell_id.isin(cells.cell_id)]
    win = M.add_cell_features(win, ign_dir, s2, s2_mean, "s", "e")
    win = win.merge(wx[["ws_pm"]], left_on="s", right_index=True, how="left")
    win = S.exposure(win, "s", patches, xy, elev, wx.wd_pm)
    win["exposed"] = win.dist_front.notna().astype(int)
    win["burn"] = ((win.ign == 1) | (win.spread_px > 0)).astype(int)
    win = win[win.frac_burned_season < 0.9]
    train = win[~win.season.isin(test)]
    print("train windows", len(train), "burn rate", round(train.burn.mean(), 4), flush=True)

    daily = M.daily_table(drivers, cells, fuel, win, test)
    daily = M.add_cell_features(daily, ign_dir, s2, s2_mean, "date")
    daily = S.exposure(daily, "date", patches, xy, elev, wx.wd_pm)
    daily["exposed"] = daily.dist_front.notna().astype(int)
    pct = pc[pc.season.isin(test)]
    burnt = win[win.season.isin(test) & (win.burn == 1)][["season", "s", "cell_id"]].copy()
    burnt["px"] = win.loc[burnt.index, "spread_px"].clip(lower=1)  # ignition-only windows count 1
    print("test burnt cell-windows", len(burnt), flush=True)

    res = {}
    rng = np.random.default_rng(0); daily["random"] = rng.random(len(daily))
    freq = train.groupby("cell_id").apply(lambda g: g.burn.sum() / g.gap.sum())
    daily["burn_freq"] = daily.cell_id.map(freq).fillna(0)
    for b in ["random", "burn_freq"]:
        res[b] = score_all(daily, pct, b, burnt); print(b, res[b], flush=True)

    def fit(rows, feats):
        wgt = None
        if os.environ.get("WEIGHT"):
            # upweight the burn types the model misses: small scars (< 2 ha in the cell), low-forest cells, cells near villages
            small = rows.spread_px.clip(lower=1) * 0.04 < 2
            hard = (rows.burn == 1) & (small | (rows.elig_ha < 20) | (rows.d_built < 500))
            wgt = np.where(hard, float(os.environ["WEIGHT"]), 1.0)
            print("weighted burn rows", int(hard.sum()), "of", int((rows.burn == 1).sum()), flush=True)
        d = lgb.Dataset(rows[feats], label=rows.burn, init_score=np.log(rows.gap.values), weight=wgt)
        return lgb.train(M.PARAMS, d, 600)

    m_ign = fit(train, FEATS_IGN); daily["ignition_feats"] = m_ign.predict(daily[FEATS_IGN])
    res["ignition_feats"] = score_all(daily, pct, "ignition_feats", burnt); print("ignition_feats", res["ignition_feats"], flush=True)
    m_comb = fit(train, FEATS_COMB); daily["combined"] = m_comb.predict(daily[FEATS_COMB])
    res["combined"] = score_all(daily, pct, "combined", burnt); print("combined", res["combined"], flush=True)
    pd.Series(m_comb.feature_importance("gain"), index=FEATS_COMB).sort_values(ascending=False).to_csv(os.path.join(out_dir, "combined_importance.csv"))
    if os.environ.get("WEIGHT"):
        daily[["season", "date", "cell_id", "beat", "combined", "ignition_feats"]].to_parquet(os.path.join(out_dir, "daily_pred_weighted.parquet"), index=False)
        json.dump(res, open(os.path.join(out_dir, "combined_results_weighted.json"), "w"), indent=1); return
    m_spr = fit(train[train.exposed == 1], FEATS_SPR)
    spr = m_spr.predict(daily[FEATS_SPR])
    daily["two_model"] = np.where(daily.exposed == 1, spr, daily.ignition_feats)
    res["two_model"] = score_all(daily, pct, "two_model", burnt); print("two_model", res["two_model"], flush=True)
    # calibration of the combined model on held-out: predicted vs observed burns by decile of predicted daily rate
    hold = win[win.season.isin(test)]
    mu = m_comb.predict(hold[FEATS_COMB]) * hold.gap.values
    q = pd.qcut(mu, 10, labels=False, duplicates="drop")
    cal = pd.DataFrame(dict(pred=mu, obs=hold.burn.values)).groupby(q).agg(pred=("pred", "sum"), obs=("obs", "sum"), n=("obs", "size"))
    res["calibration_deciles"] = cal.round(1).to_dict("index")
    print(cal.round(1), flush=True)
    daily[["season", "date", "cell_id", "beat", "combined", "two_model", "ignition_feats"]].to_parquet(os.path.join(out_dir, "daily_pred_combined.parquet"), index=False)
    json.dump(res, open(os.path.join(out_dir, "combined_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:5])
