"""Does the scar burn history say more about next season's burning than the VIIRS 'burned before' history?
Cells: all-MP 500 m beat cells with >= 10% forest. Target years 2019-2025; predictors use earlier seasons only.
Labels: (A) scar-burned (>= 10% of the cell burned on forest ground) and (B) any S-NPP point in the cell, both 15 Feb-15 Jun.
Out: burn_history/check.csv and the per-cell map files."""
import os, glob, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from pyproj import Transformer
B = "/mnt/project-files/fire-alert-scars/mp/burn_history/"
X0, Y1, NC, S = 399000.0, 2996000.0, 1829, 500.0
D = pd.read_parquet(B + "cell_year.parquet")
C = pd.read_parquet("/mnt/project-files/ratapani/mp_grid/mp_cells.parquet")[["cell", "beat_uid"]]
fo = D.groupby("cell").forest.first()
C["forest"] = C.cell.map(fo)
# forest share for cells never burned is not in D: treat as unknown -> keep them (forest NaN) only if beat cell
D["hit"] = D.burned_forest >= 0.10
scar = D[D.hit].pivot_table(index="cell", columns="year", values="hit", aggfunc="any").reindex(C.cell).fillna(False).astype(bool)
T = Transformer.from_crs(4326, 32643, always_xy=True)
v = {}
for f in sorted(glob.glob("/mnt/project-files/fire-alert-scars/alerts_mp/viirs-snpp_*.csv")):
    y = int(f[-8:-4])
    if y > 2025: continue
    a = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date"])
    md = a.acq_date.str[5:]
    a = a[(md >= "02-15") & (md <= "06-15")]
    x, yy = T.transform(a.longitude.values, a.latitude.values)
    c = ((Y1 - yy) // S).astype(int) * NC + ((x - X0) // S).astype(int)
    v[y] = pd.Series(True, index=np.unique(c))
V = pd.DataFrame({y: s.reindex(C.cell).fillna(False).values for y, s in v.items()}, index=C.cell.values).astype(bool)
rows = []
for Y in range(2019, 2026):
    pri = [y for y in range(2017, Y)]
    f_scar = scar[pri].sum(1).values
    f_last = np.array([max([y for y in pri if r[y]] or [2000]) for _, r in scar[pri].iterrows()]) if False else None
    f_v17 = V[pri].sum(1).values
    f_v14 = V[[y for y in range(2014, Y)]].sum(1).values
    for lab_name, lab in (("scar", scar[Y].values), ("viirs", V[Y].values)):
        r = dict(year=Y, label=lab_name, base_rate=round(lab.mean(), 4))
        for nm, f in (("scar_years", f_scar), ("viirs_years_2017on", f_v17), ("viirs_years_2014on", f_v14), ("scar+viirs14", f_scar + f_v14 + 0.01 * f_scar)):
            r["auc_" + nm] = round(roc_auc_score(lab, f + 1e-6 * np.random.default_rng(0).random(len(f))), 4)
            k = int(0.1 * len(f)); top = np.argsort(-(f + 1e-6 * np.random.default_rng(0).random(len(f))))[:k]
            r["top10_" + nm] = round(lab[top].sum() / lab.sum(), 4)
        rows.append(r)
R = pd.DataFrame(rows); R.to_csv(B + "check.csv", index=False)
print(R.groupby("label").mean(numeric_only=True).round(3).T.to_string())
# map files for other threads: years burned 2017-25, last burned season, mean burned share
yrs = list(range(2017, 2026))
M = pd.DataFrame({"cell": C.cell.values, "beat_uid": C.beat_uid.values,
                  "years_burned": scar[yrs].sum(1).values,
                  "last_burned": scar[yrs].apply(lambda r: max([y for y in yrs if r[y]] or [0]), axis=1).values})
sh = D.pivot_table(index="cell", columns="year", values="burned_forest").reindex(C.cell).fillna(0)
M["mean_forest_share_burned"] = sh.mean(1).round(3).values
M["forest"] = C.forest.values
M.to_csv(B + "cell_burn_history.csv", index=False)
print(M.years_burned.value_counts().sort_index().to_string())
