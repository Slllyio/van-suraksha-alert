"""Is January too early? Ratapani is the one division with January scar outlines (scar method run all season). For each season
2017-25: ground classes by first burn date (Jan 1-31, Feb 1-14, Feb 15-28, Mar 1-15) and ground not yet burnt. For every VIIRS
point (all sats, day+night) from 16 Mar to 15 Jun, the class of its cell as of 14 days before the point (so a burn counts only
once it is two weeks old), against the expected share from the forest ha of each class in the same 5 km square (indirect
standardisation, as cb2). Ratio < 1 = the old burn still protects. Out: out/january_hold.csv"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'); import cb0 as B
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
CL = [('Jan 1-31', 1, 31), ('Feb 1-14', 32, 45), ('Feb 15-28', 46, 59), ('Mar 1-15', 60, 74)]
rows = []
for key in ('Obedullahganj',):
    L, FOR = B.load_div(key); H, W = L['H'], L['W']; sq = (np.arange(H)[:, None] // B.SQ) * 1000 + (np.arange(W)[None, :] // B.SQ)
    for y in B.YEARS:
        D = B.burn_day(L, y); p = B.points(key, y); p = p[(p.doy >= 75) & (p.doy <= 166)]
        if not len(p): continue
        pr, pc = B.rc(L, p.latitude.values, p.longitude.values); ok = (pr >= 0) & (pr < H) & (pc >= 0) & (pc < W); pr, pc, pd_ = pr[ok], pc[ok], p.doy.values[ok]
        ok2 = FOR[pr, pc]; pr, pc, pd_ = pr[ok2], pc[ok2], pd_[ok2]
        for name, a, b in CL:
            burnt = (D >= a) & (D <= b) & FOR
            for s in np.unique(sq[FOR]):
                m = (sq == s) & FOR; nb = (burnt & m).sum()
                if nb == 0: continue
                pts = (sq[pr, pc] == s); n = pts.sum()
                if n == 0: continue
                # points on ground burnt in the class at least 14 days before the point; the rest on ground unburnt as of the point
                dpt = D[pr[pts], pc[pts]]; old = (dpt >= a) & (dpt <= b) & (dpt <= pd_[pts] - 14)
                unb = dpt > pd_[pts] - 14   # not yet burnt (or burnt within 14 days) at the point date
                obs = old.sum(); n_ref = unb.sum(); ref_ha = (m & (D >= 60)).sum()   # ground not burnt before March as the reference pool
                rows.append(dict(key=key, season=y, cls=name, square=s, burnt_cells=nb, ref_cells=ref_ha, pts_on_old=obs, pts_on_ref=n_ref))
R = pd.DataFrame(rows)
out = []
for name, _, _ in CL:
    d = R[R.cls == name]; rate_old = d.pts_on_old.sum() / d.burnt_cells.sum(); rate_ref = d.pts_on_ref.sum() / d.ref_cells.sum()
    # per season too
    by = d.groupby('season').apply(lambda g: (g.pts_on_old.sum() / max(g.burnt_cells.sum(), 1)) / max(g.pts_on_ref.sum() / max(g.ref_cells.sum(), 1), 1e-9)).round(2).to_dict()
    bs = []; rng = np.random.default_rng(0); sqs = d.square.unique()
    for _ in range(300):
        pick = rng.choice(sqs, len(sqs)); g = pd.concat([d[d.square == q] for q in pick]); bs.append((g.pts_on_old.sum() / g.burnt_cells.sum()) / (g.pts_on_ref.sum() / g.ref_cells.sum()))
    out.append(dict(burn_window=name, burnt_ha=d.groupby(['season']).burnt_cells.sum().sum() * B.CELL_HA, points_on_burnt=d.pts_on_old.sum(), ratio_vs_unburnt=rate_old / rate_ref, ci_lo=np.percentile(bs, 2.5), ci_hi=np.percentile(bs, 97.5), by_season=by))
O = pd.DataFrame(out); O.to_csv(OUT + 'january_hold.csv', index=False); print(O.drop(columns='by_season').round(3).to_string(index=False)); print(O[['burn_window', 'by_season']].to_string(index=False))
