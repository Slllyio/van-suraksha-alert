"""Loss-year check on the owner's dated fellings: the current NBR-window year against the fitted-break year, using flagged pixels in the 50 m box. No GEE.
Both are computed from the same yearly Oct-Nov series. The fitted break needs 2 seasons either side, so it cannot return 2017-18 or 2025. Usage: e71_year_check.py"""
import numpy as np
import pandas as pd

from common import *
from e48_tests import GT, YS, load, rule
from e49_ts import series_feats


def window_year(p):
    """Year of the largest NBR fall between the two seasons before and the two from that year, as on the map (2018-2025)."""
    best, yr = np.full(len(p), -np.inf), np.zeros(len(p), int)
    for y in range(2018, 2026):
        pre = p[[f"lr{a}" for a in (y - 2, y - 1) if a in YS]].mean(axis=1)
        post = p[[f"lr{a}" for a in (y, min(y + 1, 2025))]].mean(axis=1)
        d = (pre - post).fillna(-np.inf).values
        u = d > best
        best, yr = np.where(u, d, best), np.where(u, y, yr)
    return yr


def main():
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    q = g[(g.source == "felling_alert_verdict") & (g.label == 1)]
    print("columns with a year", q.year.notna().sum(), "of", len(q), q.year.describe()[["min", "max"]].to_dict())
    p = load()
    p = p[p.pid.isin(q.pid)].reset_index(drop=True)
    fl = rule(p)[0].values
    sf = series_feats(p)
    d = pd.DataFrame(dict(pid=p.pid, nbr=window_year(p), brk=sf.break_year.values, fl=fl, back=sf.back.values, persist=sf.persist.values))
    d = d[d.fl]
    a = d.groupby("pid")[["nbr", "brk"]].median().round().join(d.groupby("pid")[["back", "persist"]].mean()).join(q.set_index("pid").year.rename("truth")).dropna(subset=["truth"])
    rows = []
    for c, nm in (("nbr", "current NBR window"), ("brk", "fitted break")):
        e = (a[c] - a.truth)
        rows.append(dict(method=nm, n=len(a), exact=int((e == 0).sum()), within_1=int((e.abs() <= 1).sum()), median_error=float(e.median()), mean_abs=round(float(e.abs().mean()), 2), early=int((e < 0).sum()), late=int((e > 0).sum())))
    t = pd.DataFrame(rows)
    print(t.to_string())
    print("true years", a.truth.astype(int).value_counts().sort_index().to_dict())
    print("recovered at the end share", round(float(a.back.mean()), 3), "| seasons low median", a.persist.median())
    t.to_csv(OUT / "interim" / "report" / "year_check.csv", index=False)


if __name__ == "__main__":
    main()
