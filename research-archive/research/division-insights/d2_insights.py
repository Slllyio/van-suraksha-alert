# Division insights from 9 seasons (2017-25) of MP forest fire events. Every pattern gets a null or a consistency check.
# Writes results.json and per-division tables (div_*.csv).
import json
import numpy as np, pandas as pd
from pathlib import Path
from scipy import stats
from scipy.spatial import cKDTree
D = Path(__file__).parent
e = pd.read_parquet(D / "events.parquet")
cells = pd.read_parquet("/mnt/project-files/ratapani/mp_grid/mp_cells.parquet", columns=["cell", "row", "col", "beat_uid"])
import sys; sys.path.insert(0, "/mnt/project-files/field-system")
from app.geo import Beats
B = Beats()
cells["division"] = cells.beat_uid.map(lambda u: B.by_uid.get(u, {}).get("division"))
e["row"], e["col"] = ((2996000 - e.y) // 500).astype(int), ((e.x - 399000) // 500).astype(int)
e["cell"] = e.row * 1829 + e.col
e["div"] = e.beat_uid.map(lambda u: B.by_uid.get(u, {}).get("division")).fillna(e.Division)
YEARS = list(range(2017, 2026))
R = {}
rng = np.random.default_rng(7)

# ---------- A. which divisions are getting worse, as a share of the state (S-NPP-seen events, one sensor every year)
s = e[e.has_snpp].groupby(["div", "year"]).size().unstack(fill_value=0).reindex(columns=YEARS, fill_value=0)
share = s / s.sum(0)
rows = []
for d, v in share.iterrows():
    if s.loc[d].sum() < 90:
        continue
    tau, p = stats.kendalltau(YEARS, v.values)
    sl = stats.theilslopes(v.values, YEARS)[0]
    rows.append({"division": d, "events_snpp_2017_25": int(s.loc[d].sum()), "share_2017_19_%": round(100 * share.loc[d, 2017:2019].mean(), 2),
                 "share_2023_25_%": round(100 * share.loc[d, 2023:2025].mean(), 2), "kendall_tau": round(tau, 2), "p": p,
                 "change_share_pts_per_yr": round(100 * sl, 3)})
A = pd.DataFrame(rows)
A["q_fdr"] = stats.false_discovery_control(A.p.values)
A = A.sort_values("kendall_tau")
A.to_csv(D / "div_trend_share.csv", index=False)
R["trend"] = {"divisions": len(A), "fdr_below_0.1": int((A.q_fdr < 0.1).sum()), "p_below_0.05": int((A.p < 0.05).sum()),
              "expected_by_chance_p05": round(0.05 * len(A), 1),
              "rising": A[(A.p < 0.05) & (A.kendall_tau > 0)][["division", "share_2017_19_%", "share_2023_25_%", "p", "q_fdr"]].to_dict("records"),
              "falling": A[(A.p < 0.05) & (A.kendall_tau < 0)][["division", "share_2017_19_%", "share_2023_25_%", "p", "q_fdr"]].to_dict("records")}

# ---------- B. same ground every year: share of 2025 fires on cells that burned in 4+ of 2017-24, vs those cells' share of forest
past = e[e.year <= 2024].groupby("cell").year.nunique()
e25 = e[e.year == 2025]
rows = []
for d, g in cells.groupby("division"):
    pc = past.reindex(g.cell).fillna(0)
    chronic = set(pc[pc >= 4].index); never = set(pc[pc == 0].index)
    f = e25[e25["div"] == d]
    if len(f) < 30:
        continue
    rows.append({"division": d, "forest_cells": len(g), "chronic_cells_share_of_forest_%": round(100 * len(chronic) / len(g), 1),
                 "fires_2025": len(f), "fires_2025_on_chronic_%": round(100 * f.cell.isin(chronic).mean(), 1),
                 "fires_2025_on_never_burned_2017_24_%": round(100 * f.cell.isin(never).mean(), 1),
                 "never_burned_share_of_forest_%": round(100 * len(never) / len(g), 1)})
Bt = pd.DataFrame(rows)
Bt["lift"] = (Bt["fires_2025_on_chronic_%"] / Bt["chronic_cells_share_of_forest_%"].replace(0, np.nan)).round(1)
Bt = Bt.sort_values("fires_2025_on_chronic_%", ascending=False); Bt.to_csv(D / "div_chronic.csv", index=False)
allc = past.reindex(cells.cell).fillna(0)
R["chronic"] = {"state_chronic_share_of_forest_%": round(100 * (allc >= 4).mean(), 1),
                "state_2025_fires_on_chronic_%": round(100 * e25.cell.isin(set(allc[allc >= 4].index)).mean(), 1),
                "state_never_burned_share_%": round(100 * (allc == 0).mean(), 1),
                "state_2025_fires_on_never_burned_%": round(100 * e25.cell.isin(set(allc[allc == 0].index)).mean(), 1),
                "median_division_lift": float(Bt.lift.median())}
# beats that hold chronic ground: top chronic beats per division (for the officer)
cb = cells.assign(py=allc.values)
beat_chronic = cb.groupby(["division", "beat_uid"]).agg(cells=("cell", "size"), chronic=("py", lambda v: int((v >= 4).sum())), years_mean=("py", "mean")).reset_index()
beat_chronic["beat"] = beat_chronic.beat_uid.map(lambda u: B.by_uid.get(u, {}).get("beat")); beat_chronic["range"] = beat_chronic.beat_uid.map(lambda u: B.by_uid.get(u, {}).get("range"))
beat_chronic.sort_values(["division", "chronic"], ascending=[True, False]).groupby("division").head(5).to_csv(D / "div_top_chronic_beats.csv", index=False)

# ---------- C. fires that are still burning the next day, with a density null (another fire within 1.5 km 7 days later)
by = {d: g for d, g in e.groupby("date")}
def near_later(lag):
    out = np.zeros(len(e), bool)
    for d, g in by.items():
        n = by.get(d + pd.Timedelta(days=lag))
        if n is not None:
            out[g.index] = np.isfinite(cKDTree(n[["x", "y"]].values).query(g[["x", "y"]].values, distance_upper_bound=1500)[0])
    return out
e["d7"] = near_later(7)
ns = e[e.new_start]
C = ns.groupby("div").agg(new_fires=("event_id", "size"), next_day_=("next_day", "mean"), base_7d=("d7", "mean")).reset_index().rename(columns={"div": "division"})
C["still_burning_next_day_%"] = (100 * C.next_day_).round(1); C["same_spot_7_days_later_%"] = (100 * C.base_7d).round(1)
C["excess_pts"] = (C["still_burning_next_day_%"] - C["same_spot_7_days_later_%"]).round(1)
# consistency: is a division's next-day rate a stable trait? split years odd / even
odd = ns[ns.year % 2 == 1].groupby("div").next_day.mean(); even = ns[ns.year % 2 == 0].groupby("div").next_day.mean()
big = C[C.new_fires >= 200].division
rho_c = stats.spearmanr(odd.reindex(big), even.reindex(big), nan_policy="omit")
C = C[C.new_fires >= 200].drop(columns=["next_day_", "base_7d"]).sort_values("excess_pts", ascending=False); C.to_csv(D / "div_still_burning.csv", index=False)
R["still_burning"] = {"state_next_day_%": round(100 * ns.next_day.mean(), 1), "state_7d_null_%": round(100 * ns.d7.mean(), 1),
                      "odd_vs_even_years_spearman": round(rho_c.statistic, 2), "p": float(rho_c.pvalue),
                      "top5": C.head(5)[["division", "still_burning_next_day_%", "same_spot_7_days_later_%", "excess_pts"]].to_dict("records"),
                      "bottom5": C.tail(5)[["division", "still_burning_next_day_%", "same_spot_7_days_later_%", "excess_pts"]].to_dict("records")}

# ---------- D. hectares per fire (scar), and how much of a division's burnt ground comes from its biggest 5% of fires
sc = e[e.status.isin(["scar", "scar_faint"]) & e.scar_ha.notna()]
def top5(v):
    v = np.sort(v.values)[::-1]; k = max(1, int(round(len(v) * 0.05)))
    return v[:k].sum() / v.sum()
Dd = sc.groupby("div").agg(scars=("scar_ha", "size"), median_ha=("scar_ha", "median"), top5pct_fires_share=("scar_ha", top5)).reset_index()
Dd = Dd[Dd.scars >= 150]
o2 = sc[sc.year % 2 == 1].groupby("div").scar_ha.median(); e2 = sc[sc.year % 2 == 0].groupby("div").scar_ha.median()
rho_d = stats.spearmanr(o2.reindex(Dd["div"]), e2.reindex(Dd["div"]), nan_policy="omit")
Dd["top5pct_fires_share"] = (100 * Dd.top5pct_fires_share).round(1); Dd["median_ha"] = Dd.median_ha.round(1)
Dd = Dd.sort_values("median_ha", ascending=False).rename(columns={"div": "division"}); Dd.to_csv(D / "div_hectares.csv", index=False)
# do divisions where fires keep burning also have bigger scars?
j = C.merge(Dd, on="division")
rho_cd = stats.spearmanr(j["excess_pts"], j["median_ha"])
R["hectares"] = {"odd_vs_even_spearman": round(rho_d.statistic, 2), "state_median_ha": round(float(sc.scar_ha.median()), 1),
                 "state_top5pct_share_%": round(100 * top5(sc.scar_ha), 1), "still_burning_vs_scar_size_spearman": round(rho_cd.statistic, 2),
                 "p_still_vs_size": float(rho_cd.pvalue)}
# note: scar outlines are per event and neighbours overlap; medians are per event and not summed

# ---------- E. fires first seen at night (lit in the evening) among new starts, VIIRS only
nv = ns[ns.satellite.isin(["N", "N20"])]
E_ = nv.groupby("div").agg(new_fires=("event_id", "size"), night=("daynight", lambda v: (v == "N").mean())).reset_index()
E_ = E_[E_.new_fires >= 200]
o3 = nv[nv.year % 2 == 1].groupby("div").daynight.apply(lambda v: (v == "N").mean()); e3 = nv[nv.year % 2 == 0].groupby("div").daynight.apply(lambda v: (v == "N").mean())
rho_e = stats.spearmanr(o3.reindex(E_["div"]), e3.reindex(E_["div"]), nan_policy="omit")
E_["night_first_%"] = (100 * E_.night).round(1); E_ = E_.drop(columns="night").sort_values("night_first_%", ascending=False).rename(columns={"div": "division"})
E_.to_csv(D / "div_night_starts.csv", index=False)
R["night"] = {"state_night_first_%": round(100 * (nv.daynight == "N").mean(), 1), "odd_vs_even_spearman": round(rho_e.statistic, 2),
              "top5": E_.head(5).to_dict("records"), "bottom5": E_.tail(5).to_dict("records")}

# ---------- G. ground that burns twice in one season (same 500 m cell, 10+ days apart)
def twice(g):
    t = g.sort_values("date").date.values
    return (t[-1] - t[0]) >= np.timedelta64(10, "D")
cy = e.groupby(["div", "year", "cell"]).date.agg(["min", "max"])
cy["twice"] = (cy["max"] - cy["min"]).dt.days >= 10
G = cy.groupby("div").twice.agg(["size", "mean"]).reset_index(); G = G[G["size"] >= 300]
G["burnt_twice_same_season_%"] = (100 * G["mean"]).round(1); G = G.rename(columns={"div": "division", "size": "cell_seasons"}).drop(columns="mean")
G.sort_values("burnt_twice_same_season_%", ascending=False).to_csv(D / "div_burn_twice.csv", index=False)
R["burn_twice"] = {"state_%": round(100 * cy.twice.mean(), 1), "top5": G.sort_values("burnt_twice_same_season_%", ascending=False).head(5).to_dict("records")}

# ---------- H. outbreak days: how much of a division's season comes on its worst 10% of days
dd = e.groupby(["div", "date"]).size()
rows = []
for d, v in dd.groupby(level=0):
    if v.sum() < 300:
        continue
    yrs = e[e["div"] == d].year.nunique()
    full = v.values
    days = 121 * yrs
    arr = np.r_[full, np.zeros(max(0, days - len(full)))]
    k = int(days * 0.1); top = np.sort(arr)[::-1][:k].sum() / arr.sum()
    # null: same fires spread as Poisson over the same days with the division's seasonal curve
    rows.append({"division": d, "fires": int(arr.sum()), "worst_10pct_days_share_%": round(100 * top, 1)})
H = pd.DataFrame(rows).sort_values("worst_10pct_days_share_%", ascending=False); H.to_csv(D / "div_outbreak_days.csv", index=False)
# synchrony: on a division's bad days, is the whole state bad too? correlation of daily counts with the rest of MP
st = e.groupby("date").size()
syn = []
for d in H.division:
    v = dd.loc[d].reindex(st.index, fill_value=0)
    syn.append(stats.spearmanr(v, st - v).statistic)
H["sync_with_rest_of_state"] = np.round(syn, 2); H.to_csv(D / "div_outbreak_days.csv", index=False)
R["outbreaks"] = {"median_worst10_share_%": float(H["worst_10pct_days_share_%"].median()), "median_sync": float(np.median(syn)),
                  "least_synced": H.sort_values("sync_with_rest_of_state").head(5)[["division", "sync_with_rest_of_state", "worst_10pct_days_share_%"]].to_dict("records")}

json.dump(R, open(D / "results.json", "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float)[:6000])
