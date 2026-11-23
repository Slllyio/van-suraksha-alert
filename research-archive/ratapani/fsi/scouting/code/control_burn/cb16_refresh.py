"""Step 16. How often must the patch map be rebuilt? Per cell, which seasons 2017-25 it burnt (scar outlines, 60 m, forest).
Candidate repeat sets, all tested on 2024-25: burnt 3+ of 2017-21 (the tr3 rule, five seasons old), 3+ of 2019-23 (fresh five),
2+ of 2021-23 (fresh three), 2 of 2022-23 (fresh two), 1 of 2023 (last season only). For each: forest ha selected and the share
burnt per season in 2024-25, plus the share of 2024-25 burnt forest that falls on the set. Out: out/cb16_refresh.csv"""
import os, sys
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
YRS = list(range(2017, 2026)); yi = {y: i for i, y in enumerate(YRS)}
RULES = {'3+ of 2017-21 (tr3, five seasons old)': (2017, 2021, 3), '3+ of 2018-22': (2018, 2022, 3), '3+ of 2019-23 (fresh five)': (2019, 2023, 3),
         '2+ of 2021-23 (fresh three)': (2021, 2023, 2), '2 of 2022-23 (fresh two)': (2022, 2023, 2), '1 of 2023 (last season)': (2023, 2023, 1), '2+ of 2017-23 (any seven)': (2017, 2023, 2), '4+ of 2017-23': (2017, 2023, 4)}
acc = {r: [0.0, 0.0, 0.0] for r in RULES}; tot = [0.0, 0.0]
for key in B.KEYS:
    L, FOR = B.load_div(key); H, W = L['H'], L['W']
    burnt = np.zeros((len(YRS), H, W), bool)
    for f in L['fires']:
        if f['year'] not in yi: continue
        h, w = f['shape']; Mm = np.unpackbits(f['M'])[:h * w].astype(bool).reshape(h, w)
        burnt[yi[f['year']], f['r0']:f['r0'] + h, f['c0']:f['c0'] + w] |= Mm
    b24 = burnt[yi[2024]] & FOR; b25 = burnt[yi[2025]] & FOR; tot[0] += b24.sum(); tot[1] += b25.sum()
    for r, (y0, y1, k) in RULES.items():
        sel = (burnt[yi[y0]:yi[y1] + 1].sum(0) >= k) & FOR
        acc[r][0] += sel.sum(); acc[r][1] += (sel & b24).sum(); acc[r][2] += (sel & b25).sum()
    print(key, flush=True)
rows = []
for r, (n, a, b) in acc.items():
    rows.append(dict(rule=r, forest_ha=n * B.CELL_HA, burnt_share_2024=a / max(n, 1), burnt_share_2025=b / max(n, 1), share_of_2024_25_burnt_forest_on_set=(a + b) / (tot[0] + tot[1]),
                     burnt_ha_per_100ha_selected=100 * (a + b) / 2 / max(n, 1)))
R = pd.DataFrame(rows); R.to_csv(B.OUT + 'cb16_refresh.csv', index=False); print(R.round(3).to_string(index=False)); print('burnt forest ha 2024, 2025:', tot[0] * B.CELL_HA, tot[1] * B.CELL_HA)
