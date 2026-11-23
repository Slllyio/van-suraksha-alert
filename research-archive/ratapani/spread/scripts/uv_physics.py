"""C-DAC-style physics (Rothermel/level-set, ERA5 weather, roads; sim.run_event as in gap_analysis.py) on the unseen fires, issued at
every VIIRS look from the dots so far (restart at each look, as C-DAC plans), scored against the same truth and next to the same rules
as uv_apply.py. Forecast area = whatever physics burns by +24 h; also cut to the 24 ha rule's area (physics used for placement only).
  FC_SCRATCH=/tmp/claude-0/fronts python3 uv_physics.py prefix chunk nchunks
"""
import os, sys, pickle, warnings, numpy as np, pandas as pd
warnings.filterwarnings('ignore')
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C
import sim, footprint as fp
from scipy.spatial import cKDTree
PRE, CH, NCH = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); X0, Y0 = 737300.0, 2560500.0; MED = 24.1
I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
CFG = dict(fp.CFG, ign_snap=False, hours=30); WX = {}
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
fires = sorted(I.fire.unique())[CH::NCH]; rows = []
for n, fire in enumerate(fires):
    g = I[I.fire == fire]; s = int(g.season.iloc[0])
    if s not in WX:
        WX.clear(); WX[s] = sim.load_weather(s)
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min()
    for it in g.itertuples():
        kn = d[d.lk <= it.k]; tk = kn.t.max(); xy = kn[['x', 'y']].values
        truth = dom & (Tg <= it.th + 24); dd = cKDTree(xy).query(P)[0]; foot = dd <= 265
        try:
            ev = pd.DataFrame(dict(x=kn.x.values, y=kn.y.values, t=pd.to_datetime(kn.t.values), season=s, overpass=tk))
            o = sim.run_event(ev, WX[s], dict(CFG, ign_all=True, win=(r0, r1, c0, c1)), hours=30)
            T = (o['T'] / 60.0 - (tk - ev.t.min().floor('h')).total_seconds() / 3600).ravel()   # hours after the issue
        except Exception as e:
            rows.append(dict(fire=fire, k=it.k, err=str(e)[:80])); continue
        phys = foot | (np.isfinite(T) & (T <= 24))
        n24 = int(foot.sum() + MED * it.n_active / .04)
        sc = np.where(foot, -1, np.where(np.isfinite(T), T, 1e9)); pc = np.zeros(len(sc), bool); pc[np.argsort(sc, kind='stable')[:n24]] = True
        sd = np.where(foot, -1, dd); rule = np.zeros(len(sd), bool); rule[np.argsort(sd, kind='stable')[:n24]] = True
        rows.append(dict(fire=fire, season=s, k=it.k, truth_ha=truth.sum() * .04, phys_ha=phys.sum() * .04, rule_ha=n24 * .04,
                         sor_phys=so(phys, truth), sor_phys_rule_area=so(pc, truth), sor_rule=so(rule, truth), sor_foot=so(foot, truth)))
    if n % 25 == 0:
        print(CH, n, len(fires), flush=True)
pd.DataFrame(rows).to_csv(f'{PRE}_physics_{CH}.csv', index=False); print('done', CH, flush=True)
