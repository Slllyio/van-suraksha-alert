"""Step 5. Final working list: re-choose lines per division with the same method ('plan' greedy) on ALL usable seasons
(2017-25 for tiger reserves and Ratapani; the >=95%-complete seasons for the rest of MP). The held-out test (f3/f4) says how far
to trust it: the in-sample hectares here are inflated about 10-15 times relative to what the test seasons showed.
Out: out/top_fire_lines.geojson - for each division the first ~50 km of final lines (chosen_on='all seasons'), plus the lines
chosen on 2017-21 only and scored on 2022-25 (chosen_on='2017-21 (tested)')."""
import pickle, glob
import numpy as np, pandas as pd, geopandas as gpd
import common as C, f3_select as S
from f4_report import chain_line


def main():
    feats = []
    T = pd.read_csv(C.OUT + 'division_table.csv'); T20 = T[T.budget_km == 20].set_index('key')
    for p in sorted(glob.glob(C.SC + 'sel_*.pkl')):
        R = pickle.load(open(p, 'rb')); key = R['key']
        L = pickle.load(open(C.SC + f'fires_{key}.pkl', 'rb')); cand = pickle.load(open(C.SC + f'cand_{key}.pkl', 'rb'))
        tab = cand['tab']; km = tab.km.values; kind = tab.kind.values
        yrs_ok = R['tr_years'] + R['te_years']; ny = len(yrs_ok)
        yrs = np.array([f['year'] for f in L['fires']])
        F = S.Fires(L, np.nonzero(np.isin(yrs, yrs_ok))[0])
        pool = [k for k in range(len(tab)) if kind[k] in S.POOL]
        P = F.protect(cand, np.array(pool, np.int64), 1)
        sel = S.greedy(F, P, pool, km, cand)
        held = T20.loc[key, 'plan'] if key in T20.index else np.nan
        t = 0.0
        for rank, (k, g) in enumerate(sel, 1):
            t += km[k]
            if t > 55: break
            v = F.value(P, [k])
            seasons = int(len({int(F.year[f]) for f, c in P.get(k, []) if c.size >= 3}))
            cl = cand['cells'][cand['ptr'][k]:cand['ptr'][k + 1]]
            feats.append(dict(division=R['div'], data='complete (TR/Ratapani)' if key in C.CORE else 'rest-of-MP history (partial seasons)',
                              chosen_on='all seasons ' + f'{yrs_ok[0]}-{yrs_ok[-1]}', rank=rank, kind=kind[k], km=round(km[k], 2), cum_km=round(t, 1),
                              hist_ha_saved_per_yr=round(v.sum() / ny, 1), seasons_cut=seasons,
                              heldout_div_ha_per_km_yr=round(float(held), 2), geometry=chain_line(cl, L)))
        # tested lines (chosen on training seasons only)
        t = 0.0
        for rank, k in enumerate(R['sel']['plan'], 1):
            ln = R['lines'][k]; t += ln['km']
            if t > 22: break
            feats.append(dict(division=R['div'], data='complete (TR/Ratapani)' if key in C.CORE else 'rest-of-MP history (partial seasons)',
                              chosen_on=f"{R['tr_years'][0]}-{R['tr_years'][-1]} (tested)", rank=rank, kind=ln['kind'], km=round(ln['km'], 2), cum_km=round(t, 1),
                              hist_ha_saved_per_yr=round(R['train_line_ha'][k] / len(R['tr_years']), 1),
                              test_ha_saved_per_yr=round(R['test_line_ha'][k] / len(R['te_years']), 1),
                              test_seasons_with_gain=int(sum(v > 0.5 for v in R['test_line_years'].get(k, {}).values())),
                              heldout_div_ha_per_km_yr=round(float(held), 2), geometry=chain_line(ln['cells'], R['grid'])))
        print(key, len(sel), flush=True)
    G = gpd.GeoDataFrame(feats, geometry='geometry', crs=4326)
    G.to_file(C.OUT + 'top_fire_lines.geojson', driver='GeoJSON')
    print(len(G), G.groupby('chosen_on').size().to_dict())


if __name__ == '__main__':
    main()
