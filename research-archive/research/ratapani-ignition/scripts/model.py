"""Ignition-rate model (Poisson, interval-censored) and its scoring.

Fit: LightGBM with a Poisson objective on cell windows (label = new ignition in the window, offset =
log(window days)); spread-burn windows are left out. Predict a daily rate per cell for the test seasons,
rank cells inside each pseudo-beat per day, keep the top BUDGET, and ask of every new-ignition patch:
was one of its cells on the list on the last day it was seen unburned (strict) or on any day of its date
window (lenient)? Baselines: random, long-run burn frequency of the cell, and sanctuary-level activity only.
Usage: python model.py <data_dir> <ign_dir> <out_dir> [test_seasons=2025,2026]
"""
import os, sys, json
import numpy as np, pandas as pd, lightgbm as lgb

BUDGET = 5
STATIC = ["tree", "shrub", "grass", "crop", "elev", "slope", "northness", "eastness", "d_built", "d_crop", "d_edge", "d_aoi"]
FUEL = ["age_mean", "frac_burned_last", "frac_burned_3y", "frac_never", "frac_burned_season"]
WEATHER = ["T2M_MAX", "RH2M", "WS10M", "rain", "days_since_rain", "rh_min7", "tmax7", "rain30"]
CALENDAR = ["doy", "weekend", "holi_week", "mahua", "tendu"]
ACTIVITY = ["log_ha_7d", "n_new_7d"]
TERRAIN_WX = ["insol", "insol_dry", "insol_tmax"]          # within-beat weather proxy from slope/aspect
S2 = ["ndmi_last", "nbr_last", "ndvi_last", "ndmi_anom", "s2_age"]  # satellite fuel moisture before the window
GROUPS = dict(static=STATIC, fuel=FUEL, weather=WEATHER, calendar=CALENDAR, activity=ACTIVITY)
ALL = STATIC + FUEL + WEATHER + CALENDAR + ACTIVITY


ERA5 = ["e_tmax", "e_rh_min", "e_rh_pm", "e_ws_pm", "e_rain", "e_soil", "e_rad", "e_dry_days", "e_rh_min7", "e_tmax7"]


def add_era5(df, ign_dir, date_col, end_col=None):
    """Per-cell weather from the nearest ERA5-Land 0.1 deg point (33 points over the sanctuary), as window
    means (end_col given) or day values."""
    pts = pd.read_parquet(os.path.join(ign_dir, "era5_daily_points.parquet")).sort_values(["point_id", "date"])
    pts["dry_days"] = pts.groupby("point_id").rain.transform(lambda r: (r < 2).groupby((r >= 2).cumsum()).cumsum())
    pts["rh_min7"] = pts.groupby("point_id").rh_min.transform(lambda v: v.rolling(7, min_periods=1).min())
    pts["tmax7"] = pts.groupby("point_id").tmax.transform(lambda v: v.rolling(7, min_periods=1).mean())
    cols = ["tmax", "rh_min", "rh_pm", "ws_pm", "rain", "soil", "rad", "dry_days", "rh_min7", "tmax7"]
    cp = pd.read_csv(os.path.join(ign_dir, "cell_point.csv")).set_index("cell_id").point_id
    df["point_id"] = df.cell_id.map(cp).values
    if end_col is None:
        m = df[["point_id", date_col]].merge(pts[["point_id", "date"] + cols], left_on=["point_id", date_col],
                                             right_on=["point_id", "date"], how="left")
        vals = m[cols].values
    else:
        # window means via per-point cumulative sums over a daily calendar
        cal = pd.date_range(pts.date.min(), pts.date.max())
        wide = {c: pts.pivot(index="date", columns="point_id", values=c).reindex(cal).ffill() for c in cols}
        cum = {c: np.vstack([np.zeros((1, wide[c].shape[1])), np.nancumsum(wide[c].values, axis=0)]) for c in cols}
        pid_col = {p: i for i, p in enumerate(wide[cols[0]].columns)}
        i0 = (pd.to_datetime(df[date_col]) - cal[0]).dt.days.values + 1      # days s+1 .. e
        i1 = (pd.to_datetime(df[end_col]) - cal[0]).dt.days.values + 1
        pj = df.point_id.map(pid_col).values
        n = np.maximum(i1 - i0 + 1, 1)
        vals = np.column_stack([(cum[c][i1, pj] - cum[c][i0 - 1, pj]) / n for c in cols])
    for k, c in zip(ERA5, cols):
        df[k] = vals[:, cols.index(c)]
    return df


def add_cell_features(df, ign_dir, s2, s2_mean, date_col, end_col=None):
    """Per-cell-day (or per-cell-window) insolation and last satellite dryness. df has season, cell_id,
    date_col (a day, or the window start s) and, for windows, end_col e; RH2M and T2M_MAX present."""
    ins = np.load(os.path.join(ign_dir, "insolation.npy"))
    idx = pd.read_csv(os.path.join(ign_dir, "insolation_cells.csv")).cell_id
    row = pd.Series(np.arange(len(idx)), index=idx.values)
    cum = np.concatenate([np.zeros((ins.shape[0], 1)), np.cumsum(ins, axis=1)], axis=1)  # cum[:, d] = sum doy 1..d
    r = row.reindex(df.cell_id).values
    y0 = pd.to_datetime(df.season.astype(str) + "-01-01")
    d1 = (pd.to_datetime(df[date_col]) - y0).dt.days.clip(0, 171).values
    if end_col is None:
        df["insol"] = ins[r, np.minimum(d1, 171)]
    else:
        d2 = (pd.to_datetime(df[end_col]) - y0).dt.days.clip(1, 172).values
        df["insol"] = (cum[r, d2] - cum[r, d1]) / np.maximum(d2 - d1, 1)
    df["insol_dry"] = df.insol * (100 - df.RH2M)
    df["insol_tmax"] = df.insol * df.T2M_MAX
    # last clear satellite look at or before the day / window start, within 30 days
    key = pd.to_datetime(df[date_col])
    tmp = df[["season", "cell_id"]].copy(); tmp["key"] = key.values; tmp["_i"] = np.arange(len(df))
    tmp = tmp.sort_values("key")
    s2s = s2.assign(s2date=s2.date).rename(columns={"date": "key"}).sort_values("key")
    m = pd.merge_asof(tmp, s2s, on="key", by=["season", "cell_id"], direction="backward", tolerance=pd.Timedelta(days=30))
    m = m.sort_values("_i")
    df["ndmi_last"] = m.ndmi.values; df["nbr_last"] = m.nbr.values; df["ndvi_last"] = m.ndvi.values
    df["ndmi_anom"] = df.ndmi_last - df.cell_id.map(s2_mean).values
    df["s2_age"] = (key.values - m.s2date.values).astype("timedelta64[D]").astype(float) if "s2date" in m else np.nan
    return df
PARAMS = dict(objective="poisson", learning_rate=0.03, num_leaves=15, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, seed=0)


def fit(train, feats, rounds=600):
    d = lgb.Dataset(train[feats], label=train.ign, init_score=np.log(train.gap.values))
    return lgb.train(PARAMS, d, rounds)


def daily_table(drivers, cells, fuel, windows, seasons):
    """Cell x day rows for the test seasons with the same feature columns as the windows."""
    out = []
    for y in seasons:
        d = drivers[drivers.season == y]
        c = cells.merge(fuel[fuel.season == y].drop(columns="season"), on="cell_id")
        t = d.assign(k=1).merge(c.assign(k=1), on="k").drop(columns="k")
        # fraction of the cell burned so far this season, from the windows table (step function in time)
        w = windows[windows.season == y][["cell_id", "s", "frac_burned_season"]].sort_values("s")
        t = pd.merge_asof(t.sort_values("date"), w.rename(columns={"s": "date"}), on="date", by="cell_id", direction="backward")
        t["frac_burned_season"] = t.frac_burned_season.fillna(0)
        out.append(t)
    return pd.concat(out, ignore_index=True)


def score(daily, pc, pred_col):
    """Recall of new-ignition patches at BUDGET cells per beat per day. A patch counts by its main cell
    (the one holding most of its pixels), scored on the last day it was seen unburned (strict) or on any
    day of its date window (lenient). "any_cell" lets any cell the patch touches count (generous for big patches)."""
    daily = daily.copy()
    daily["rank"] = daily.groupby(["season", "date", "beat"])[pred_col].rank("first", ascending=False)
    listed = daily[daily["rank"] <= BUDGET][["season", "date", "cell_id"]]
    listed_set = set(zip(listed.season, listed.date, listed.cell_id))
    p = pc[pc.new == 1]
    strict = lenient = anyc = 0; n = 0
    for (y, patch), g in p.groupby(["season", "patch"]):
        s, e = pd.Timestamp(g.window_start.iloc[0]), pd.Timestamp(g.window_end.iloc[0])
        main_cell = g.sort_values("px").cell_id.iloc[-1]
        n += 1
        strict += (y, s, main_cell) in listed_set
        lenient += any((y, t, main_cell) in listed_set for t in pd.date_range(s, e - pd.Timedelta(days=1)))
        anyc += any((y, s, c) in listed_set for c in set(g.cell_id))
    return dict(patches=n, strict=strict / n, lenient=lenient / n, any_cell=anyc / n)


def when_score(daily, pc, pred_col):
    """Does the sanctuary-wide daily rate track when new ignitions happen? Each new-ignition patch is
    spread evenly over its date window; compare with the summed predicted rate per day (Spearman)."""
    from scipy.stats import spearmanr
    tot = daily.groupby(["season", "date"])[pred_col].sum()
    obs = pd.Series(0.0, index=tot.index)
    for (y, patch), g in pc[pc.new == 1].groupby(["season", "patch"]):
        s, e = pd.Timestamp(g.window_start.iloc[0]), pd.Timestamp(g.window_end.iloc[0])
        days = pd.date_range(s + pd.Timedelta(days=1), e)
        for t in days:
            if (y, t) in obs.index:
                obs[(y, t)] += 1 / len(days)
    out = {}
    for y in tot.index.get_level_values(0).unique():
        out[int(y)] = float(spearmanr(tot.loc[y], obs.loc[y]).correlation)
    return out


def main(data_dir, ign_dir, out_dir, test="2025,2026"):
    os.makedirs(out_dir, exist_ok=True)
    test = [int(v) for v in test.split(",")]
    win = pd.read_parquet(os.path.join(data_dir, "cell_windows.parquet"))
    drivers = pd.read_csv(os.path.join(data_dir, "daily_drivers.csv"), parse_dates=["date"])
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv"))
    fuel = pd.read_csv(os.path.join(ign_dir, "fuel_age.csv"))
    pc = pd.read_csv(os.path.join(data_dir, "patch_cells.csv")).rename(columns=lambda c: "new" if c.startswith("new_") else c)
    pc = pc[pc.cell_id.isin(cells[cells.elig_ha >= 5].cell_id)]
    s2 = pd.read_parquet(os.path.join(ign_dir, "s2_cells.parquet"))
    s2_mean = s2[~s2.season.isin(test)].groupby("cell_id").ndmi.mean()
    win = add_cell_features(win, ign_dir, s2, s2_mean, "s", "e")
    if os.environ.get("ERA5"):
        win = add_era5(win, ign_dir, "s", "e")
    fitrows = win[win.spread == 0]
    train, hold = fitrows[~fitrows.season.isin(test)], fitrows[fitrows.season.isin(test)]
    daily = daily_table(drivers, cells[cells.elig_ha >= 5], fuel, win, test)
    daily = add_cell_features(daily, ign_dir, s2, s2_mean, "date")
    if os.environ.get("ERA5"):
        daily = add_era5(daily, ign_dir, "date")
    pct = pc[pc.season.isin(test)]
    res = {}
    # baselines
    rng = np.random.default_rng(0)
    daily["random"] = rng.random(len(daily))
    freq = win[~win.season.isin(test)].groupby("cell_id").apply(lambda g: (g.ign.sum() + g.spread_px.gt(0).sum()) / g.gap.sum())
    daily["burn_freq"] = daily.cell_id.map(freq).fillna(0)
    res["random"] = score(daily, pct, "random")
    res["burn_frequency"] = score(daily, pct, "burn_freq")
    # "when" baseline: a seasonal curve only (mean ignitions by day of year over the training seasons)
    doy_model = fit(train, ["doy"], 200); daily["doy_only"] = doy_model.predict(daily[["doy"]])
    res["doy_only"] = dict(when_spearman=when_score(daily, pct, "doy_only"))
    print("doy_only", res["doy_only"], flush=True)
    # models: all features, then drop one group at a time
    configs = [("all", ALL), ("all+terrain_wx", ALL + TERRAIN_WX), ("all+s2", ALL + S2), ("all+both", ALL + TERRAIN_WX + S2)]
    if os.environ.get("ERA5"):
        NOWX = [f for f in ALL if f not in WEATHER]
        configs = [("all", ALL), ("era5_instead_of_power", NOWX + ERA5), ("era5_plus_power", ALL + ERA5)]
    if os.environ.get("ABLATE"):
        configs += [(f"no_{g}", [f for f in ALL if f not in fs]) for g, fs in GROUPS.items()] + [("static_fuel_only", STATIC + FUEL)]
    for name, feats in configs:
        m = fit(train, feats)
        daily[name] = m.predict(daily[feats])
        r = score(daily, pct, name)
        r["when_spearman"] = when_score(daily, pct, name)
        # held-out Poisson deviance on windows, lower is better
        mu = m.predict(hold[feats]) * hold.gap.values
        y = hold.ign.values
        with np.errstate(divide="ignore", invalid="ignore"):
            dev = 2 * np.nansum(np.where(y > 0, y * np.log(y / mu), 0) - (y - mu))
        r["deviance"] = float(dev)
        res[name] = r
        print(name, {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}, flush=True)
        imp = pd.Series(m.feature_importance("gain"), index=feats).sort_values(ascending=False)
        imp.to_csv(os.path.join(out_dir, f"importance_{name}.csv"))
        if name == "all":
            m.save_model(os.path.join(out_dir, "ignition_all.txt"))
            # calendar effects: predicted rate ratio when a flag is on vs off, other things equal
            eff = {}
            for f in ["weekend", "holi_week", "mahua", "tendu"]:
                a, b = hold.copy(), hold.copy(); a[f] = 1; b[f] = 0
                eff[f] = float(m.predict(a[feats]).mean() / m.predict(b[feats]).mean())
            res["rate_ratio_flag_on_vs_off"] = eff
            print("rate ratios", {k: round(v, 2) for k, v in eff.items()})
    daily[["season", "date", "cell_id", "beat", "all", "burn_freq", "random"]].to_parquet(os.path.join(out_dir, "daily_pred.parquet"), index=False)
    json.dump(res, open(os.path.join(out_dir, os.environ.get("RESULTS", "results.json")), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if isinstance(v, dict) and "strict" in v}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
