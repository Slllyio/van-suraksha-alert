"""Part A: how big is a 'normal' burn by division and by part of the season? Scar sizes, 15 Feb-31 May 2022-25, all MP (scar thread events with a scar).
Out: results/a_division.csv, a_division_phase.csv, a_summary.json"""
import json, numpy as np, pandas as pd
from scipy.stats import spearmanr
R = '/mnt/project-files/research/dynamic-cutoff/results/'
E = pd.read_parquet('/mnt/project-files/research/ceiling/scar_key/scar_events.parquet')
E = E[(E.status == 'scar') & (E.scar_ha > 0)].copy(); E['yr'] = E.ld.dt.year
doy = E.ld.dt.month * 100 + E.ld.dt.day
E['phase'] = np.select([doy <= 315, doy <= 415, doy <= 515], ['1 15Feb-15Mar', '2 16Mar-15Apr', '3 16Apr-15May'], '4 16May-31May')
E['lha'] = np.log(E.scar_ha)
def stats(g): return pd.Series(dict(n=len(g), median_ha=g.scar_ha.median(), p75_ha=g.scar_ha.quantile(.75), p90_ha=g.scar_ha.quantile(.9),
    ge4=(g.scar_ha >= 4).mean(), ge7_5=(g.scar_ha >= 7.5).mean(), ge25=(g.scar_ha >= 25).mean(), ha_total=g.scar_ha.sum()))
D = E.groupby('Division').apply(stats); D = D[D.n >= 50].sort_values('median_ha'); D.round(3).to_csv(R + 'a_division.csv')
P = E.groupby('phase').apply(stats); DP = E[E.Division.isin(D.index)].groupby(['Division', 'phase']).apply(stats); DP.round(3).to_csv(R + 'a_division_phase.csv')
# stability: division median in even vs odd years; phase pattern per division in even vs odd years
ev, od = E[E.yr % 2 == 0], E[E.yr % 2 == 1]
m = pd.concat([ev.groupby('Division').scar_ha.median(), od.groupby('Division').scar_ha.median()], axis=1).loc[D.index].dropna()
dpe = ev[ev.Division.isin(D.index)].groupby(['Division', 'phase']).scar_ha.median(); dpo = od[od.Division.isin(D.index)].groupby(['Division', 'phase']).scar_ha.median()
rel_e = (dpe / dpe.groupby(level=0).transform('median')).rename('e'); rel_o = (dpo / dpo.groupby(level=0).transform('median')).rename('o'); rr = pd.concat([rel_e, rel_o], axis=1).dropna()
# variance of log size explained
tot = E.lha.var()
def r2(keys): return 1 - (E.lha - E.groupby(keys).lha.transform('mean')).var() / tot
yr_by_div = E[E.Division.isin(D.index)].groupby(['Division', 'yr']).scar_ha.median().unstack()
S = dict(events=int(len(E)), divisions=int(len(D)), by_phase=P.round(3).to_dict('index'),
    division_median_ha_range=[round(float(D.median_ha.min()), 1), round(float(D.median_ha.max()), 1)],
    stability_division_median_even_vs_odd=round(float(spearmanr(m.iloc[:, 0], m.iloc[:, 1])[0]), 3),
    stability_phase_shape_within_division=round(float(spearmanr(rr.e, rr.o)[0]), 3),
    r2_log_size=dict(division=round(float(r2('Division')), 3), phase=round(float(r2('phase')), 3), division_x_phase=round(float(r2(['Division', 'phase'])), 3), year=round(float(r2('yr')), 3), division_x_year=round(float(r2(['Division', 'yr'])), 3)),
    year_median_by_division_spread=yr_by_div.std(1).median().round(2).item())
# phases where size grows: share of divisions whose late (phase 3) median > early (phase 1) median
w = DP.median_ha.unstack()
S['divisions_late_bigger_than_early'] = [int((w['3 16Apr-15May'] > w['1 15Feb-15Mar']).sum()), int(w[['1 15Feb-15Mar', '3 16Apr-15May']].dropna().shape[0])]
json.dump(S, open(R + 'a_summary.json', 'w'), indent=1); print(json.dumps(S, indent=1))
print(D[['n', 'median_ha', 'p75_ha', 'ge4', 'ge7_5', 'ge25']].round(2).to_string())
print(w.round(1).to_string())
