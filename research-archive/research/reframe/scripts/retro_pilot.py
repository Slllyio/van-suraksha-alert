"""Retrospective dry run of Akkshay's pilot design (15 Oct): one sanctuary, one season, frozen model (trained on 2017-24 only),
season window 15 Feb-15 Jun. Rules compared at the SAME staff-hours as today's fixed 5 per beat per day.
Staff-hours per beat-day = nearest-neighbour tour from the beat centroid through the day's picks and back
(straight line x 1.4 detour, 15 km/h mixed vehicle + foot) + 0.5 h on site per check. Crews start in the beat they check.
Each burn cell-day is split by what was known at issue time: 'near active fire' = a VIIRS point within 1.5 km of the cell
in the last 3 days; 'new ignition' = none. Outputs per rule: hours, checks, share of each class found, checks with no burn."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, exp_budget as E
m = pd.read_parquet(D.OUT + 'pooled_full.parquet')
m = m[(m.season >= 2025) & (m.date.dt.strftime('%m%d') >= '0215') & (m.date.dt.strftime('%m%d') <= '0615')].reset_index(drop=True)
c = D.cells().set_index('cell_id'); X, Y = c.x.values, c.y.values
cen = c.groupby('beat_uid')[['x', 'y']].mean()
m['near'] = m.d3 <= 1500
SPEED, DET, SITE = 15.0, 1.4, 0.5

def hours(d, p):
    h = 0.0
    for (s, dt, b), g in d[p].groupby(['season', 'date', 'beat_uid']).cell_id:
        pts = list(zip(X[g.values], Y[g.values])); cur = tuple(cen.loc[b]); start = cur; km = 0.0
        while pts:
            k = int(np.argmin([(px - cur[0]) ** 2 + (py - cur[1]) ** 2 for px, py in pts])); nx = pts.pop(k)
            km += np.hypot(nx[0] - cur[0], nx[1] - cur[1]) / 1000; cur = nx
        km += np.hypot(start[0] - cur[0], start[1] - cur[1]) / 1000
        h += km * DET / SPEED + SITE * len(g)
    return h

def stats(d, p, H):
    pos = d.pos.values; nr = d.near.values; pp = p.values
    return dict(staff_hours=round(H), checks=int(pp.sum()), checks_per_day=round(pp.sum() / d.groupby(['season', 'date']).ngroups, 1),
                new_ignitions_found=round(float((pos & ~nr & pp).sum() / (pos & ~nr).sum()), 4),
                near_active_found=round(float((pos & nr & pp).sum() / (pos & nr).sum()), 4),
                all_found=round(float((pos & pp).sum() / pos.sum()), 4),
                checks_with_no_burn=round(float((~pos & pp).sum() / pp.sum()), 4),
                checks_near_active_fire=round(float((nr & pp).sum() / pp.sum()), 4))

res = {}
for season in (2025, 2026):
    d = m[m.season == season].reset_index(drop=True)
    d['rnd'] = np.random.default_rng(0).random(len(d))
    p0 = E.pick(d, 's', 'fixed5'); H0 = hours(d, p0); r = {'fixed5_lean (today)': stats(d, p0, H0)}
    pr = E.pick(d, 'rnd', 'fixed5'); r['fixed5_random'] = stats(d, pr, hours(d, pr))
    sc_f = E.scale_nopeek(d, 'mu_N2'); sc_c = E.scale_nopeek(d, 'mu_N2', clim=True)
    for name, col, sc in (('calendar_total_lean', 's', sc_c), ('calendar_total_ranker', 'p_avg', sc_c),
                          ('forecast_total_lean', 's', sc_f), ('forecast_total_ranker', 'p_avg', sc_f)):
        lo, hi = 0.2, 3.0
        for _ in range(9):                      # scale the season total until staff-hours match fixed5
            k = (lo + hi) / 2; H = hours(d, E.pick(d, col, 'day_varying', sc * k))
            lo, hi = (k, hi) if H < H0 else (lo, k)
        k = (lo + hi) / 2; p = E.pick(d, col, 'day_varying', sc * k); r[name] = dict(stats(d, p, hours(d, p)), budget_multiplier=round(k, 3))
        print(season, name, r[name], flush=True)
    r['positives'] = dict(new_ignition=int((d.pos & ~d.near).sum()), near_active=int((d.pos & d.near).sum()))
    res[season] = r; print(season, json.dumps(r, indent=0), flush=True)
res['assumptions'] = dict(speed_kmh=SPEED, detour=DET, hours_on_site=SITE, near_active='VIIRS (S-NPP, NOAA-20, NOAA-21) within 1.5 km in last 3 days',
                          model='frozen: trained 2017-24', window='15 Feb-15 Jun')
json.dump(res, open('/mnt/project-files/research/reframe/results/retro_pilot.json', 'w'), indent=1); print('DONE')
