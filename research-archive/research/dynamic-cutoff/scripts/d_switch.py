# D: choose per region x phase which inputs to use (Prithvi on/off, in-season dryness on/off), picked on other seasons only.
import pandas as pd, numpy as np, json
R = '/mnt/project-files/research/dynamic-cutoff/results/'
b = pd.read_csv(R + 'b_by_region_phase.csv'); c = pd.read_csv(R + 'c_by_region_phase.csv')
V = {'full': b[b.model == 'division+phase cut-off'], 'no Prithvi': b[b.model == 'division+phase cut-off, no Prithvi'],
     'no dryness update': c[c.model == 'pre-season only']}
K = ['region', 'season', 'phase']
D = None
for k, d in V.items():
    d = d[K + ['ha_burnt', 'ha_caught']].rename(columns={'ha_caught': k})
    D = d if D is None else D.merge(d[K + [k]], on=K)
names = list(V)
def pick(train, by):
    w = train.ha_burnt
    s = train.groupby(by).apply(lambda g: pd.Series({n: (g[n] * g.ha_burnt).sum() / g.ha_burnt.sum() for n in names}))
    return s.idxmax(axis=1)
out = {}; rows = []
for by in (['region', 'phase'], ['region'], ['phase']):
    got = []
    for s in sorted(D.season.unique()):
        ch = pick(D[D.season != s], by).rename('choice').reset_index()
        t = D[D.season == s].merge(ch, on=by, how='left').fillna({'choice': 'full'})
        t['switch'] = [r[r.choice] for _, r in t.iterrows()]; got.append(t)
    G = pd.concat(got)
    out['switch by ' + '+'.join(by)] = round(float(G.switch.mean()), 4)
    if by == ['region', 'phase']:
        rows = G
for n in names: out[n] = round(float(D[n].mean()), 4)
out['oracle (best per region x phase x season)'] = round(float(D[names].max(axis=1).mean()), 4)
gain = rows.assign(g=rows.switch - rows.full)
out['switch_vs_full_by_season'] = gain.groupby('season').g.mean().round(4).to_dict()
out['switch_vs_full_by_region'] = gain.groupby('region').g.mean().round(4).to_dict()
out['choice_counts'] = rows.choice.value_counts().to_dict()
bs = [gain.groupby('region').g.mean().sample(frac=1, replace=True, random_state=i).mean() for i in range(2000)]
out['switch_vs_full_CI90'] = [round(float(np.percentile(bs, 5)), 4), round(float(np.percentile(bs, 95)), 4)]
json.dump(out, open(R + 'd_switch.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
