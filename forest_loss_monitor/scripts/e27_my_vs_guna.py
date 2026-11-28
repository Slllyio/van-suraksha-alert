"""Blind agreement check: I label a mix of the owner's reference points from the same 30 m chips used for my validation rounds."""
import numpy as np
import pandas as pd

from calibrate_sample import sheets
from chips import make_chips
from common import *

GT = ROOT / "ground_truth"
ref = pd.read_csv(GT / "guna_labels.csv")
ref = ref[ref.source == "blind_reference"]
rng = np.random.default_rng(99)
k = pd.concat([ref[ref.label == 1], ref[ref.label == 0].iloc[rng.choice((ref.label == 0).sum(), 55, replace=False)]]).sample(frac=1, random_state=99).reset_index(drop=True)
k["sample_id"] = np.arange(1, len(k) + 1)
d = GT / "agreement"
d.mkdir(exist_ok=True)
k.to_csv(d / "key.csv", index=False)
init()
make_chips(k.assign(map_year=-1), d / "chips")
sheets(k, d)
