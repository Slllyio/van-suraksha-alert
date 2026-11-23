# Check app/runway.py's live feature extraction against the research table (research/runway-statewide, r2_rays.py) on a sample of
# statewide first-look fronts: same open side? The accuracy itself is the research's held-out number (the app model was trained on
# all fronts, so scoring it on them would be in-sample).   RW_SCRATCH=<research scratch> python scripts/runway_check.py [N]
import os, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from app import runway
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
S = os.environ['RW_SCRATCH']; F = pd.read_parquet(f'{S}/F.parquet'); E = pickle.load(open(f'{S}/events.pkl', 'rb'))
O = {o['origin']: o for e in E for o in e['origins']}
ids = F[F.kind == 'first'].origin.drop_duplicates().sample(N, random_state=2)
cols = runway._model()['cols']; agree, near, cor = [], [], []
for oid in ids:
    g = F[F.origin == oid].sort_values('ray')
    if len(g) < 36: continue
    o = O[oid]
    X, rows, ok1, ok2 = runway.features(dict(x=o['x'], y=o['y'], hot_b=o['hot_b'], hot_m=o['hot_m'], ax=o['ax'], el=o['el'], mom=np.nan))
    pa, pr = runway.predict(X), runway.predict(g[cols].astype(float).values)
    sa = np.array([pa[runway.SEC == k].mean() for k in range(8)]); sr = np.array([pr[runway.SEC == k].mean() for k in range(8)])
    a, b = int(np.argmax(sa)), int(np.argmax(sr))
    agree.append(a == b); near.append(min((a - b) % 8, (b - a) % 8) <= 1)
    cor.append(np.corrcoef(X[:, cols.index('local_height_0_300')], g['local_height_0_300'])[0, 1])
print(f'fronts {len(agree)}: same open side {np.mean(agree):.0%}, within one side {np.mean(near):.0%}; local height corr median {np.median(cor):.2f}')
