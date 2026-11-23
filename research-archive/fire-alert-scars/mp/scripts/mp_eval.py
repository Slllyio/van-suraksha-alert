"""All-MP check: scar found for real fire events vs control points (same date, 3 km away, forest, no alert within
1.5 km / 30 days), by division and region. Out: mp/out/eval_sample_by_division.csv"""
import pandas as pd
M = "/mnt/project-files/fire-alert-scars/mp/out/"
S = pd.read_csv(M + "set_sample.csv"); R = pd.read_csv(M + "scars_sample.csv").drop_duplicates("event_id", keep="last")
D = S.merge(R[["event_id", "status", "scar_ha", "gap_days", "severity"]], on="event_id")
D = D[~D.status.isin(["waiting", "no_pre", "error", "no_clear_image"])]
D["yes"] = D.status == "scar"; D["any"] = D.status.isin(["scar", "scar_faint"])
D["ratapani"] = D.Division.isin(["Obedullahganj", "Raisen"])
print(D.groupby("kind")[["yes", "any"]].mean().round(3), D.kind.value_counts().to_dict())
# pairs: fires that have a control
P = D[D.kind == "control"].assign(event_id=lambda d: d.event_id.str[2:])[["event_id", "yes"]].merge(
    D[D.kind == "fire"][["event_id", "yes", "Division"]], on="event_id", suffixes=("_c", "_f"))
print("paired", len(P), "fire yes", P.yes_f.mean().round(3), "control yes", P.yes_c.mean().round(3))
F = D[D.kind == "fire"]
print("fire scar median ha", F[F.yes].scar_ha.median(), "| by year", F.groupby(F.acq_date.str[:4]).yes.mean().round(2).to_dict())
F["doy"] = pd.to_datetime(F.acq_date).dt.month
print("by month", F.groupby("doy").yes.mean().round(2).to_dict())
G = D.groupby(["Division", "kind"]).yes.agg(["mean", "size"]).unstack()
G.columns = [f"{a}_{b}" for a, b in G.columns]
G.round(3).to_csv(M + "eval_sample_by_division.csv")
f = G["mean_fire"].dropna()
print("divisions", len(f), "fire yes-rate quartiles", f.quantile([.1, .25, .5, .75, .9]).round(2).to_dict())
print("lowest", f.sort_values().head(8).round(2).to_dict())
