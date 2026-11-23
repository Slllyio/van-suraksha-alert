"""What one pilot season can show (amended protocol, 15 Oct): ignition stream only. Cells with a VIIRS point within 1.5 km in the
last 3 days are removed from every arm's ignition list (they belong to the response stream). Each arm runs its own rule inside its
own beats (pilot/beat_arms.csv); calendar and forecast arms share checks across their own beats only. Every arm gets the staff-hours
of 5 checks per beat per day on its beats (same hours model as retro_pilot.py). Endpoint: burns with no nearby recent VIIRS found
per 100 staff-hours, satellite stand-in for 'verified fires with no nearby recent VIIRS detection'. 95% intervals: bootstrap over
beats within each arm (2,000 draws)."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, exp_budget as E
m = pd.read_parquet(D.OUT + 'pooled_full.parquet')
m = m[(m.season >= 2025) & (m.date.dt.strftime('%m%d') >= '0215') & (m.date.dt.strftime('%m%d') <= '0615')].reset_index(drop=True)
m = m[m.d3 > 1500].reset_index(drop=True)                     # ignition stream only
c = D.cells().set_index('cell_id'); X, Y = c.x.values, c.y.values; cen = c.groupby('beat_uid')[['x', 'y']].mean()
arm = pd.read_csv('/mnt/project-files/research/reframe/pilot/beat_arms.csv').set_index('beat_uid').arm
m['arm'] = m.beat_uid.map(arm)
SPEED, DET, SITE = 15.0, 1.4, 0.5

def beat_hours(d, p):
    out = {}
    for (s, dt, b), g in d[p].groupby(['season', 'date', 'beat_uid']).cell_id:
        pts = list(zip(X[g.values], Y[g.values])); cur = tuple(cen.loc[b]); start = cur; km = 0.0
        while pts:
            k = int(np.argmin([(px - cur[0]) ** 2 + (py - cur[1]) ** 2 for px, py in pts])); nx = pts.pop(k)
            km += np.hypot(nx[0] - cur[0], nx[1] - cur[1]) / 1000; cur = nx
        km += np.hypot(start[0] - cur[0], start[1] - cur[1]) / 1000
        out[b] = out.get(b, 0) + km * DET / SPEED + SITE * len(g)
    return pd.Series(out)

res = {}; rng = np.random.default_rng(0)
for season in (2025, 2026):
    per_beat = {}
    for a, rule in (('fixed', None), ('calendar', True), ('forecast', False)):
        d = m[(m.season == season) & (m.arm == a)].reset_index(drop=True); nb = d.beat_uid.nunique()
        H0 = beat_hours(d, E.pick(d, 's', 'fixed5')).sum()
        if rule is None: p = E.pick(d, 's', 'fixed5')
        else:
            sc = E.scale_nopeek(d, 'mu_N2', clim=rule) * nb / 94; lo, hi = 0.2, 3.0
            for _ in range(9):
                k = (lo + hi) / 2; H = beat_hours(d, E.pick(d, 's', 'day_varying', sc * k)).sum(); lo, hi = (k, hi) if H < H0 else (lo, k)
            p = E.pick(d, 's', 'day_varying', sc * (lo + hi) / 2)
        hb = beat_hours(d, p); fb = d[p & d.pos].groupby('beat_uid').size(); tot = d[d.pos].groupby('beat_uid').size()
        t = pd.DataFrame({'hours': hb, 'found': fb, 'total': tot}).fillna(0); per_beat[a] = t
        print(season, a, round(t.hours.sum()), int(t.found.sum()), int(t.total.sum()), flush=True)
    r = {}
    for a, t in per_beat.items():
        r[a] = dict(staff_hours=round(t.hours.sum()), burns_found=int(t.found.sum()), burns_in_arm=int(t.total.sum()),
                    share_found=round(t.found.sum() / t.total.sum(), 3), per_100_staff_hours=round(100 * t.found.sum() / t.hours.sum(), 3))
    boots = {a: [] for a in per_beat}
    for _ in range(2000):
        for a, t in per_beat.items():
            s_ = t.iloc[rng.integers(0, len(t), len(t))]; boots[a].append(100 * s_.found.sum() / s_.hours.sum())
    for a in ('calendar', 'forecast'):
        ratio = np.array(boots[a]) / np.array(boots['fixed'])
        r[f'{a}_vs_fixed_rate_ratio'] = dict(point=round(r[a]['per_100_staff_hours'] / r['fixed']['per_100_staff_hours'], 3),
                                             ci95=[round(float(x), 3) for x in np.percentile(ratio, [2.5, 97.5])])
    ratio = np.array(boots['forecast']) / np.array(boots['calendar'])
    r['forecast_vs_calendar_rate_ratio'] = dict(point=round(r['forecast']['per_100_staff_hours'] / r['calendar']['per_100_staff_hours'], 3),
                                                ci95=[round(float(x), 3) for x in np.percentile(ratio, [2.5, 97.5])])
    res[season] = r; print(season, json.dumps(r), flush=True)
json.dump(res, open('/mnt/project-files/research/reframe/results/pilot_power.json', 'w'), indent=1); print('DONE')
