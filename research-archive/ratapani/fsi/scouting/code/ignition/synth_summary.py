"""Summarise synthetic test results. Usage: python -I synth_summary.py <synth.csv> [...]"""
import sys
import numpy as np, pandas as pd
for f in sys.argv[1:]:
    R = pd.read_csv(f); R = R[R.detected == True]
    one = R[~R.two]; two = R[R.two]
    print("==", f, "single n", len(one), "two n", len(two))
    q = lambda s: f"med {s.median():.0f} p75 {s.quantile(.75):.0f} p90 {s.quantile(.9):.0f}"
    for c in ["err_e0", "err_e1", "err_e2", "err_e2map", "err_rand"]:
        print(f"  {c:10s}", q(one[c]))
    print("  truth inside first-pass footprint:", round(one.truth_in_first_fp.mean(), 3),
          " mean predicted p_in_first_fp:", round(one.p_in_first_fp.mean(), 3))
    for lo, hi in [(0, .2), (.2, .5), (.5, .8), (.8, 1.01)]:
        m = (one.p_in_first_fp >= lo) & (one.p_in_first_fp < hi)
        print(f"    p in [{lo},{hi}): n {m.sum()}, observed {one.truth_in_first_fp[m].mean():.2f}")
    print("  coverage err_e2<=R50:", round((one.err_e2 <= one.e2_r50).mean(), 3), " <=R90:",
          round((one.err_e2 <= one.e2_r90).mean(), 3), " <=E1 radius:", round((one.err_e1 <= one.e1_r).mean(), 3))
    k = np.quantile(one.err_e2 / one.e2_r90.clip(lower=40), 0.9)
    print("  R90 inflation for 90% coverage:", round(k, 2))
    print("  time: first-detection lag", q(one.t_first_lag), "h | E2 err med", round(one.terr.median(), 2),
          "MAE", round(one.terr.abs().median(), 2), "naive MAE", round(one.t_naive_err.abs().median(), 2),
          "90% interval coverage", round(one.tcov.mean(), 3))
    for nm, sub in [("single", one), ("two", two)]:
        f60 = (sub.n_ign_v60 >= 2).mean(); f150 = (sub.n_ign_v150 >= 2).mean()
        fr = (sub.max_resid_h > 3).mean()
        print(f"  {nm}: flag n_ign_v60>=2 {f60:.3f}, v150 {f150:.3f}, resid>3h {fr:.3f}, either {((sub.n_ign_v60>=2)|(sub.max_resid_h>3)).mean():.3f}")
    by = pd.cut(one.scar_ha, [0, 10, 30, 100, 1000])
    print(one.groupby(by, observed=True)[["err_e0", "err_e2", "err_rand"]].median().round(0).to_string())
    print(one.groupby(pd.cut(one.v_true, [0, 40, 80, 150, 400]), observed=True)[["err_e0", "err_e2", "truth_in_first_fp"]].median().round(2).to_string())
