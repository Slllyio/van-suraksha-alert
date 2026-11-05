"""Do the newly labelled stage-1 flags help? 58 new flags in background tree cover, labelled blind from Sentinel-2 strips (e93): 'no visible change' joins the no-loss class as hard negatives,
'clearing' joins tree loss; thinning and water are left out as ambiguous. Same held-out 5 km blocks and reference scoring as e91; stage 1 is unchanged, so every row re-scores the same flags.
Usage: e95_cc_hardneg.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
sys.argv = [sys.argv[0], "logistic", "10"]

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

import e91_cc_four as m
from e49_ts import series_feats
from e63_cascade import feats, triggers
from e76_cc_train import GT, REPORT, load, ref_w, thr_for, wpr
from e77_cc_local import wide
from e79_cc_fusion import px_table
from e83_cc_pxmodel import CACHE, px_features
from e89_cc_second import new_feats

warnings.filterwarnings("ignore")
REPEATS, KEEP = 10, (1.0, .95, .9, .8)


def main():
    if CACHE.exists():
        CACHE.unlink()               # built before the new points existed
    d, A = load()
    n = len(d)
    lab = pd.read_csv(GT / "cc_strips_labelled.csv", keep_default_na=False).set_index("cid").label
    mine = d.cid.map(lab).fillna("").values
    new = (d.set == "new_flag").values
    scal, chg, lchg, _, _ = px_features(d, A, wide(d))
    p = px_table(d)
    sf = series_feats(p)
    Fx = feats(p, sf, triggers(p, sf)).reindex(d.cid).values
    N = new_feats(d)
    radar = N[[c for c in N if c.split(":")[0] in ("dry_vv", "dry_vh", "leaf_vv", "leaf_vh", "dry_ratio", "leaf_ratio")]].values
    Sp = m.spatial(d)
    s2_year = sf.break_year.replace(0, np.nan).groupby(p.pid).median().reindex(d.cid).values
    Xs = np.hstack([scal, Fx, radar, Sp, np.c_[np.abs(2017 + scal[:, 20] - s2_year), 2017 + scal[:, 20]]])
    X4 = np.hstack([Xs, chg, lchg])
    v4 = [list(range(Xs.shape[1], Xs.shape[1] + 64)), list(range(Xs.shape[1] + 64, Xs.shape[1] + 128))]
    cs = list(range(Xs.shape[1]))
    kcls = m.classes(d)
    kcls[new & (mine == "C")] = 1
    ybin = np.isin(kcls, [1, 2]).astype(int)
    old = ~new
    labelled_old = (d.y.values >= 0) & old
    usable_new = new & np.isin(mine, ["N", "C"])
    print("new flags used:", int(usable_new.sum()), "as no loss:", int((new & (mine == "N")).sum()), "as tree loss:", int((new & (mine == "C")).sum()), flush=True)
    w, g, k = ref_w(d), d.block.values, (d.set == "reference").values
    c1 = list(range(scal.shape[1]))
    runs = {"1 embeddings only": (scal, c1, [], ybin, labelled_old),
            "1 embeddings only + new labels": (scal, c1, [], ybin, labelled_old | usable_new),
            "4 spatial + disturbance type": (X4, cs, v4, kcls, old),
            "4 spatial + disturbance type + new labels": (X4, cs, v4, kcls, old | usable_new)}
    S, gates = {a: [] for a in runs}, []
    for rep in range(REPEATS):
        folds = list(StratifiedGroupKFold(m.FOLDS, shuffle=True, random_state=rep).split(np.zeros(n), kcls, g))
        for a, (X, sc, ve, tgt, tm) in runs.items():
            S[a].append(m.run_cv(X, sc, ve, tgt, tm, folds, kcls, g, rep))
        s, fo = S["1 embeddings only"][-1]
        gate, gate_in = np.zeros(n, bool), []
        for tr, te, inner in fo:
            ri = tr[k[tr] & np.isfinite(inner[tr])]
            th = thr_for(inner[ri], ybin[ri], w[ri], m.S1_TARGET)
            gate[te] = s[te] >= th
            gate_in.append(inner >= th)
        gates.append((gate, gate_in))
        print("repeat", rep, flush=True)
    y, beat, rows = ybin, d.beat.values[k], []
    s1 = np.mean([a for a, _ in gates], axis=0) >= .5
    for a in runs:
        for keep in KEEP:
            fl = []
            for (s, fo), (gate, gate_in) in zip(S[a], gates):
                f = np.zeros(n, bool)
                for (tr, te, inner), gi in zip(fo, gate_in):
                    ri = tr[k[tr] & (y[tr] == 1) & gi[tr] & np.isfinite(inner[tr])]
                    f[te] = gate[te] & (s[te] >= (np.quantile(inner[ri], 1 - keep, method="lower") if len(ri) else -np.inf))
                fl.append(f)
            f = np.mean(fl, axis=0) >= .5
            fk = f[k]
            tp, fp = int((fk & (y[k] == 1)).sum()), int((fk & (y[k] == 0)).sum())
            pw, rw = wpr(y[k], fk.astype(int), w[k])
            pc, rc, ppc = m.boot(beat, y[k], w[k], fk)
            bg = k & (d.stratum == "background").values
            rows.append(dict(approach=a, keep_target=keep, losses_kept=f"{tp}/{int((s1[k] & (y[k] == 1)).sum())}", false_alarms=fp, background_false=int((f & bg & (y == 0)).sum()), background_losses=f"{int((f & bg & (y == 1)).sum())}/6",
                             point_precision=round(tp / max(tp + fp, 1), 3), point_p_range=ppc, area_precision=round(pw, 3), area_p_range=pc, area_recall=round(rw, 3), area_r_range=rc,
                             random_flag_pct=round(100 * f[(d.set == "random").values].mean(), 1), new_flags_no_change_still_flagged=f"{int(f[new & (mine == 'N')].sum())}/{int((new & (mine == 'N')).sum())}",
                             new_flags_clearing_kept=f"{int(f[new & (mine == 'C')].sum())}/{int((new & (mine == 'C')).sum())}"))
            print(json.dumps(rows[-1]), flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_hardneg.csv", index=False)
    pd.set_option("display.width", 330, "display.max_columns", 40, "display.max_colwidth", 46)
    print(t.to_string())


if __name__ == "__main__":
    main()
