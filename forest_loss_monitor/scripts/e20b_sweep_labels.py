"""Blind labels of the sweep chips: the CCDC-flagged stable pixels plus 15 random unflagged per stratum. U = ambiguous at 30 m."""
import pandas as pd

from common import OUT

D = OUT / "timeseries" / "sweep_review"
A = {6, 10, 12, 13, 16, 17, 27, 30, 32, 33, 35, 39, 43}
U = {3, 19}
k = pd.read_csv(D / "key.csv")
k["label"] = k.chip_id.map(lambda i: "U" if i in U else "A" if i in A else "N")
k.to_csv(D / "labels.csv", index=False)
print(pd.crosstab([k.stratum, k.flag], k.label).to_string())
print(k[k.flag][["chip_id", "stratum", "size", "year", "label"]].to_string(index=False))
