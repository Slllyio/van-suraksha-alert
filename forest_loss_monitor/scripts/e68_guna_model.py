"""Stress test of the time-series logistic trained only on Guna-area owner labels: whole-beat held-out scores with bootstrap ranges, a shuffled-label control, the rule's 6 background points,
and transfer to my statewide points it never saw (no Guna points there). Usage: e68_guna_model.py"""
import warnings

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from common import *
from e23_guna_labels import wpr
from e48_tests import load
from e49_ts import series_feats, ts_pass
from e63_cascade import NETS, feats, fit, labels, pick, triggers

warnings.filterwarnings("ignore")
REPS = 10
REPORT = OUT / "interim" / "report"


def boot_ci(ref, f, n=400, seed=1):
    rng = np.random.default_rng(seed)
    beats = ref.group.unique()
    ps, rs = [], []
    for _ in range(n):
        s = pd.concat([ref[ref.group == b].assign(_f=f[ref.group == b]) for b in rng.choice(beats, len(beats))])
        a, b = wpr(s.y.values, s._f.values.astype(int), s.eval_w.values)
        if np.isfinite(a):
            ps.append(a)
        rs.append(b)
    return [round(float(np.quantile(ps, q)), 3) for q in (.025, .975)], [round(float(np.quantile(rs, q)), 3) for q in (.025, .975)]


def main():
    p = load()
    L = labels().set_index("pid")
    L = L[L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    sf = series_feats(p)
    t = triggers(p, sf)
    F = feats(p, sf, t).reindex(L.index)
    cand = t[NETS["+ NBR"]].any(axis=1).groupby(p.pid).any().reindex(L.index).fillna(False).values
    base = (t["rule"] & ts_pass(sf, (.15, .15, 0, 9))).groupby(p.pid).sum().reindex(L.index).fillna(0).ge(2).values
    y = L.y.values.copy()
    is_ref = (L.set == "blind_reference").values
    guna = L.set.isin(["blind_reference", "felling_alert_verdict"]).values | ((L.set == "bamori_validated").values & (L.cls == "forest_to_crop").values)
    tr_all = np.flatnonzero(guna & cand)
    w = np.where(is_ref, L.eval_w.values / L.eval_w[is_ref].mean(), 1.0)
    print("training points", len(tr_all), "positives", int(y[tr_all].sum()), "reference points among them", int(is_ref[tr_all].sum()), "reference positives", int(y[tr_all][is_ref[tr_all]].sum()), "reference false", int((1 - y[tr_all][is_ref[tr_all]]).sum()))

    def cv_scores(yy, seed):
        flags = {n: np.zeros(len(L), bool) for n in ("max F1", "precision >= 75%")}
        cv = StratifiedGroupKFold(5, shuffle=True, random_state=seed)
        for a, b in cv.split(F.iloc[tr_all], yy[tr_all], L.group.values[tr_all]):
            tr, te = tr_all[a], tr_all[b]
            m = fit("logistic", F.iloc[tr], yy[tr], w[tr])
            s = m.predict_proba(F.iloc[te])[:, 1]
            inner = np.zeros(len(tr))
            for c, d in StratifiedGroupKFold(3, shuffle=True, random_state=seed).split(F.iloc[tr], yy[tr], L.group.values[tr]):
                inner[d] = fit("logistic", F.iloc[tr[c]], yy[tr[c]], w[tr[c]]).predict_proba(F.iloc[tr[d]])[:, 1]
            ri = is_ref[tr]
            for n, tg in (("max F1", None), ("precision >= 75%", .75)):
                flags[n][te] = s >= pick(inner[ri], yy[tr][ri], L.eval_w.values[tr][ri], tg)
        return flags

    ref = L[is_ref]
    res = []
    fb = base[is_ref]
    pb, rb = wpr(ref.y.values, fb.astype(int), ref.eval_w.values)
    ci = boot_ci(ref, fb)
    res.append(dict(test="Guna held-out", method="filter + 2 px", precision=round(pb, 3), p_ci=ci[0], recall=round(rb, 3), r_ci=ci[1], flagged=int(fb.sum()), real=int((fb & (ref.y.values == 1)).sum())))
    for n in ("max F1", "precision >= 75%"):
        runs = [cv_scores(y, s)[n][is_ref] for s in range(REPS)]
        vals = [wpr(ref.y.values, r.astype(int), ref.eval_w.values) for r in runs]
        f = np.mean(runs, axis=0) >= .5
        ci = boot_ci(ref, f)
        pr, re = wpr(ref.y.values, f.astype(int), ref.eval_w.values)
        res.append(dict(test="Guna held-out", method="logistic " + n, precision=round(pr, 3), p_ci=ci[0], recall=round(re, 3), r_ci=ci[1], flagged=int(f.sum()), real=int((f & (ref.y.values == 1)).sum()), p_mean=round(np.nanmean([a for a, _ in vals]), 3), r_mean=round(np.mean([b for _, b in vals]), 3), p_sd=round(np.nanstd([a for a, _ in vals]), 3), r_sd=round(np.std([b for _, b in vals]), 3), bg_real=f"{int((f & (ref.y.values == 1) & (ref.stratum.values == 'background')).sum())}/6"))
    rng = np.random.default_rng(9)
    shuf = []
    for s in range(10):
        yy = y.copy()
        yy[tr_all] = rng.permutation(y[tr_all])
        fl = cv_scores(yy, s)["max F1"][is_ref]
        shuf.append(wpr(yy[is_ref], fl.astype(int), ref.eval_w.values))
    res.append(dict(test="shuffled labels (should be poor)", method="logistic max F1", precision=round(np.nanmean([a for a, _ in shuf]), 3), recall=round(np.mean([b for _, b in shuf]), 3)))
    m = fit("logistic", F.iloc[tr_all], y[tr_all], w[tr_all])
    inner = np.zeros(len(tr_all))
    for c, d in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(F.iloc[tr_all], y[tr_all], L.group.values[tr_all]):
        inner[d] = fit("logistic", F.iloc[tr_all[c]], y[tr_all[c]], w[tr_all[c]]).predict_proba(F.iloc[tr_all[d]])[:, 1]
    ri = is_ref[tr_all]
    for n, tg in (("max F1", None), ("precision >= 75%", .75)):
        th = pick(inner[ri], y[tr_all][ri], L.eval_w.values[tr_all][ri], tg)
        s = m.predict_proba(F)[:, 1]
        f = (s >= th) & cand
        for setname in ("round2", "round1"):
            k = (L.set == setname).values
            pr, re = wpr(y[k], f[k].astype(int), L.eval_w.values[k])
            pb, rb = wpr(y[k], base[k].astype(int), L.eval_w.values[k])
            res.append(dict(test=f"statewide, never seen: {setname}", method="logistic " + n, precision=round(pr, 3), recall=round(re, 3), flagged=int(f[k].sum()), real=int((f[k] & (y[k] == 1)).sum()), base_precision=round(pb, 3), base_recall=round(rb, 3), base_flagged=int(base[k].sum()), base_real=int((base[k] & (y[k] == 1)).sum())))
            if setname == "round2":
                for z in sorted(set(L.zone[k])):
                    q = k & (L.zone.values == z)
                    pr, re = wpr(y[q], f[q].astype(int), L.eval_w.values[q])
                    pb, rb = wpr(y[q], base[q].astype(int), L.eval_w.values[q])
                    res.append(dict(test=f"round2 {z}", method="logistic " + n, precision=round(pr, 3), recall=round(re, 3), flagged=int(f[q].sum()), real=int((f[q] & (y[q] == 1)).sum()), base_precision=round(pb, 3), base_recall=round(rb, 3)))
        q = (L.set == "random300").values
        print(n, "threshold", round(float(th), 3), "share of random forest kept", round(100 * f[q].mean(), 1), "%, candidates", round(100 * cand[q].mean(), 1), "%")
    co = pd.Series(m.named_steps["logisticregression"].coef_[0], index=F.columns)
    print(co.reindex(co.abs().sort_values(ascending=False).index).head(14).round(3).to_string())
    r = pd.DataFrame(res)
    print(r.drop(columns=[c for c in ("p_mean", "r_mean") if c not in r]).to_string())
    r.to_csv(REPORT / "guna_model_stress_test.csv", index=False)


if __name__ == "__main__":
    main()
