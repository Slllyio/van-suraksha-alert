"""Recall-first cascade: wide candidate net at pixels of the 50 m box, then a learned filter scored on whole beats it never saw. Thresholds come from inner folds of the training beats only.
Guna and statewide results are reported apart, with the current filter + 2 px rule on the same points. Usage: e63_cascade.py stage1 | model [ts|emb|both|prithvi|ts+prithvi] [all|tree|conv]"""
import json
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier as HGB
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import *
from e14_accuracy import metrics
from e23_guna_labels import A_H, wpr
from e32_enetra10m import FOREST_MIN, NDVI_DROP, WOODY_MIN
from e48_tests import GT, YS, load, rule, s2f_flags
from e49_ts import rolling, series_feats, ts_pass
from zones import zone as zone_of

warnings.filterwarnings("ignore")
REPORT = OUT / "interim" / "report"
REAL_RANDOM = {35, 61, 63, 133, 149, 151, 153, 164, 253, 260, 261, 272, 291}     # my relabel under the owner's definition
FOLDS, REPEATS = 5, 3
OPS = (("max F1", None), ("precision >= 75%", .75), ("recall >= 70%", .70))


def labels():
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    a = g.assign(y=g.label, set=g.source, group="G_" + g.beat.astype(str), zone="mixed_dry_deciduous")[["pid", "y", "set", "group", "zone", "stratum", "cls"]]
    n = a[a.set == "blind_reference"].stratum.value_counts()
    a["eval_w"] = np.where(a.set == "blind_reference", a.stratum.map(lambda s: A_H.get(s, 0) / n.get(s, 1)), 0.0)
    rows = [a]
    for base, sub, nm in ((100000, "validation", "round1"), (200000, "validation2", "round2")):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / sub / "prelabels.csv"), on="sample_id")
        area = json.load(open(OUT / sub / "strata_area_ha.json"))
        rows.append(pd.DataFrame(dict(pid=k.sample_id + base, y=k.label.isin(list("LD")).astype(int), set=nm, group=k.Division + "_" + k.Beat.astype(str), zone=k.Division.map(zone_of), stratum=k.stratum, cls="", eval_w=k.stratum.map(area) / k.stratum.map(k.stratum.value_counts()))))
    r = pd.read_csv(GT / "s2f_random300.csv")
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    rows.append(pd.DataFrame(dict(pid=r.pid, y=(r.pid - 600000).isin(REAL_RANDOM).astype(int), set="random300", group=r.zone_id.map(lk.Division).astype(str) + "_" + r.zone_id.map(lk.Beat).astype(str), zone=r.zone_id.map(lk.Division).map(zone_of), stratum="random", cls="", eval_w=1.0)))
    return pd.concat(rows, ignore_index=True)


def triggers(p, sf):
    nda, ndb, nw = p.nea - p.nla, p.neb - p.nlb, p.water < 5
    forest = (p.ea_t >= FOREST_MIN) | (p.eb_t >= FOREST_MIN)
    t = {"rule": rule(p)[0]}
    t["tree08"] = (((p.ea_t >= FOREST_MIN) & (p.ea_t - p.la_t >= .08) & (nda >= NDVI_DROP)) | ((p.eb_t >= FOREST_MIN) & (p.eb_t - p.lb_t >= .08) & (ndb >= NDVI_DROP))) & nw
    t["rolling"] = rolling(p, .12, NDVI_DROP) & nw
    t["nbr"] = forest & (sf.drop_r >= .15) & nw
    t["bsi"] = forest & (p[["lb2023", "lb2024"]].mean(axis=1) - p[["lb2018", "lb2019"]].mean(axis=1) >= .05) & nw
    t["s2f_tight"] = s2f_flags(p, .1, .15, .3, 2)
    t["s2f_loose"] = s2f_flags(p, .1, .1, .3, 2)
    return pd.DataFrame(t)


NETS = {"rule": ["rule"], "+ tree 0.08": ["rule", "tree08"], "+ rolling": ["rule", "tree08", "rolling"], "+ NBR": ["rule", "tree08", "rolling", "nbr"], "+ scrub tight": ["rule", "tree08", "rolling", "nbr", "s2f_tight"],
        "+ scrub loose": ["rule", "tree08", "rolling", "nbr", "s2f_loose"], "+ BSI": ["rule", "tree08", "rolling", "nbr", "s2f_loose", "bsi"]}


def stage1():
    p = load()
    L = labels()
    sf = series_feats(p)
    t = triggers(p, sf)
    rows = []
    for name, cols in NETS.items():
        c = t[cols].any(axis=1).groupby(p.pid).any()
        q = L.assign(c=L.pid.map(c).fillna(False).astype(int))
        ref = q[q.set == "blind_reference"]
        pr, re = wpr(ref.y.values, ref.c.values, ref.eval_w.values)
        rnd = q[q.set == "random300"]
        d = dict(net=name, guna_recall_weighted=round(re, 3), guna_precision=round(pr, 3), guna_losses=f"{int((ref.c & ref.y).sum())}/{int(ref.y.sum())}", background_losses=f"{int((ref.c & ref.y)[ref.stratum == 'background'].sum())}/{int(ref.y[ref.stratum == 'background'].sum())}")
        for s in ("bamori_validated", "felling_alert_verdict"):
            x = q[(q.set == s) & (q.y == 1)]
            d[s] = f"{int(x.c.sum())}/{len(x)}"
        d["candidate_pct_random300"] = round(100 * rnd.c.mean(), 1)
        d["random_real_caught"] = f"{int((rnd.c & rnd.y).sum())}/{int(rnd.y.sum())}"
        rows.append(d)
    r = pd.DataFrame(rows)
    print(r.T.to_string())
    r.to_csv(REPORT / "cascade_stage1.csv", index=False)


def feats(p, sf, t):
    """Per pixel, then median and max over the box."""
    x = pd.DataFrame({k: sf[k].astype(float) for k in ("drop_n", "drop_r", "persist", "pre_sd", "break_year")})
    x["back"] = sf.back.astype(float)
    for b, nm in (("ln", "ndvi"), ("lr", "nbr"), ("lb", "bsi"), ("r", "rabi"), ("d", "dry")):
        pre, post = p[[f"{b}{y}" for y in (2017, 2018, 2019)]].mean(axis=1), p[[f"{b}{y}" for y in (2022, 2023, 2024)]].mean(axis=1)
        x[nm + "_pre"], x[nm + "_post"], x[nm + "_diff"] = pre, post, post - pre
        m = p[[f"{b}{y}" for y in YS]]
        x[nm + "_sd"] = m.std(axis=1)
        x[nm + "_min"] = m.min(axis=1)
    amp = pd.DataFrame({y: p[f"r{y}"] - p[f"d{y}"] for y in YS})
    x["amp_pre"], x["amp_post"], x["amp_max"] = amp[[2017, 2018, 2019]].max(axis=1), amp[[2022, 2023, 2024]].mean(axis=1), amp.max(axis=1)
    for c in ("ea_t", "ea_s", "ea_c", "eb_t", "eb_s", "eb_c", "la_t", "la_c", "la_b", "la_u", "la_s", "lb_t", "lb_c", "lb_b", "lb_u", "lb_s", "mon0", "mon24", "water"):
        x[c] = p[c]
    x["tree_drop"], x["crop_rise"], x["mon_drop"] = p.ea_t - p.la_t, p.la_c - p.ea_c, p.mon0 - p.mon24
    x["pid"] = p.pid.values
    g = x.groupby("pid")
    o = pd.concat([g.median().add_suffix("_med"), g.max().add_suffix("_max")], axis=1)
    tc = t.astype(float).assign(pid=p.pid.values).groupby("pid").mean().add_prefix("frac_")
    ts = ts_pass(sf, (.15, .15, 0, 9)).groupby(p.pid).sum().rename("npass")
    return o.join(tc).join(ts)


def emb_feats(pids):
    rows = [json.loads(l) for l in open(WORK / "emb_points.jsonl")]
    e = pd.DataFrame(rows).set_index("pid").reindex(pids)
    ys = list(range(2017, 2025))
    A = np.stack([e[[f"y{y}_{i:02d}" for i in range(64)]].values for y in ys], axis=1).astype("float32")
    d = np.linalg.norm(A[:, 1:] - A[:, :-1], axis=2)
    o = {f"ed_{y}": d[:, k] for k, y in enumerate(ys[1:])}
    o["ed_max"] = np.nanmax(d, axis=1)
    o["ed_year"] = np.where(np.isnan(d).all(axis=1), np.nan, np.nanargmax(np.nan_to_num(d, nan=-1), axis=1))
    pre, post = np.nanmean(A[:, :3], axis=1), np.nanmean(A[:, 5:8], axis=1)
    o["ed_prepost"] = np.linalg.norm(post - pre, axis=1)
    out = pd.DataFrame(o, index=pids)
    out = pd.concat([out, pd.DataFrame(post - pre, index=pids).add_prefix("ediff_"), pd.DataFrame(pre, index=pids).add_prefix("epre_"), pd.DataFrame(post, index=pids).add_prefix("epost_")], axis=1)
    return out


def prithvi_feats(pids):
    z = np.load(WORK / "prithvi_points.npz")
    d = pd.DataFrame(z["post"] - z["pre"], index=z["pid"]).reindex(pids).add_prefix("pd_")
    d["pd_norm"] = np.linalg.norm(d.values, axis=1)
    return d


def fit(kind, Xtr, ytr, wtr):
    if kind == "hgb":
        m = HGB(max_depth=3, learning_rate=.05, max_iter=150, l2_regularization=2.0, min_samples_leaf=15, random_state=1)
        return m.fit(Xtr, ytr, sample_weight=wtr)
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=.02, max_iter=2000))
    return m.fit(Xtr, ytr, logisticregression__sample_weight=wtr)


def pick(s, y, w, target):
    """Threshold from training-beat scores only."""
    best = None
    for th in np.unique(np.quantile(s, np.linspace(.3, .995, 80))):
        pr, re = wpr(y, (s >= th).astype(int), w)
        if not np.isfinite(pr) or pr == 0:
            continue
        if target is None:
            v = 2 * pr * re / (pr + re + 1e-9)
        elif target == .75:
            v = re if pr >= .75 else -1
        else:
            v = pr if re >= .70 else -1
        if v >= 0 and (best is None or v > best[0]):
            best = (v, th)
    return best[1] if best else np.inf


def model(view, track="all"):
    p = load()
    L = labels().set_index("pid")
    L = L[L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    sf = series_feats(p)
    t = triggers(p, sf)
    F = feats(p, sf, t).reindex(L.index)
    cand = t[NETS["+ NBR" if track == "tree" else "+ scrub tight"]].any(axis=1).groupby(p.pid).any().reindex(L.index).fillna(False).values
    base = (t["rule"] & ts_pass(sf, (.15, .15, 0, 9))).groupby(p.pid).sum().reindex(L.index).fillna(0).ge(2).values
    if view == "ts":
        X = F
    elif view == "emb":
        X = emb_feats(L.index)
    elif view == "both":
        X = pd.concat([F, emb_feats(L.index)], axis=1)
    elif view == "prithvi":
        X = prithvi_feats(L.index)
    elif view == "ts_same_rows":     # time-series features on exactly the points Prithvi has, for a fair comparison
        X = F[prithvi_feats(L.index).pd_norm.notna().values].reindex(L.index)
    else:
        X = pd.concat([F, prithvi_feats(L.index)], axis=1)
    is_ref = (L.set == "blind_reference").values
    keep = np.ones(len(L), bool)
    if track == "tree":     # tree loss only: conversions and my farmland labels are a different question
        keep = ~(L.set.isin(["random300"]).values | ((L.set == "bamori_validated").values & (L.cls != "forest_to_crop").values))
    if track == "conv":     # scrub-to-farm: loose net, Bamori and my 13 conversions against unchanged random points and the owner's no-loss points
        cand = t["s2f_loose"].groupby(p.pid).any().reindex(L.index).fillna(False).values
        base = t["s2f_tight"].groupby(p.pid).sum().reindex(L.index).fillna(0).ge(13).values
        keep = (L.set.isin(["random300", "bamori_validated"]).values | (is_ref & (L.y.values == 0))) & (L.cls.fillna("").values != "forest_to_bare")
        is_ref = (L.set == "random300").values
    have = X.notna().any(axis=1).values & cand & keep
    y = L.y.values
    groups = L.group.values
    w_train = np.where(is_ref, L.eval_w.values / max(L.eval_w[is_ref].mean(), 1e-9), 1.0)
    w_train = np.where(L.set.isin(["round1", "round2"]), .5, w_train)
    res = []
    curves = {}
    for kind in ("logistic", "hgb"):
        oof = np.zeros((REPEATS, len(L)))
        ops = {o[0]: np.zeros((REPEATS, len(L)), bool) for o in OPS}
        fold_pos = []
        for rep in range(REPEATS):
            cv = StratifiedGroupKFold(FOLDS, shuffle=True, random_state=rep)
            for tr, te in cv.split(X, y, groups):
                tr = tr[have[tr]]
                m = fit(kind, X.iloc[tr], y[tr], w_train[tr])
                oof[rep, te] = m.predict_proba(X.iloc[te])[:, 1]
                fold_pos.append(dict(rep=rep, guna_pos=int(y[te][is_ref[te]].sum()), guna_bg_pos=int(((L.stratum.values[te] == "background") & (y[te] == 1)).sum()), statewide_pos=int(y[te][L.set.values[te] == "round2"].sum())))
                inner = np.zeros(len(tr))
                for a, b in StratifiedGroupKFold(3, shuffle=True, random_state=rep).split(X.iloc[tr], y[tr], groups[tr]):
                    inner[b] = fit(kind, X.iloc[tr[a]], y[tr[a]], w_train[tr[a]]).predict_proba(X.iloc[tr[b]])[:, 1]
                ri = is_ref[tr]
                for nm, target in OPS:
                    th = pick(inner[ri], y[tr][ri], L.eval_w.values[tr][ri], target)
                    ops[nm][rep, te] = oof[rep, te] >= th
        if track == "conv":
            bm = ((L.set == "bamori_validated") & (L.cls != "forest_to_bare")).values
            for nm, _ in OPS:
                res.append(dict(view=view, model=kind, points="Bamori", op=nm, recall=round(float(np.mean([(ops[nm][r][bm] & cand[bm]).mean() for r in range(REPEATS)])), 3)))
            res.append(dict(view=view, model=kind, points="Bamori", op="tight rule", recall=round(float(base[bm].mean()), 3)))
        for sname, mask, wcol in (("random300" if track == "conv" else "Guna reference", is_ref, L.eval_w.values), ("round2 statewide", (L.set == "round2").values, L.eval_w.values)):
            yy, ww = y[mask], wcol[mask]
            pr, re = wpr(yy, base[mask].astype(int), ww)
            res.append(dict(view=view, model=kind, points=sname, op="current filter + 2 px", precision=round(pr, 3), recall=round(re, 3)))
            for nm, _ in OPS:
                ps = [wpr(yy, (ops[nm][r][mask] & cand[mask]).astype(int), ww) for r in range(REPEATS)]
                res.append(dict(view=view, model=kind, points=sname, op=nm, precision=round(np.nanmean([a for a, _ in ps]), 3), recall=round(np.mean([b for _, b in ps]), 3), p_sd=round(np.nanstd([a for a, _ in ps]), 3), r_sd=round(np.std([b for _, b in ps]), 3)))
            sc = oof.mean(axis=0)[mask] * cand[mask]
            cur = []
            for th in np.quantile(sc[sc > 0], np.linspace(.02, .98, 25)) if (sc > 0).any() else []:
                pr, re = wpr(yy, (sc >= th).astype(int), ww)
                cur.append(dict(view=view, model=kind, points=sname, th=round(th, 4), precision=round(pr, 3), recall=round(re, 3)))
            curves[(kind, sname)] = cur
        print(kind, "positives per fold", pd.DataFrame(fold_pos).describe().loc[["min", "50%", "max"]].round(1).to_dict())
        z = (L.zone.values)
        for zn in np.unique(z[(L.set == "round2").values]):
            mk = (L.set == "round2").values & (z == zn)
            ps = wpr(y[mk], (ops["max F1"][0][mk] & cand[mk]).astype(int), L.eval_w.values[mk])
            res.append(dict(view=view, model=kind, points="round2 " + zn, op="max F1", precision=round(ps[0], 3), recall=round(ps[1], 3), positives=int(y[mk].sum())))
    r = pd.DataFrame(res)
    print(r.to_string())
    r.to_csv(REPORT / f"cascade_model_{track}_{view}.csv", index=False)
    pd.DataFrame([x for v in curves.values() for x in v]).to_csv(REPORT / f"cascade_curve_{track}_{view}.csv", index=False)
    if view == "ts":
        imp = fit("hgb", X[have], y[have], w_train[have])
        print("training rows", int(have.sum()), "positives", int(y[have].sum()))
        from sklearn.inspection import permutation_importance
        q = permutation_importance(imp, X[have], y[have], n_repeats=3, random_state=1, scoring="average_precision")
        print(pd.Series(q.importances_mean, index=X.columns).sort_values(ascending=False).head(12).round(3).to_string())


if __name__ == "__main__":
    stage1() if sys.argv[1] == "stage1" else model(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "all")
