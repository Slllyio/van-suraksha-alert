# Are "still burning next day" and "first seen at night" division traits, or just forest type/fragmentation and month?
# Expected rate per fire from local forest share (WorldCover within 375 m, 10 bins) x month x fire density; division
# residual = observed - expected. Plus beat-boundary fires vs random points in the same beats.
import json, numpy as np, pandas as pd
from pathlib import Path
from scipy import stats
import sys; sys.path.insert(0, "/mnt/project-files/field-system")
from app.geo import Beats
D = Path(__file__).parent
e = pd.read_parquet(D / "events.parquet"); B = Beats()
fs = pd.read_csv("/mnt/project-files/fire-alert-scars/mp/out/mp_events.csv", usecols=["event_id", "forest_share"])
e = e.merge(fs, on="event_id", how="left")
e["div"] = e.beat_uid.map(lambda u: B.by_uid.get(u, {}).get("division")).fillna(e.Division)
e["fbin"] = pd.qcut(e.forest_share, 10, labels=False, duplicates="drop"); e["month"] = e.date.dt.month
# local density: forest events within the same 10 km block that year
e["blk"] = (e.x // 10000).astype(int).astype(str) + "_" + (e.y // 10000).astype(int).astype(str)
e["dens"] = pd.qcut(e.groupby(["blk", "year"]).event_id.transform("size"), 5, labels=False, duplicates="drop")
R = {}
ns = e[e.new_start].copy()
for col, name, sub in [("next_day", "still_burning", ns), ("night", "night_first", ns[ns.satellite.isin(["N", "N20"])].assign(night=lambda d: d.daynight.eq("N")))]:
    sub = sub.copy(); sub[col] = sub[col].astype(float)
    sub["exp"] = sub.groupby(["fbin", "month", "dens"])[col].transform("mean")
    g = sub.groupby("div").agg(n=(col, "size"), obs=(col, "mean"), exp=("exp", "mean")).reset_index()
    g = g[g.n >= 200]; g["resid_pts"] = (100 * (g.obs - g.exp)).round(1); g["obs_%"] = (100 * g.obs).round(1); g["expected_%"] = (100 * g.exp).round(1)
    # stability of the residual: odd vs even years
    r = {}
    for par in (0, 1):
        s2 = sub[sub.year % 2 == par]; r[par] = (s2.groupby("div")[col].mean() - s2.groupby("div")["exp"].mean())
    rho = stats.spearmanr(r[0].reindex(g["div"]), r[1].reindex(g["div"]), nan_policy="omit")
    share_explained = 1 - np.var(g.obs - g.exp) / np.var(g.obs)
    g = g.sort_values("resid_pts", ascending=False).rename(columns={"div": "division"}).drop(columns=["obs", "exp"])
    g.to_csv(D / f"div_{name}_adjusted.csv", index=False)
    R[name] = {"residual_odd_even_spearman": round(rho.statistic, 2), "p": float(rho.pvalue), "share_of_division_spread_explained_by_forest_month_density": round(float(share_explained), 2),
               "top": g.head(6).to_dict("records"), "bottom": g.tail(6).to_dict("records")}
# night share vs fragmentation
nv = ns[ns.satellite.isin(["N", "N20"])]
q = nv.groupby("div").agg(n=("event_id", "size"), night=("daynight", lambda v: (v == "N").mean()), forest=("forest_share", "median"))
q = q[q.n >= 200]
R["night_vs_forest_share_spearman"] = round(stats.spearmanr(q.night, q.forest).statistic, 2)

# ---- beat boundaries: fires within 250 m of a beat edge vs random points in the same beats
from shapely import STRtree, points, boundary, distance
from shapely.ops import transform
from pyproj import Transformer
T = Transformer.from_crs(4326, 32643, always_xy=True).transform
geo = [transform(T, g) for g in B.geoms]
edges = [boundary(g) for g in geo]; tree = STRtree(edges)
P = points(e.x.values, e.y.values)
idx = tree.query_nearest(P, return_distance=True, all_matches=False)
e["d_edge"] = idx[1]
# random points: uniform in beat cells (500 m grid) with jitter, same division mix as fires
cells = pd.read_parquet("/mnt/project-files/ratapani/mp_grid/mp_cells.parquet", columns=["x0", "y0", "beat_uid"])
cells["div"] = cells.beat_uid.map(lambda u: B.by_uid.get(u, {}).get("division"))
rng = np.random.default_rng(3)
w = e["div"].value_counts()
rs = []
for d, n in w.items():
    c = cells[cells["div"] == d]
    if len(c) == 0: continue
    k = c.sample(min(n, 20000), replace=True, random_state=1)
    rs.append(pd.DataFrame({"div": d, "x": k.x0.values + rng.uniform(0, 500, len(k)), "y": k.y0.values - rng.uniform(0, 500, len(k))}))
rs = pd.concat(rs)
rs["d_edge"] = tree.query_nearest(points(rs.x.values, rs.y.values), return_distance=True, all_matches=False)[1]
R["beat_edge"] = {"fires_within_250m_%": round(100 * (e.d_edge <= 250).mean(), 1), "random_within_250m_%": round(100 * (rs.d_edge <= 250).mean(), 1),
                  "fires_median_m": round(float(e.d_edge.median())), "random_median_m": round(float(rs.d_edge.median()))}
# do edge fires behave differently? next-day and scar size, within division (stratified)
ns = e[e.new_start].copy(); ns["edge"] = ns.d_edge <= 250
a = ns.groupby(["div", "edge"]).next_day.mean().unstack().dropna()
sz = e[e.status.eq("scar")].assign(edge=lambda d: d.d_edge <= 250).groupby(["div", "edge"]).scar_ha.median().unstack().dropna()
R["beat_edge"]["next_day_edge_minus_interior_pts_median_div"] = round(100 * float((a[True] - a[False]).median()), 1)
R["beat_edge"]["divisions_edge_higher_next_day"] = f"{int((a[True] > a[False]).sum())}/{len(a)}"
R["beat_edge"]["scar_ha_edge_over_interior_median_div"] = round(float((sz[True] / sz[False]).median()), 2)
R["beat_edge"]["divisions_edge_bigger_scar"] = f"{int((sz[True] > sz[False]).sum())}/{len(sz)}"
e[["event_id", "d_edge"]].to_parquet(D / "edge_dist.parquet")
json.dump(R, open(D / "results_controls.json", "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float)[:5000])
