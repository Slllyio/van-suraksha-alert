"""Per-division fire timing from burn scars 2022-25 (15 Feb-31 May): day of season by which 25/50/75% of scar ha has burnt, peak week,
and how stable that is between years. Out: results/t1_division_timing.csv, t1_summary.json"""
import json, numpy as np, pandas as pd
R = '/mnt/project-files/research/fire-timing/results/'
E = pd.read_parquet('/mnt/project-files/research/ceiling/scar_key/scar_events.parquet'); E = E[E.status == 'scar'].copy()
E['ld'] = pd.to_datetime(E.ld); E['Y'] = E.ld.dt.year; E['doy'] = (E.ld - pd.to_datetime(E.Y.astype(str) + '-02-15')).dt.days
E = E[(E.doy >= 0) & (E.doy <= 105)]
def q(g, p):
    g = g.sort_values('doy'); c = g.scar_ha.cumsum() / g.scar_ha.sum(); return float(g.doy.values[np.searchsorted(c.values, p)])
rows = []
for d, g in E.groupby('Division'):
    if len(g) < 100: continue
    r = dict(Division=d, fires=len(g), ha=round(g.scar_ha.sum()), d25=q(g, .25), d50=q(g, .5), d75=q(g, .75))
    w = g.groupby(g.doy // 7).scar_ha.sum(); r['peak_week'] = int(w.idxmax())
    yr = {Y: q(h, .5) for Y, h in g.groupby('Y') if len(h) >= 20}; r.update({f'd50_{Y}': v for Y, v in yr.items()})
    r['late_share'] = round(float(g.scar_ha[g.doy >= 60].sum() / g.scar_ha.sum()), 3)  # after 15 Apr
    rows.append(r)
T = pd.DataFrame(rows).sort_values('d50')
dt = lambda x: (pd.Timestamp('2025-02-15') + pd.Timedelta(days=x)).strftime('%d %b')
T['half_burnt_by'] = T.d50.map(dt); T['quarter_by'] = T.d25.map(dt); T['three_q_by'] = T.d75.map(dt)
T.to_csv(R + 't1_division_timing.csv', index=False)
Ys = [c for c in T if c.startswith('d50_')]; C = T[Ys].corr(method='spearman').values; off = C[~np.eye(len(Ys), dtype=bool)]
ev = T[['d50_2022', 'd50_2024']].mean(1); od = T[['d50_2023', 'd50_2025']].mean(1)
S = dict(divisions=len(T), statewide_half_by=dt(q(E, .5)), earliest=T.head(8)[['Division', 'half_burnt_by', 'late_share']].values.tolist(),
         latest=T.tail(8)[['Division', 'half_burnt_by', 'late_share']].values.tolist(), spread_days_p10_p90=[float(T.d50.quantile(.1)), float(T.d50.quantile(.9))],
         year_pair_spearman_mean=round(float(np.nanmean(off)), 2), even_vs_odd_spearman=round(float(ev.corr(od, method='spearman')), 2),
         year_shift_statewide={int(Y): dt(q(E[E.Y == Y], .5)) for Y in sorted(E.Y.unique())})
json.dump(S, open(R + 't1_summary.json', 'w'), indent=1); print(json.dumps(S, indent=1))
