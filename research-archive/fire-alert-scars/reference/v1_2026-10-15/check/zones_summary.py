"""Summarise check/zones.csv into per-fire error bands (see zones.py). Out: check/zones_summary.md text on stdout,
check/zones_per_fire.csv"""
import numpy as np, pandas as pd
C = "/mnt/project-files/fire-alert-scars/reference/v1_2026-10-15/check/"
Z = pd.read_csv(C + "zones.csv")
Z["contrast"] = Z.br_far - Z.br_core            # > 0: core darker than far ring
def share(z): return ((Z.br_far - Z["br_" + z]) / Z.contrast).clip(0, 1)
for z in ("edge_in", "out_0_75", "out_75_250"):
    Z["f_" + z] = share(z)
Z["size"] = pd.qcut(Z.scar_ha, 3, labels=["small", "medium", "large"])
R, D = Z[~Z.decoy].copy(), Z[Z.decoy].copy()
# a fire "reads" when its core is clearly darker than its far ring; threshold = 90th percentile of decoys
thr = D.contrast.quantile(0.9)
R["reads"] = R.contrast > thr
print(f"fires {len(R)}, decoys {len(D)}; contrast threshold (decoy 90th pct) {thr:.1f}")
print("core clearly darker than far ring: real", R.reads.mean().round(3), "decoy", (D.contrast > thr).mean().round(3))
print(R.groupby("size", observed=True).reads.mean().round(2).to_dict(), R.groupby(pd.cut(R.year, [2000, 2019, 2024, 2030]), observed=True).reads.mean().round(2).to_dict())
Q = R[R.reads].copy()
Q["missed_ha"] = Q.ha_out_0_75 * Q.f_out_0_75 + Q.ha_out_75_250 * Q.f_out_75_250
Q["false_edge_ha"] = Q.ha_edge_in * (1 - Q.f_edge_in)
Q["missed_rel"] = Q.missed_ha / Q.scar_ha; Q["false_rel"] = Q.false_edge_ha / Q.scar_ha
# noise floor: same unmixing on decoys that happen to "read" is meaningless, so use the bands' share in decoys vs their own far ring
for z in ("edge_in", "out_0_75", "out_75_250"):
    print(z, "burned share real median", Q["f_" + z].median().round(2), "IQR", Q["f_" + z].quantile([.25, .75]).round(2).tolist())
print("missed area / outline: median", Q.missed_rel.median().round(2), "IQR", Q.missed_rel.quantile([.25, .75]).round(2).tolist(),
      "| false edge / outline: median", Q.false_rel.median().round(2), "IQR", Q.false_rel.quantile([.25, .75]).round(2).tolist())
print(Q.groupby("size", observed=True)[["missed_rel", "false_rel"]].median().round(2))
print("whole outline not readable (core not darker than decoy noise):", (~R.reads).mean().round(2))
Q.to_csv(C + "zones_per_fire.csv", index=False)
