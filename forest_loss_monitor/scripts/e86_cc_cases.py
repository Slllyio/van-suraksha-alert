"""Case-by-case account of the Guna embedding model at its 90% recall setting, and of what the time-series filters do to each flagged point.
Every label is judged at a 50 m box (polygons at their inner point). 'Before' and 'signal' types come from Dynamic World 2017-19 vs 2022-24 and Sentinel-2 Oct-Nov NDVI/NBR, not from looking at imagery.
Offline. Usage: e86_cc_cases.py"""
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd

from common import OUT
from e49_ts import series_feats, ts_pass
from e63_cascade import feats, triggers
from e76_cc_train import REPORT, load, ref_w, wpr
from e77_cc_local import design, wide
from e79_cc_fusion import boot, cv_view, flags_at, px_table
from e83_cc_pxmodel import px_features

warnings.filterwarnings("ignore")
REPEATS = 10
S1_TARGET, S2_TARGET = .9, .7
FALLS = (.15, .15, 0, 9)          # fitted-break fall in Oct-Nov NDVI and NBR, as in the running rule
SRC = "E:/e_Netra/outputs/local_detector/reference_sample/reference_worksheet.csv"


def describe(p, sf):
    """Median over the 25 pixels of each box."""
    amp = lambda ys: np.nanmean(np.stack([(p[f"r{y}"] - p[f"d{y}"]).values for y in ys]), axis=0)
    x = pd.DataFrame(dict(pid=p.pid.values, trees_early=p.ea_t.values, shrub_early=p.ea_s.values, crops_early=p.ea_c.values, trees_late=p.la_t.values, shrub_late=p.la_s.values, crops_late=p.la_c.values, bare_late=p.la_b.values, built_late=p.la_u.values,
                           ndvi_pre=p[[f"ln{y}" for y in (2017, 2018, 2019)]].mean(axis=1).values, ndvi_post=p[[f"ln{y}" for y in (2023, 2024, 2025)]].mean(axis=1).values,
                           rabi_cycle_pre=amp((2017, 2018, 2019)), rabi_cycle_post=amp((2023, 2024, 2025)), ndvi_fall=sf.drop_n.values, nbr_fall=sf.drop_r.values, pre_scatter=sf.pre_sd.values,
                           ts_break_year=sf.break_year.replace(0, np.nan).values, water=p.water.values))
    return x.groupby("pid").median()


def before_type(r):
    if r.water >= 5:
        return "water or shore"
    if r.trees_early >= .30:
        return "tree cover"
    if r.crops_early >= .30:
        return "cropland"
    if r.trees_early + r.shrub_early >= .40:
        return "scrub"
    return "bare, grass or mixed"


def signal(r):
    if r.water >= 5:
        return "water level"
    if r.trees_early - r.trees_late >= .12 and r.ndvi_fall >= .08:
        return "tree cover and greenness fell"
    if r.crops_late - r.crops_early >= .15:
        return "crop cover rose"
    if r.ndvi_fall >= .15:
        return "greenness fell, cover class steady"
    if r.ndvi_post - r.ndvi_pre >= .08:
        return "got greener"
    return "no clear optical change"


def outcome(y, f):
    return np.select([(y == 1) & f, (y == 1) & ~f, (y == 0) & f, (y == 0) & ~f], ["caught", "missed", "false alarm", "correctly ignored"], "not scored")


def show(title, t):
    print("\n##", title)
    print(t.to_string())


def main():
    d, A = load()
    scal = px_features(d, A, wide(d))[0]
    y, w = d.y.values, ref_w(d)
    k = (d.set == "reference").values
    X, sc, ve = design({"step": scal}, ("step",))
    emb = [cv_view(X, d, y, sc, ve, r) for r in range(REPEATS)]
    s1_each = [flags_at(a, b, y, w, k, S1_TARGET) for a, b in emb]
    s1 = np.mean(s1_each, axis=0) >= .5
    p = px_table(d)
    sf = series_feats(p)
    t = triggers(p, sf)
    Fx = feats(p, sf, t).reindex(d.cid).values
    npass = ts_pass(sf, FALLS).groupby(p.pid).sum().reindex(d.cid).fillna(0).values
    ts = [cv_view(Fx, d, y, list(range(Fx.shape[1])), [], r) for r in range(REPEATS)]
    both = [((a + c) / 2, [(u[0], u[1], (u[2] + v[2]) / 2) for u, v in zip(b, f)]) for (a, b), (c, f) in zip(emb, ts)]
    learned = np.mean([flags_at(a, b, y, w, k, S2_TARGET, g) for (a, b), g in zip(both, s1_each)], axis=0) >= .5
    D = describe(p, sf).reindex(d.cid).reset_index(drop=True)
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == "Guna"].drop_duplicates("Beat").set_index("Beat").Range
    notes = pd.read_csv(SRC).set_index("point_id").notes
    c = pd.concat([d[["cid", "set", "id", "y", "cls", "stratum", "beat", "ha", "year"]], D], axis=1)
    c["range"] = c.beat.map(lk)
    c["owner_note"] = c.id.map(notes)
    c["before"] = [before_type(r) for r in D.itertuples()]
    c["signal"] = [signal(r) for r in D.itertuples()]
    c["emb_t_median"], c["emb_t_q90"], c["emb_t_max"], c["emb_noise"] = scal[:, 0].round(2), scal[:, 2].round(2), scal[:, 3].round(2), scal[:, 21].round(3)
    c["emb_break_year"] = 2017 + np.round(scal[:, 20]).astype(int)
    c["emb_score"] = np.nanmean([a for a, _ in emb], axis=0).round(2)
    c["ts_pixels_passing"] = npass.astype(int)
    c["stage1"] = outcome(y, s1)
    variants = {"fixed falls, 1 px": s1 & (npass >= 1), "fixed falls, 2 px": s1 & (npass >= 2), "fixed falls, 5 px": s1 & (npass >= 5), "learned, embeddings + time series": learned}
    for nm, f in variants.items():
        c["after " + nm] = np.where(s1, np.where(f, "kept", "removed"), "")
    c.round(3).to_csv(REPORT / "cc_cases.csv", index=False)
    ref = c[k]
    show("stage 1 on the reference, by stratum", pd.crosstab(ref.stratum, ref.stage1))
    p0, r0 = wpr(y[k], s1[k].astype(int), w[k])
    print("stage 1 weighted precision", round(p0, 3), "recall", round(r0, 3))
    show("reference, stage-1 outcome by land type before", pd.crosstab(ref.before, ref.stage1))
    show("reference, stage-1 outcome by signal", pd.crosstab(ref.signal, ref.stage1))
    show("reference negatives: false alarm vs ignored, by stratum and land type", pd.crosstab([ref.stratum[ref.y == 0], ref.before[ref.y == 0]], ref.stage1[ref.y == 0]))
    show("reference negatives: false alarm vs ignored, by stratum and signal", pd.crosstab([ref.stratum[ref.y == 0], ref.signal[ref.y == 0]], ref.stage1[ref.y == 0]))
    num = ["emb_t_median", "emb_t_q90", "emb_t_max", "emb_noise", "trees_early", "shrub_early", "crops_early", "trees_late", "crops_late", "bare_late", "ndvi_pre", "ndvi_post", "ndvi_fall", "nbr_fall", "pre_scatter", "rabi_cycle_pre", "rabi_cycle_post", "ts_pixels_passing"]
    show("reference medians by outcome", ref.groupby("stage1")[num].median().T.round(3))
    show("reference medians by stratum and outcome, negatives", ref[ref.y == 0].groupby(["stratum", "stage1"])[num].median().T.round(3))
    show("reference by range", pd.crosstab(ref.range.fillna("?"), ref.stage1))
    show("embedding break year, reference", pd.crosstab(ref.emb_break_year, ref.stage1))
    show("owner notes on reference negatives", ref[(ref.y == 0) & ref.owner_note.notna()][["id", "stratum", "stage1", "before", "signal", "owner_note"]])
    show("the two missed losses and the background losses", ref[(ref.y == 1) & ((ref.stage1 == "missed") | (ref.stratum == "background"))][["id", "beat", "stratum", "stage1", "before", "signal", "emb_t_max", "emb_score", "trees_early", "trees_late", "ndvi_fall", "ts_pixels_passing"] + ["after " + v for v in variants]])
    oth = c[~k & (c.y >= 0)]
    show("other label sets at stage 1", pd.crosstab([oth.set, oth.y], oth.stage1))
    bf = c[c.set == "bamori_fp"]
    show("Bamori false alarms by owner note", pd.crosstab(bf.cls, bf.stage1))
    show("Bamori false alarms by land type", pd.crosstab(bf.before, bf.stage1))
    show("Bamori false alarms by signal", pd.crosstab(bf.signal, bf.stage1))
    show("Bamori false alarms medians", bf.groupby("stage1")[num + ["ha"]].median().T.round(3))
    rn = c[c.set == "random"]
    show("random forest points by land type", pd.crosstab(rn.before, rn.stage1, margins=True))
    show("random forest points by signal", pd.crosstab(rn.signal, rn.stage1, margins=True))
    bt = c[(c.set == "bamori_tp")]
    show("Bamori changes by owner class", pd.crosstab(bt.cls, s1[bt.index]))
    res = []
    for nm, f in variants.items():
        pr, re = wpr(y[k], f[k].astype(int), w[k])
        ci = boot(d, f)
        col = "after " + nm
        res.append(dict(filter=nm, precision=round(pr, 3), p_ci=ci[0], recall=round(re, 3), r_ci=ci[1], ref_false_alarms_removed=f"{int(((ref.stage1 == 'false alarm') & (ref[col] == 'removed')).sum())}/{int((ref.stage1 == 'false alarm').sum())}",
                        ref_losses_lost=f"{int(((ref.stage1 == 'caught') & (ref[col] == 'removed')).sum())}/{int((ref.stage1 == 'caught').sum())}", random_flag_pct=round(100 * f[(d.set == 'random').values].mean(), 1)))
        fa, ca = ref[ref.stage1 == "false alarm"], ref[ref.stage1 == "caught"]
        show(f"{nm}: reference false alarms by stratum", pd.crosstab(fa.stratum, fa[col]))
        show(f"{nm}: reference false alarms by land type", pd.crosstab(fa.before, fa[col]))
        show(f"{nm}: reference false alarms by signal", pd.crosstab(fa.signal, fa[col]))
        show(f"{nm}: real losses by land type", pd.crosstab(ca.before, ca[col]))
        show(f"{nm}: real losses by signal", pd.crosstab([ca.stratum, ca.signal], ca[col]))
        of = c[~k & (c.stage1.isin(["false alarm", "caught"]))]
        show(f"{nm}: other sets", pd.crosstab([of.set, of.stage1], of[col]))
        show(f"{nm}: Bamori false alarms by owner note", pd.crosstab(bf.cls[bf.stage1 == "false alarm"], bf[col][bf.stage1 == "false alarm"]))
        show(f"{nm}: Bamori changes by owner class", pd.crosstab(bt.cls[s1[bt.index]], bt[col][s1[bt.index]]))
        show(f"{nm}: random flagged by land type", pd.crosstab(rn.before[rn.stage1 == "false alarm"], rn[col][rn.stage1 == "false alarm"]))
    r = pd.DataFrame(res)
    r.to_csv(REPORT / "cc_cases_filters.csv", index=False)
    show("filters after stage 1", r)
    fa = ref[ref.stage1 == "false alarm"]
    show("medians of reference false alarms kept vs removed by fixed falls 2 px", fa.groupby("after fixed falls, 2 px")[num].median().T.round(3))


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200, "display.max_colwidth", 60)
    main()
