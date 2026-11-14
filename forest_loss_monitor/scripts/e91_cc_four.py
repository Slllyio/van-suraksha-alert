"""Four approaches on the owner's 284 reference points, same held-out 5 km blocks for all:
  1 embeddings only; 2 + Sentinel-2 temporal features; 3 + Sentinel-1; 4 + spatial patch features and a disturbance-type classifier (tree loss, scrub conversion, non-forest change, no loss).
Stage 1 is the embedding model at 90% area-weighted recall. Each approach then re-scores the stage-1 flags; its threshold is set on training blocks to keep a fixed share of the real losses stage 1 caught there.
Point-level and area-weighted results are reported side by side for the same flags. Usage: e91_cc_four.py logistic|hgb [repeats]"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
KIND = sys.argv[1] if len(sys.argv) > 1 else "logistic"
REPEATS = int(sys.argv[2]) if len(sys.argv) > 2 else 10
sys.argv = sys.argv[:1]          # imported scripts read argv

import numpy as np
import pandas as pd
from scipy.ndimage import label
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from e49_ts import series_feats
from e63_cascade import feats, triggers
from e76_cc_train import REPORT, WORK, load, ref_w, thr_for, wpr
from e77_cc_local import wide
from e79_cc_fusion import px_table
from e83_cc_pxmodel import px_features
from e85_cc_area import BOX_HALF, F as WIN, grid
from e89_cc_second import new_feats

warnings.filterwarnings("ignore")
FOLDS, S1_TARGET = 5, .9
KEEP = (1.0, .95, .9, .8)
SEED = 20261106
CLASSES = ["no loss", "tree loss", "scrub conversion", "non-forest change"]


def classes(d):
    """What kind of change, from the owner's label sets only."""
    k = np.zeros(len(d), int)
    k[(d.set.isin(["felling", "recall_kit", "recent_new", "reference"]) & (d.y == 1)).values | ((d.set == "bamori_tp") & d.cls.isin(["forest_to_crop", "forest_to_bare"])).values] = 1
    k[((d.set == "bamori_tp") & d.cls.isin(["shrub_to_crop", "unspecified"])).values] = 2
    k[(d.set == "bamori_fp").values | ((d.set == "bamori_tp") & (d.cls == "bare_to_crop")).values] = 3
    return k


def spatial(d):
    """Shape of the embedding break around the point, from its 300 m window: contrast with surroundings, and the patch that touches the box at three thresholds."""
    pos = {c: i for i, c in enumerate(d.cid)}
    out = np.full((len(d), 17), np.nan)
    for l in open(WIN):
        r = json.loads(l)
        i = pos.get(r["cid"])
        if i is None:
            continue
        g, x0, y1 = grid(r)
        g = np.where(np.isfinite(g), g, np.nan)
        c = np.zeros(g.shape, bool)
        cr, cc, n = int((y1 - d.y_m[i]) / 10), int((d.x[i] - x0) / 10), BOX_HALF // 10
        c[max(cr - n, 0):cr + n + 1, max(cc - n, 0):cc + n + 1] = True
        med = np.nanmedian(g)
        gy, gx = np.gradient(np.nan_to_num(g, nan=med))
        f = [np.nanmax(g[c]) - np.nanmedian(g[~c]), (np.nanquantile(g[c], .9) - med) / (1.4826 * np.nanmedian(np.abs(g - med)) + .05), np.nanmedian(g[~c]), np.nanstd(g), np.hypot(gy, gx)[c].mean()]
        for th in (2.0, 2.5, 3.0):
            m = np.nan_to_num(g, nan=-9) >= th
            lab, _ = label(m, structure=np.ones((3, 3)))
            ids = np.unique(lab[c])
            ids = ids[ids > 0]
            if len(ids):
                p = lab == ids[np.argmax(np.bincount(lab.ravel())[ids])]
                rr, cc2 = np.nonzero(p)
                f += [p.sum() * .01, p.sum() / ((np.ptp(rr) + 1) * (np.ptp(cc2) + 1)), float(p[0].any() or p[-1].any() or p[:, 0].any() or p[:, -1].any()), m.mean()]
            else:
                f += [0., 0., 0., m.mean()]
        out[i] = f
    return out


def make(scal, vec, multi):
    tf = [("s", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), scal)] + [(f"v{i}", make_pipeline(StandardScaler(), PCA(8, random_state=0)), v) for i, v in enumerate(vec)]
    if KIND == "logistic":
        head = LogisticRegression(C=.05, max_iter=4000, class_weight="balanced")
    else:
        head = HistGradientBoostingClassifier(max_depth=3, learning_rate=.05, max_iter=120, min_samples_leaf=15, l2_regularization=2.0, class_weight="balanced", random_state=1)
    return make_pipeline(ColumnTransformer(tf), head)


def loss_prob(m, X):
    p = m.predict_proba(X)
    cl = m.classes_
    return p[:, np.isin(cl, [1, 2])].sum(axis=1) if len(cl) > 2 else p[:, 1]


def run_cv(X, scal, vec, target, tmask, folds, strat, g, rep, pred=None):
    """Held-out score for every point, and for each fold the scores its own training points get from inner folds (never from a model that saw them)."""
    n = len(target)
    s, out = np.full(n, np.nan), []
    multi = len(np.unique(target)) > 2
    for tr, te in folds:
        trm = tr[tmask[tr]]
        m = make(scal, vec, multi).fit(X[trm], target[trm])
        s[te] = loss_prob(m, X[te])
        if pred is not None:
            pred[te] = m.predict(X[te])
        inner = np.full(n, np.nan)
        for a, b in StratifiedGroupKFold(3, shuffle=True, random_state=rep).split(trm, strat[trm], g[trm]):
            inner[trm[b]] = loss_prob(make(scal, vec, multi).fit(X[trm[a]], target[trm[a]]), X[trm[b]])
        out.append((tr, te, inner))
    return s, out


def boot(ref_beat, y, w, f, n=1000):
    rng = np.random.default_rng(SEED)
    idx = {b: np.flatnonzero(ref_beat == b) for b in np.unique(ref_beat)}
    P, R, PP = [], [], []
    for _ in range(n):
        i = np.concatenate([idx[b] for b in rng.choice(list(idx), len(idx))])
        p, r = wpr(y[i], f[i].astype(int), w[i])
        if np.isfinite(p):
            P.append(p)
        R.append(r)
        if f[i].sum():
            PP.append((f[i] & (y[i] == 1)).sum() / f[i].sum())
    q = lambda v: f"{np.quantile(v, .025):.2f}-{np.quantile(v, .975):.2f}"
    return q(P), q(R), q(PP)


def main():
    d, A = load()
    n = len(d)
    scal, chg, lchg, _, _ = px_features(d, A, wide(d))
    p = px_table(d)
    sf = series_feats(p)
    Fx = feats(p, sf, triggers(p, sf)).reindex(d.cid).values
    N = new_feats(d)
    radar = N[[c for c in N if c.split(":")[0] in ("dry_vv", "dry_vh", "leaf_vv", "leaf_vh", "dry_ratio", "leaf_ratio")]].values
    Sp = spatial(d)
    print("points with spatial window", int(np.isfinite(Sp).all(axis=1).sum()), "of", n, flush=True)
    s2_year = sf.break_year.replace(0, np.nan).groupby(p.pid).median().reindex(d.cid).values
    timing = np.c_[np.abs(2017 + scal[:, 20] - s2_year), 2017 + scal[:, 20]]
    kcls = classes(d)
    ybin = np.isin(kcls, [1, 2]).astype(int)
    assert (ybin[d.y.values >= 0] == d.y.values[d.y.values >= 0]).all()
    w, g = ref_w(d), d.block.values
    k = (d.set == "reference").values
    labelled, everyone = d.y.values >= 0, np.ones(n, bool)

    def cols(*blocks):
        X = np.hstack(blocks)
        return X, list(range(X.shape[1]))

    X1, c1 = cols(scal)
    X2, c2 = cols(scal, Fx)
    X3, c3 = cols(scal, Fx, radar)
    Xs, cs = cols(scal, Fx, radar, Sp, timing)
    X4 = np.hstack([Xs, chg, lchg])
    v4 = [list(range(Xs.shape[1], Xs.shape[1] + 64)), list(range(Xs.shape[1] + 64, Xs.shape[1] + 128))]
    approaches = {"1 embeddings only": (X1, c1, [], ybin, labelled),
                  "2 + Sentinel-2 temporal": (X2, c2, [], ybin, labelled),
                  "3 + Sentinel-1": (X3, c3, [], ybin, labelled),
                  "4 + spatial + disturbance type": (X4, cs, v4, kcls, everyone),
                  "4a same features, loss / no loss only": (X4, cs, v4, ybin, everyone),
                  "4b disturbance type, no spatial features": (X3, c3, [], kcls, everyone)}
    S = {a: [] for a in approaches}
    pred = np.full((REPEATS, n), -1)
    gates = []
    for rep in range(REPEATS):
        folds = list(StratifiedGroupKFold(FOLDS, shuffle=True, random_state=rep).split(np.zeros(n), kcls, g))
        for a, (X, sc, ve, tgt, tm) in approaches.items():
            S[a].append(run_cv(X, sc, ve, tgt, tm, folds, kcls, g, rep, pred[rep] if a.startswith("4 ") else None))
        s, fo = S["1 embeddings only"][-1]
        gate, gate_in = np.zeros(n, bool), []
        for tr, te, inner in fo:
            ri = tr[k[tr] & np.isfinite(inner[tr])]
            th = thr_for(inner[ri], ybin[ri], w[ri], S1_TARGET)
            gate[te] = s[te] >= th
            gate_in.append(inner >= th)
        gates.append((gate, gate_in))
        print("repeat", rep, flush=True)
    s1 = np.mean([a for a, _ in gates], axis=0) >= .5
    y = ybin
    beat = d.beat.values[k]
    rows, keepflags = [], {}

    def report(name, keep, fl):
        f = np.mean(fl, axis=0) >= .5
        fk = f[k]
        tp, fp = int((fk & (y[k] == 1)).sum()), int((fk & (y[k] == 0)).sum())
        pw, rw = wpr(y[k], fk.astype(int), w[k])
        pc, rc, ppc = boot(beat, y[k], w[k], fk)
        each = [(x[k] & (y[k] == 1)).sum() / max(x[k].sum(), 1) for x in fl]
        bg = k & (d.stratum == "background").values
        row = dict(approach=name, keep_target=keep, losses_kept=f"{tp}/{int((s1[k] & (y[k] == 1)).sum())}", false_alarms=fp, background_false=int((f & bg & (y == 0)).sum()), background_losses=f"{int((f & bg & (y == 1)).sum())}/6",
                   point_precision=round(tp / max(tp + fp, 1), 3), point_p_range=ppc, point_p_mean=round(float(np.mean(each)), 3), point_p_sd=round(float(np.std(each)), 3), point_recall=round(tp / int(y[k].sum()), 3),
                   area_precision=round(pw, 3), area_p_range=pc, area_recall=round(rw, 3), area_r_range=rc, random_flag_pct=round(100 * f[(d.set == "random").values].mean(), 1))
        for nm, q in (("bamori_rejected", d.set == "bamori_fp"), ("bare_to_crop", (d.set == "bamori_tp") & (d.cls == "bare_to_crop")), ("forest_to_crop", (d.set == "bamori_tp") & (d.cls == "forest_to_crop")),
                      ("shrub_to_crop", (d.set == "bamori_tp") & (d.cls == "shrub_to_crop")), ("fellings", (d.set == "felling") & (d.y == 1)), ("rejected_fellings", d.set.isin(["felling", "recall_kit", "recent_new"]) & (d.y == 0))):
            row[nm] = f"{int(f[q.values].sum())}/{int(q.sum())}"
        rows.append(row)
        keepflags[f"{name} @ {keep}"] = f
        print(json.dumps(row), flush=True)

    report("stage 1 (embeddings at 90% area recall)", "", [a for a, _ in gates])
    aucs = []
    for a in approaches:
        for keep in KEEP:
            fl = []
            for (s, fo), (gate, gate_in) in zip(S[a], gates):
                f = np.zeros(n, bool)
                for (tr, te, inner), gi in zip(fo, gate_in):
                    ri = tr[k[tr] & (y[tr] == 1) & gi[tr] & np.isfinite(inner[tr])]
                    th = np.quantile(inner[ri], 1 - keep, method="lower") if len(ri) else -np.inf
                    f[te] = gate[te] & (s[te] >= th)
                fl.append(f)
            report(a, keep, fl)
        q = k & s1
        aucs.append(dict(approach=a, auc_point=round(float(np.mean([roc_auc_score(y[q], s[q]) for s, _ in S[a]])), 3), auc_area=round(float(np.mean([roc_auc_score(y[q], s[q], sample_weight=w[q]) for s, _ in S[a]])), 3),
                         auc_point_all_reference=round(float(np.mean([roc_auc_score(y[k], s[k]) for s, _ in S[a]])), 3), auc_area_all_reference=round(float(np.mean([roc_auc_score(y[k], s[k], sample_weight=w[k]) for s, _ in S[a]])), 3)))
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / f"cc_four_{KIND}.csv", index=False)
    pd.DataFrame(aucs).to_csv(REPORT / f"cc_four_auc_{KIND}.csv", index=False)
    pd.concat([d[["cid", "set", "id", "y", "cls", "stratum", "beat"]], pd.DataFrame(keepflags)], axis=1).assign(true_class=[CLASSES[i] for i in kcls], predicted_class=[CLASSES[i] if i >= 0 else "" for i in pred[0]]).to_csv(REPORT / f"cc_four_points_{KIND}.csv", index=False)
    pd.set_option("display.width", 330, "display.max_columns", 40, "display.max_colwidth", 50)
    print(t.to_string())
    print(pd.DataFrame(aucs).to_string())
    print("\nHeld-out disturbance type, approach 4, first repeat (rows true, columns predicted)")
    print(pd.crosstab(pd.Series([CLASSES[i] for i in kcls], name="true"), pd.Series([CLASSES[i] for i in pred[0]], name="predicted")).to_string())
    print(pd.crosstab([d.set, pd.Series([CLASSES[i] for i in kcls], name="true")], pd.Series([CLASSES[i] for i in pred[0]], name="predicted")).to_string())


if __name__ == "__main__":
    main()
