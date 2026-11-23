"""Spread model: given the burns seen in the last week, which nearby cells burn next?

Exposure, for a cell on day t: the nearest scar patch whose window closed in [t-7, t] (a burn known that
morning) within 3 km, with its distance, bearing, size and age, the alignment of that bearing with the
afternoon wind (downwind = 1, upwind = -1), the elevation difference, and the burnt area within 2 km in the
last 7 days. Fit (Poisson, offset log days) on exposed cell windows; label = any scar first showing in the
window. Score on 2025-26: spread patches (not new ignitions) caught at 5 cells per beat per day, ranking
only exposed cells, on the last day the patch's main cell was seen unburned.
Usage: python spread.py <data_dir> <ign_dir> <out_dir> [test=2025,2026]
"""
import os, sys, json
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M

R_EXPOSED = 3000; LOOK = 7
EXPO = ["dist_front", "downwind", "front_ha", "front_age", "ha_2km_7d", "delev", "cos_asp_front"]
LOCAL = M.STATIC + M.FUEL
WX = M.WEATHER + ["ws_pm"] + M.CALENDAR + M.ACTIVITY
PARAMS = dict(M.PARAMS)


def cell_xy(ign_dir):
    cell = np.load(os.path.join(ign_dir, "cell_px.npy"))
    sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts")
    import fetch
    r, c = np.where(fetch.INSIDE)
    ok = cell >= 0
    n = cell.max() + 1
    cnt = np.bincount(cell[ok], minlength=n)
    return pd.DataFrame(dict(cell_id=np.arange(n), row=np.bincount(cell[ok], weights=r[ok], minlength=n) / np.maximum(cnt, 1),
                             col=np.bincount(cell[ok], weights=c[ok], minlength=n) / np.maximum(cnt, 1)))


def exposure(df, date_col, patches, xy, elev, wd):
    """Add EXPO columns to df (season, cell_id, date_col). wd: Series date -> afternoon wind direction (deg, from)."""
    out = {k: np.full(len(df), np.nan) for k in EXPO}
    pe = pd.to_datetime(patches.window_end)
    key = pd.to_datetime(df[date_col])
    idx_all = np.arange(len(df))
    for (y, t), ii in pd.Series(idx_all).groupby([df.season.values, key.values]).groups.items():
        ii = np.asarray(ii)
        t = pd.Timestamp(t)
        lag = 1 if os.environ.get("LEAKSAFE") else 0   # LEAKSAFE: only scars seen on images up to t-1
        p = patches[(patches.season == y) & (pe >= t - pd.Timedelta(days=LOOK)) & (pe <= t - pd.Timedelta(days=lag))]
        if len(p) == 0:
            continue
        px = np.c_[p.col.values * 20, -p.row.values * 20]  # metres, y up
        tree = cKDTree(px)
        cx = np.c_[xy.loc[df.cell_id.values[ii], "col"].values * 20, -xy.loc[df.cell_id.values[ii], "row"].values * 20]
        d, j = tree.query(cx, k=1, distance_upper_bound=R_EXPOSED)
        ok = np.isfinite(d)
        if not ok.any():
            continue
        jj = j[ok]; sel = ii[ok]
        src = p.iloc[jj]
        out["dist_front"][sel] = d[ok]
        out["front_ha"][sel] = src.ha.values
        out["front_age"][sel] = (t - pd.to_datetime(src.window_end)).dt.days.values
        bearing = np.degrees(np.arctan2(cx[ok, 0] - px[jj, 0], cx[ok, 1] - px[jj, 1])) % 360  # from front to cell, 0 = N
        wdir = wd.get(t, np.nan)                       # wind FROM direction; fire travels toward wdir + 180
        out["downwind"][sel] = np.cos(np.radians(bearing - (wdir + 180)))
        out["delev"][sel] = elev.loc[df.cell_id.values[sel]].values - elev.reindex(src.cell_id.values).values
        asp = np.degrees(np.arctan2(xy.loc[df.cell_id.values[sel], "east"].values, xy.loc[df.cell_id.values[sel], "north"].values)) % 360
        out["cos_asp_front"][sel] = np.cos(np.radians(asp - (bearing + 180)))  # does the cell face the front?
        # burnt area within 2 km in the last 7 days
        near = tree.query_ball_point(cx[ok], 2000)
        out["ha_2km_7d"][sel] = [p.ha.values[n_].sum() for n_ in near]
    for k in EXPO:
        df[k] = out[k]
    return df


def score(daily, pc, pred_col):
    daily = daily[daily.dist_front.notna()].copy()
    daily["rank"] = daily.groupby(["season", "date", "beat"])[pred_col].rank("first", ascending=False)
    listed = daily[daily["rank"] <= M.BUDGET]
    listed_set = set(zip(listed.season, listed.date, listed.cell_id))
    p = pc[pc.new == 0]
    hit = n = 0
    for (y, patch), g in p.groupby(["season", "patch"]):
        s = pd.Timestamp(g.window_start.iloc[0]); mc = g.sort_values("px").cell_id.iloc[-1]
        n += 1; hit += (y, s, mc) in listed_set
    return dict(patches=n, strict=hit / n)


def main(data_dir, ign_dir, out_dir, test="2025,2026"):
    os.makedirs(out_dir, exist_ok=True)
    test = [int(v) for v in test.split(",")]
    win = pd.read_parquet(os.path.join(data_dir, "cell_windows.parquet"))
    drivers = pd.read_csv(os.path.join(data_dir, "daily_drivers.csv"), parse_dates=["date"])
    wx = pd.read_csv(os.path.join(ign_dir, "weather_power_2017_2026.csv"), parse_dates=["date"]).set_index("date")
    if "ws_pm" not in drivers:
        drivers = drivers.merge(wx[["ws_pm"]], left_on="date", right_index=True, how="left")
    wd = wx.wd_pm
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv")); cells = cells[cells.elig_ha >= 5]
    fuel = pd.read_csv(os.path.join(ign_dir, "fuel_age.csv"))
    patches = pd.read_csv(os.path.join(ign_dir, "patches.csv")).rename(columns={"new_1000": "new"})
    pc = pd.read_csv(os.path.join(data_dir, "patch_cells.csv")).rename(columns=lambda c: "new" if c.startswith("new_") else c)
    xy = cell_xy(ign_dir).set_index("cell_id").join(cells.set_index("cell_id")[["northness", "eastness"]].rename(columns={"northness": "north", "eastness": "east"}))
    # a patch's source cell for elevation: the cell under its centroid
    cell_px = np.load(os.path.join(ign_dir, "cell_px.npy"))
    sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts"); import fetch
    full = np.full(fetch.INSIDE.shape, -1, np.int32); full[fetch.INSIDE] = cell_px
    patches["cell_id"] = full[patches.row.values, patches.col.values]
    elev = cells.set_index("cell_id").elev
    win = win.merge(wx[["ws_pm"]], left_on="s", right_index=True, how="left")
    win = exposure(win, "s", patches, xy, elev, wd)
    win["burn"] = ((win.ign == 1) | (win.spread_px > 0)).astype(int)
    ex = win[win.dist_front.notna() & (win.frac_burned_season < 0.9)]
    print("exposed windows", len(ex), "of", len(win), "burn rate", round(ex.burn.mean(), 3), "vs unexposed",
          round(win[win.dist_front.isna()].burn.mean(), 3), flush=True)
    train, hold = ex[~ex.season.isin(test)], ex[ex.season.isin(test)]
    daily = M.daily_table(drivers, cells, fuel, win, test)
    daily = exposure(daily, "date", patches, xy, elev, wd)
    pct = pc[pc.season.isin(test) & pc.cell_id.isin(cells.cell_id)]
    res = {}
    rng = np.random.default_rng(0); daily["random"] = rng.random(len(daily))
    daily["closest"] = -daily.dist_front
    res["random_among_exposed"] = score(daily, pct, "random")
    res["closest_front_first"] = score(daily, pct, "closest")
    print(res, flush=True)
    for name, feats in [("exposure_only", EXPO), ("exposure+local", EXPO + LOCAL), ("all", EXPO + LOCAL + WX),
                        ("all_no_wind", [f for f in EXPO + LOCAL + WX if f not in ("downwind", "ws_pm", "WS10M")])]:
        d = lgb.Dataset(train[feats], label=train.burn, init_score=np.log(train.gap.values))
        m = lgb.train(dict(PARAMS, objective="poisson"), d, 600)
        daily[name] = m.predict(daily[feats])
        r = score(daily, pct, name)
        from sklearn.metrics import roc_auc_score
        r["holdout_auc_windows"] = float(roc_auc_score(hold.burn, m.predict(hold[feats]) * hold.gap.values))
        res[name] = r; print(name, r, flush=True)
        if name == "all":
            pd.Series(m.feature_importance("gain"), index=feats).sort_values(ascending=False).to_csv(os.path.join(out_dir, "spread_importance.csv"))
            # directional effects, other things equal
            for f, lo, hi in [("downwind", -1, 1), ("delev", -50, 50), ("cos_asp_front", -1, 1)]:
                a, b = hold.copy(), hold.copy(); a[f] = hi; b[f] = lo
                res[f"rate_ratio_{f}_{hi}_vs_{lo}"] = float(m.predict(a[feats]).mean() / m.predict(b[feats]).mean())
    # how spread probability falls with distance and rises with wind alignment (observed)
    obs = {}
    for lab, bins in [("dist_front", [0, 500, 1000, 1500, 2000, 3000]), ("downwind", [-1, -0.5, 0, 0.5, 1.01]), ("front_age", [-1, 1, 3, 5, 7])]:
        g = ex.groupby(pd.cut(ex[lab], bins), observed=True)
        obs[lab] = {str(k): [round(float(v), 4), int(c)] for k, v, c in zip(g.burn.mean().index, g.burn.sum() / g.gap.sum(), g.size())}
    res["observed_burn_per_cell_day"] = obs
    json.dump(res, open(os.path.join(out_dir, "spread_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
