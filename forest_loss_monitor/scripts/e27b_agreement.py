"""My blind labels of 110 reference points from 30 m chips, against the owner's Google Earth labels (treated as the reference).
1 = visible loss at the marked pixel. Half the points are the owner's loss points, by design, so these rates are not area-weighted."""
import pandas as pd

from common import ROOT

MINE = {1, 8, 11, 12, 33, 46, 49, 59, 60, 68, 76, 84, 91, 107}
d = ROOT / "ground_truth" / "agreement"
k = pd.read_csv(d / "key.csv")
k["mine"] = k.sample_id.isin(MINE).astype(int)
k.to_csv(d / "labels.csv", index=False)
print(pd.crosstab(k.label, k.mine, rownames=["owner"], colnames=["mine"]).to_string())
tp = ((k.label == 1) & (k.mine == 1)).sum()
print("agreement %.2f" % (k.label == k.mine).mean(), "I caught %d of %d owner losses (%.0f%%)" % (tp, k.label.sum(), 100 * tp / k.label.sum()),
      "my loss calls that owner agrees with %d of %d" % (tp, k.mine.sum()))
print(k[k.label == 1].cls.fillna("none").str.strip().value_counts().head(8).to_dict())
print(k[(k.label == 1) & (k.mine == 0)].cls.fillna("none").str.strip().value_counts().head(8).to_dict())
