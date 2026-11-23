"""Step 15. How fast the patch map goes stale: of the tr3 patches (3+ of 5 seasons 2017-21), how many still repeat in 2022-25,
and how much NEW repeat ground (3+ of the 4 seasons 2022-25, not in tr3) appeared. Per division and all MP.
Out: out/cb15_stale.csv"""
import os, sys, glob
import numpy as np, pandas as pd
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
rows = []
for key in B.KEYS:
    Z = np.load(B.SC26 + f'patches_{key}.npz'); ct = Z['cnt_tr']; ca = Z['cnt_all']; fb = Z['fb'].astype(bool); lab = Z['lab_tr3']
    cte = ca - ct                      # seasons burnt 2022-25 (of 4)
    tr3 = lab > 0; ha = 1.44           # 120 m cells
    new = (cte >= 3) & ~tr3 & fb
    labn, n = ndi.label(new, structure=np.ones((3, 3), bool))
    if n:
        area = ndi.sum(fb, labn, np.arange(1, n + 1)) * ha; keep = np.r_[False, area >= 10]; new = keep[labn]
    npat = int(lab.max()); still = 0; pha = 0.0; still_ha = 0.0
    if npat:
        pa = np.bincount(lab[fb & tr3], minlength=npat + 1) * ha
        bs = np.bincount(lab[fb & tr3], weights=cte[fb & tr3], minlength=npat + 1) / 4 / np.maximum(pa / ha, 1)   # mean seasons burnt per cell 2022-25 / 4
        still = int(((bs >= 0.5) & (pa > 0)).sum()); pha = float(pa[1:].sum()); still_ha = float(pa[1:][bs[1:] >= 0.5].sum())
    rows.append(dict(key=key, tr3_patches=npat, tr3_ha=pha, tr3_patches_still_repeat=still, tr3_ha_still_repeat=still_ha,
                     tr3_ha_burnt_share_2022_25=float(cte[fb & tr3].mean() / 4) if tr3.any() else np.nan,
                     tr3_ha_burnt_share_2017_21=float(ct[fb & tr3].mean() / 5) if tr3.any() else np.nan,
                     new_repeat_ha=float(new[fb].sum() * ha), forest_ha=float(fb.sum() * ha)))
    print(key, flush=True)
S = pd.DataFrame(rows); S.to_csv(B.OUT + 'cb15_stale.csv', index=False)
t = S[['tr3_patches', 'tr3_ha', 'tr3_patches_still_repeat', 'tr3_ha_still_repeat', 'new_repeat_ha', 'forest_ha']].sum()
print(t); print('share of tr3 ha still repeat (burnt >= 2 of 4 seasons 2022-25, patch mean):', round(t.tr3_ha_still_repeat / t.tr3_ha, 3))
print('tr3 burnt share per season 2017-21 vs 2022-25 (ha-weighted):', round((S.tr3_ha_burnt_share_2017_21 * S.tr3_ha).sum() / S.tr3_ha.sum(), 3), round((S.tr3_ha_burnt_share_2022_25 * S.tr3_ha).sum() / S.tr3_ha.sum(), 3))
print('new repeat ground 2022-25 outside tr3:', round(t.new_repeat_ha), 'ha =', round(100 * t.new_repeat_ha / t.tr3_ha, 1), '% of tr3 area')
