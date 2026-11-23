"""Real-data check: scars where a Sentinel-2/Landsat 20-30 m fire pixel (~10:45 IST) was seen BEFORE the
first FIRMS detection. The fire pixel marks where the front was at that time, so it lies between the true
ignition and the later FIRMS footprints. Score estimators run on FIRMS only by their distance to it.

Usage: python -I valaf.py <prepdir> <firms_only.csv> <out.csv>
"""
import sys
import numpy as np, pandas as pd

PREP, FO, OUT = sys.argv[1:4]
D = pd.read_pickle(PREP + "/dets.pkl"); Lk = pd.read_pickle(PREP + "/links.pkl")
EP = pd.Timestamp(0, tz="UTC")
D["th"] = (D.t - EP) / pd.Timedelta(hours=1)
E = pd.read_csv(FO); E = E[E.status == "ok"]
L = Lk.merge(D[["src", "th", "x", "y", "hx", "hy"]], left_on="det", right_index=True)
rows = []
for _, e in E.iterrows():
    g = L[L.scar == e.scar]
    af = g[(g.src == "af") & (g.th < e.t_first - 0.5)]
    if len(af) == 0:
        continue
    a = af[af.th == af.th.min()]
    ax, ay = a.x.mean(), a.y.mean()
    f = g[(g.src == "firms") & (g.th <= e.t_first + 1.0)]
    in_fp = bool(((np.abs(f.x - ax) <= f.hx) & (np.abs(f.y - ay) <= f.hy)).any())
    rows.append(dict(scar=e.scar, event_id=e.event_id, lag_h=e.t_first - a.th.iloc[0], n_af=len(a),
                     af_in_first_fp=in_fp,
                     d_e0=np.hypot(e.e0_x - ax, e.e0_y - ay), d_e1=np.hypot(e.e1_x - ax, e.e1_y - ay),
                     d_e2=np.hypot(e.e2_x - ax, e.e2_y - ay), d_e2map=np.hypot(e.e2_map_x - ax, e.e2_map_y - ay),
                     e2_r50=e.e2_r50, e2_r90=e.e2_r90, e1_r=e.e1_r,
                     t_ign_med=e.t_ign_med, t_ign_05=e.t_ign_05, t_ign_95=e.t_ign_95, t_af=a.th.iloc[0],
                     af_after_t05=a.th.iloc[0] >= e.t_ign_05))
R = pd.DataFrame(rows)
R.to_csv(OUT, index=False)
print("n", len(R), "lag h median", R.lag_h.median(), "same-day share", (R.lag_h < 6).mean())
print("AF inside first FIRMS footprint:", R.af_in_first_fp.mean().round(3))
for c in ["d_e0", "d_e1", "d_e2", "d_e2map"]:
    print(c, "median", round(R[c].median()), "p75", round(R[c].quantile(.75)))
print("AF within E2 R50 / R90:", (R.d_e2 <= R.e2_r50).mean().round(3), (R.d_e2 <= R.e2_r90).mean().round(3))
print("AF time after E2 5% ignition time:", R.af_after_t05.mean().round(3))
sd = R[R.lag_h < 6]
print("same-day subset n", len(sd), {c: round(sd[c].median()) for c in ["d_e0", "d_e1", "d_e2"]},
      "inside fp", sd.af_in_first_fp.mean().round(3), "within R90", (sd.d_e2 <= sd.e2_r90).mean().round(3))
print("E2 closer than E0:", (R.d_e2 < R.d_e0).mean().round(3), " E1 closer than E0:", (R.d_e1 < R.d_e0).mean().round(3))
