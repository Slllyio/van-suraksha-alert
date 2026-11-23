"""Build the ignition dataset: one row per (season, cell, clear-look window (s, e]).

label_ign = 1 if a NEW-ignition scar patch (no earlier burn within NEW_R m, see patches.py) first shows
in this cell with window_end in (s, e]; spread = 1 if any other patch does (such rows are masked from the
ignition fit: the cell was being burnt anyway). Exposure = e - s days. Features are window means of the
daily drivers. Also writes a daily feature table used to score forecasts day by day.
Usage: python build_windows.py <ign_dir> <patch_dir> <labels_dir> <out_dir>
"""
import os, sys, datetime as dt
import numpy as np, pandas as pd

NEW_R = 1000           # a patch is a new ignition if no burn within 1 km in the previous week
MIN_CLEAR = 0.5        # a cell counts as "seen" on a date if this share of its eligible pixels was clear
MAX_GAP = 20
HOLI = {2017: "03-13", 2018: "03-02", 2019: "03-21", 2020: "03-10", 2021: "03-29", 2022: "03-18",
        2023: "03-08", 2024: "03-25", 2025: "03-14", 2026: "03-03"}
SEASON_END = "06-20"


def daily_drivers(ign_dir, patches, years):
    """One row per calendar day of each season: weather, calendar and sanctuary-wide recent fire."""
    w = pd.read_csv(os.path.join(ign_dir, "weather_power_2017_2026.csv"), parse_dates=["date"]).set_index("date")
    w["rain"] = w.PRECTOTCORR
    w["days_since_rain"] = (w.rain < 2).groupby((w.rain >= 2).cumsum()).cumsum()
    w["rh_min7"] = w.RH2M.rolling(7, min_periods=1).min()
    w["tmax7"] = w.T2M_MAX.rolling(7, min_periods=1).mean()
    w["rain30"] = w.rain.rolling(30, min_periods=1).sum()
    out = []
    for y in years:
        days = pd.date_range(f"{y}-01-01", f"{y}-{SEASON_END}")
        d = w.reindex(days).copy()
        d["season"] = y; d["doy"] = days.dayofyear; d["dow"] = days.dayofweek
        d["weekend"] = (d.dow >= 5).astype(int)
        holi = pd.Timestamp(f"{y}-{HOLI[y]}")
        d["days_to_holi"] = (days - holi).days
        d["holi_week"] = (abs(d.days_to_holi) <= 3).astype(int)
        d["mahua"] = ((days >= f"{y}-03-01") & (days <= f"{y}-04-15")).astype(int)
        d["tendu"] = ((days >= f"{y}-04-20") & (days <= f"{y}-05-25")).astype(int)
        # sanctuary-wide fire in the 7 days before each day, from scars (what was known that morning)
        p = patches[patches.season == y]
        pe = pd.to_datetime(p.window_end)
        act = pd.Series(0.0, index=days); nign = pd.Series(0.0, index=days)
        for e, ha, new in zip(pe, p.ha, p[f"new_{NEW_R}"]):
            lo, hi = e + pd.Timedelta(days=1), e + pd.Timedelta(days=7)
            act[lo:hi] += ha; nign[lo:hi] += new
        d["ha_7d"] = act.values; d["n_new_7d"] = nign.values
        d["log_ha_7d"] = np.log1p(d.ha_7d)
        out.append(d.reset_index().rename(columns={"index": "date"}))
    return pd.concat(out, ignore_index=True)


def main(ign_dir, patch_dir, labels_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    patches = pd.read_csv(os.path.join(patch_dir, "patches.csv"))
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv"))
    fuel = pd.read_csv(os.path.join(ign_dir, "fuel_age.csv"))
    cell_px = np.load(os.path.join(ign_dir, "cell_px.npy"))
    cal = pd.read_parquet(os.path.join(labels_dir, "clear_calendar.parquet"))
    years = sorted(patches.season.unique())
    drivers = daily_drivers(ign_dir, patches, years)
    drivers.to_csv(os.path.join(out_dir, "daily_drivers.csv"), index=False)
    # patch -> cells (pixel counts)
    pc = []
    for y in years:
        pid = np.load(os.path.join(patch_dir, f"patch_id_{y}.npy"))
        m = (pid > 0) & (cell_px >= 0)
        g = pd.DataFrame(dict(patch=pid[m], cell_id=cell_px[m])).groupby(["patch", "cell_id"]).size().rename("px").reset_index()
        g["season"] = y; pc.append(g)
    pc = pd.concat(pc).merge(patches[["season", "patch", "window_start", "window_end", f"new_{NEW_R}", "ha"]], on=["season", "patch"])
    pc.to_csv(os.path.join(out_dir, "patch_cells.csv"), index=False)
    # cell windows from the clear calendar
    cal = cal[cal.clear_frac >= MIN_CLEAR].copy()
    cal["date"] = pd.to_datetime(cal.date)
    cal = cal.sort_values(["season", "cell_id", "date"]).drop_duplicates(["season", "cell_id", "date"])
    cal["prev"] = cal.groupby(["season", "cell_id"]).date.shift()
    win = cal.dropna(subset=["prev"]).rename(columns={"prev": "s", "date": "e"})
    win["gap"] = (win.e - win.s).dt.days
    win = win[(win.gap <= MAX_GAP) & (win.e >= pd.to_datetime(win.season.astype(str) + "-01-01")) &
              (win.e <= pd.to_datetime(win.season.astype(str) + "-" + SEASON_END))][["season", "cell_id", "s", "e", "gap"]]
    # labels: a patch belongs to the cell window with s < window_end <= e
    pc["we"] = pd.to_datetime(pc.window_end)
    lab = win.merge(pc[["season", "cell_id", "we", f"new_{NEW_R}", "px"]], on=["season", "cell_id"], how="left")
    hit = (lab.we > lab.s) & (lab.we <= lab.e)
    lab = lab[hit].groupby(["season", "cell_id", "s", "e"]).agg(
        ign=(f"new_{NEW_R}", "max"), spread_px=("px", lambda v: int(v.sum())),
        ign_px=("px", "sum")).reset_index()
    win = win.merge(lab, on=["season", "cell_id", "s", "e"], how="left").fillna({"ign": 0, "spread_px": 0, "ign_px": 0})
    # patch that is "new" at 1 km but the cell also had other burns in this window: keep as ignition
    win["spread"] = ((win.spread_px > 0) & (win.ign == 0)).astype(int)
    win["ign"] = win.ign.astype(int)
    # fraction of the cell already burned this season before s (fuel gone)
    pc2 = pc[["season", "cell_id", "we", "px"]]
    cnt = cells.set_index("cell_id").elig_ha * 25  # eligible pixels
    done = win.merge(pc2, on=["season", "cell_id"], how="left")
    done = done[done.we <= done.s].groupby(["season", "cell_id", "s", "e"]).px.sum().rename("burned_px_before")
    win = win.merge(done.reset_index(), on=["season", "cell_id", "s", "e"], how="left").fillna({"burned_px_before": 0})
    win["frac_burned_season"] = (win.burned_px_before / win.cell_id.map(cnt).clip(lower=1)).clip(0, 1)
    # window-mean drivers
    dcols = ["T2M_MAX", "RH2M", "WS10M", "rain", "days_since_rain", "rh_min7", "tmax7", "rain30", "doy", "weekend",
             "holi_week", "mahua", "tendu", "log_ha_7d", "n_new_7d"]
    dd = drivers.set_index(["season", "date"])[dcols]
    rows = []
    for (y, s, e), grp in win.groupby(["season", "s", "e"]):
        days = pd.date_range(s + pd.Timedelta(days=1), e)
        m = dd.loc[y].reindex(days).mean()
        rows.append(pd.DataFrame([m.values] * len(grp), columns=dcols, index=grp.index))
    win = pd.concat([win, pd.concat(rows)], axis=1)
    win = win.merge(cells, on="cell_id").merge(fuel, on=["season", "cell_id"])
    win = win[win.elig_ha >= 5]
    win.to_parquet(os.path.join(out_dir, "cell_windows.parquet"), index=False)
    print("windows", len(win), "ign", int(win.ign.sum()), "spread", int(win.spread.sum()),
          "median gap", win.gap.median())
    print(win.groupby("season").agg(n=("ign", "size"), ign=("ign", "sum"), spread=("spread", "sum")).T)


if __name__ == "__main__":
    main(*sys.argv[1:5])
