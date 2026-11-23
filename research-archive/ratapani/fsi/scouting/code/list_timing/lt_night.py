"""List timing (round 23): night vs day passes.
1. Fires (strict events, 10 divisions) first seen on the night (~01:30) vs day (~13:30) pass, by brand-new / not.
2. Detection mix by pass: share, FRP, low-confidence share (type 0, 15 Feb-31 May, 10 divisions' squares).
3. Is the night pass under-detecting? Persistence test on 500 m squares: a square detected on the day pass of t and
   again on the day pass of t+1 has very likely burned (or smouldered) through the night; how often does the night pass
   of t+1 in between see it (in the square or next to it)? And the reverse (night t and night t+1 -> day t+1 between).
   Also split by the FRP of the bracketing detections.
4. MODIS: share of fires whose first VIIRS detection was preceded within 12 h by a MODIS point within 1 km (Terra 10:30 /
   22:00, Aqua 13:30 / 01:30), i.e. how often an earlier MODIS look could have started the clock sooner.
Out: out/night_*.csv (small)."""
import sys, os
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/list_timing')
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
import lt_score as L
C = L.C
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/list_timing/out/'; os.makedirs(OUT, exist_ok=True)


def fires_by_pass():
    rows = []
    for per in ('held', 'fwd'):
        ET = L.event_times(per); ev = pd.concat([v['ev'] for v in ET.values()]); ev = ev[ev.common]
        for nm, m in (('all', ev.new | ~ev.new), ('brand-new', ev.new), ('other', ~ev.new)):
            e = ev[m]; rows.append(dict(period=per, fires=nm, n=len(e), night_first=int((e.dn == 'N').sum()), night_pct=100 * (e.dn == 'N').mean(),
                                        frp_first_med_night=e.frp[e.dn == 'N'].median(), frp_first_med_day=e.frp[e.dn == 'D'].median()))
        by = ev.groupby('season').apply(lambda e: pd.Series(dict(n=len(e), night_pct=100 * (e.dn == 'N').mean()))).reset_index(); by['period'] = per
        rows += [dict(period=per, fires=f'season {int(r.season)}', n=int(r.n), night_pct=r.night_pct) for r in by.itertuples()]
    T = pd.DataFrame(rows); T.round(2).to_csv(OUT + 'night_fires_by_pass.csv', index=False); print(T.round(1).to_string())


def det_mix():
    import features as Fe
    U = Fe.base()['U']
    v = C.load_det(range(2019, 2027)); v = v[v.type == 0]
    md = v.ld.dt.month * 100 + v.ld.dt.day; v = v[(md >= 215) & (md <= 531)]
    v = v[np.isin(v.row.values * C.W + v.col.values, U)]
    g = v.groupby('daynight').agg(n=('frp', 'size'), frp_med=('frp', 'median'), frp_p90=('frp', lambda x: x.quantile(.9)), low=('confidence', lambda x: 100 * (x == 'l').mean()))
    g['share'] = 100 * g.n / g.n.sum(); g.round(2).to_csv(OUT + 'night_det_mix.csv'); print(g.round(2))
    return v


def persistence(v):
    """slot index: 2*day + (0 night, 1 day); a square's set of slots with detections (3x3 neighbourhood for the middle)."""
    v = v[v.season >= 2019]
    dn0 = (v.ld - pd.Timestamp('2000-01-01')).dt.days.values; sl = 2 * dn0 + (v.daynight.values == 'D')
    cell = v.row.values.astype(np.int64) * C.W + v.col.values
    d = pd.DataFrame(dict(cell=cell, sl=sl, frp=v.frp.values)).groupby(['cell', 'sl']).frp.max().reset_index()
    key = set(zip(d.cell.values, d.sl.values))
    nb = [dr * C.W + dc for dr in (-1, 0, 1) for dc in (-1, 0, 1)]
    keyn = set((c + o, s) for c, s in key for o in nb)
    rows = []
    for kind, a_par in (('day->day, night between', 1), ('night->night, day between', 0)):
        a = d[d.sl % 2 == a_par]
        b = a.merge(a, on='cell', suffixes=('', '_2')); b = b[b.sl_2 == b.sl + 2]
        mid = b.sl + 1
        hit_sq = np.array([(c, s) in key for c, s in zip(b.cell.values, mid.values)])
        hit_nb = np.array([(c, s) in keyn for c, s in zip(b.cell.values, mid.values)])
        fmin = np.minimum(b.frp.values, b.frp_2.values)
        for lab, m in (('all', np.ones(len(b), bool)), ('both FRP < 5 MW', fmin < 5), ('both FRP 5-15 MW', (fmin >= 5) & (fmin < 15)), ('both FRP >= 15 MW', fmin >= 15)):
            rows.append(dict(test=kind, frp=lab, n=int(m.sum()), seen_in_square=100 * hit_sq[m].mean(), seen_in_3x3=100 * hit_nb[m].mean()))
    T = pd.DataFrame(rows); T.round(2).to_csv(OUT + 'night_persistence.csv', index=False); print(T.round(1).to_string())


def modis_first():
    rows = []
    for per in ('held', 'fwd'):
        te = C.PERIODS[per][1]
        m = pd.concat([pd.read_csv(C.P + f'fire-alert-scars/alerts_mp/modis_{y}.csv') for y in te])
        m = m[m.type == 0]
        x, y_ = C.TF.transform(m.longitude.values, m.latitude.values)
        m['ist'] = pd.to_datetime(m.acq_date) + pd.to_timedelta(m.acq_time // 100, 'h') + pd.to_timedelta(m.acq_time % 100, 'm') + pd.Timedelta(hours=5, minutes=30)
        tm = (m.ist - pd.Timestamp('2000-01-01')) / pd.Timedelta('1h')
        tree = cKDTree(np.c_[x, y_]); tmv = tm.values; satv = m.satellite.values; hrv = m.ist.dt.hour.values
        ET = L.event_times(per)
        for name, et in ET.items():
            d = C.grids()[name]
            ev = et['ev']; ev = ev[ev.common]; cells = et['cells'][et['cells'].lab.isin(ev.lab)]
            R = L.E.prep(per)[name]
            cx = C.X0 + (R['cols'][cells.cell.values] + 0.5) * C.S; cy = C.Y1 - (R['rows'][cells.cell.values] + 0.5) * C.S
            tf = ((cells.tf - pd.Timestamp('2000-01-01')) / pd.Timedelta('1h')).values
            nn = tree.query_ball_point(np.c_[cx, cy], r=1000)
            pre = np.zeros(len(cells), bool); which = np.full(len(cells), '', object)
            for i, js in enumerate(nn):
                if not js: continue
                js = np.array(js); dt = tf[i] - tmv[js]; ok = (dt > 0) & (dt <= 12)
                if ok.any():
                    pre[i] = True; j = js[ok][np.argmax(dt[ok])]; which[i] = f'{satv[j]} {"day" if 6 <= hrv[j] < 18 else "night"}'
            q = pd.DataFrame(dict(lab=cells.lab.values, pre=pre, which=which)).sort_values('pre', ascending=False).groupby('lab').first()
            e = ev.set_index('lab').join(q); e['period'] = per; rows.append(e.reset_index()[['period', 'division', 'lab', 'dn', 'new', 'pre', 'which']])
    T = pd.concat(rows)
    s = T.groupby(['period', 'dn']).agg(n=('pre', 'size'), modis_before_pct=('pre', lambda x: 100 * x.mean())).reset_index()
    w = T[T.pre].groupby(['period', 'which']).size().rename('n').reset_index()
    s.round(2).to_csv(OUT + 'night_modis_before.csv', index=False); w.to_csv(OUT + 'night_modis_before_which.csv', index=False)
    print(s.round(1).to_string()); print(w.to_string())


if __name__ == '__main__':
    fires_by_pass(); v = det_mix(); persistence(v); modis_first()
