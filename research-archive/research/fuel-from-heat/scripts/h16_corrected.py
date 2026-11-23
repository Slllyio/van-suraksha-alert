"""FRP fuel load, re-analysed with what we learnt (Akkshay 17 Oct 08:02Z).

CORRECTED PROBLEM STATEMENT
  Fuel burnt per hectare = 0.368 kg/MJ x (fire radiative ENERGY over the whole fire) / (ground it burnt).
  - Energy per area, not FRP per pixel: FRP in one pixel = fuel per area x speed x front length, so grass (fast
    spread, little fuel) can look as "hot" as litter. Only total energy / total burnt area cancels the speed.
    (This is why the within-pass "relative heat" of the second method followed grass: it measured intensity.)
  - The satellite's view of that energy is biased in four measured ways, corrected here:
    1. viewing angle: summed FRP of a fire falls with slant path, more under trees (same-fire 2-satellite pairs, h13b):
       log-slope per unit (sec - 1) = -0.30 open ground, about -0.57 closed forest -> slope(c) = -0.30 - 0.42 x canopy.
       Each detection is scaled back to its straight-down equivalent.
    2. leafy crowns hide fires and heat: keep the comparison to LEAF-OFF fires (>= 80% leaves fallen), where crowns
       are bare and no detection loss was found.
    3. night: the MODIS-count clock says night burning is 13% of afternoon; FRP itself says 24%. Clock refitted so
       01:30 / 13:30 IST = 0.24 (base 0.184 instead of 0.084).
    4. swath-edge overlap / missed weak pixels: CLEAN set = fires whose energy comes >= 70% from passes within 30 deg
       of straight down (sec <= 1.15).
  Then: does corrected heat per hectare follow canopy / the fuel map? Expected if the map were right (power) vs seen.
Out: results/corrected_fire_fuel.csv, results/corrected_tests.json, figures/corrected_fuel.png
"""
import json
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from h0_lib import RES, BF, HERE, K_FRE, _p

BASE = 0.184
def r2(t):
    t = pd.to_datetime(pd.Series(np.atleast_1d(t)))
    ist = (t.dt.hour + t.dt.minute / 60 + 5.5).values % 24
    f = lambda h: BASE + (1 - BASE) * np.exp(-((h - _p['peak_ist'] + 12) % 24 - 12) ** 2 / (2 * _p['width_h'] ** 2))
    return f(ist) / f(np.arange(0, 24, 1 / 60)).mean()
def hours2(t0, t1):
    if t1 <= t0: return 0.0
    n = max(int((t1 - t0).total_seconds() / 120), 1); ts = pd.date_range(t0, t1, periods=n + 1)
    return float(np.trapezoid(r2(ts), dx=(t1 - t0).total_seconds() / 3600 / n))

G = pd.read_csv(f'{RES}/det_geom.csv', parse_dates=['t']).dropna(subset=['fire', 'canopy01'])
G['fire'] = G.fire.astype(int)
G['slope'] = -0.30 - 0.42 * G.canopy01
G['frp_c'] = G.frp * np.exp(-G.slope * (G.sec - 1))          # straight-down equivalent
P = G.groupby(['fire', 'sensor', 't']).agg(frp=('frp', 'sum'), frp_c=('frp_c', 'sum'), sec=('sec', 'mean'), fallen=('fallen', 'mean'),
                                           leafy=('leafy', 'mean')).reset_index().sort_values(['fire', 't'])
P['r_old'] = __import__('h0_lib').r_clock(P.t); P['r_new'] = r2(P.t)
area = pd.read_csv(f'{BF}/fires.csv').set_index('fire').area_ha
def energy(g, col, rcol, hfun, lead=6, tail=6, cap=12):
    t = list(g.t); E = 0.0; Enad = 0.0
    for i in range(len(g)):
        a = lead if i == 0 else min(hfun(t[i - 1], t[i]) / 2, cap)
        b = tail if i == len(g) - 1 else min(hfun(t[i], t[i + 1]) / 2, cap)
        e = g[col].iloc[i] / g[rcol].iloc[i] * (a + b); E += e
        if g.sec.iloc[i] <= 1.15: Enad += e
    return E, Enad
from h0_lib import clock_hours
rows = []
for fire, g in P.groupby('fire'):
    if len(g) < 2: continue
    k = 10 * K_FRE * 3600 / (area[fire] * 1e4)
    e0, _ = energy(g, 'frp', 'r_old', clock_hours)
    e1, en = energy(g, 'frp_c', 'r_new', hours2)
    rows.append(dict(fire=fire, n_pass=len(g), fuel_raw=e0 * k, fuel_corr=e1 * k, nadir_share=en / e1 if e1 > 0 else np.nan,
                     fallen=np.nanmean(g.fallen), leafy=np.nanmean(g.leafy), sec_mean=g.sec.mean()))
R = pd.DataFrame(rows).merge(pd.read_csv(f'{RES}/fire_cov.csv'), on='fire')
R = R[R.month.between(2, 6)].dropna(subset=['canopy', 'litter', 'grass'])
R['mapfuel'] = R.litter + R.grass
R.to_csv(f'{RES}/corrected_fire_fuel.csv', index=False)
R['clean'] = (R.nadir_share >= .7) & (R.fallen >= .8)
out = {'fires': len(R), 'clean_fires': int(R.clean.sum()),
       'median_tha': {'raw': round(R.fuel_raw.median(), 2), 'corrected': round(R.fuel_corr.median(), 2),
                      'corrected_clean': round(R[R.clean].fuel_corr.median(), 2)}}
print(out)
# what the correction did, by canopy
cb = pd.cut(R.canopy, [0, 20, 40, 60, 100])
t = R.groupby(cb, observed=True).agg(fires=('fire', 'size'), raw=('fuel_raw', 'median'), corrected=('fuel_corr', 'median'),
                                     map_fuel=('mapfuel', 'median'))
t['corrected_clean'] = R[R.clean].groupby(cb[R.clean], observed=True).fuel_corr.median()
t['clean_fires'] = R[R.clean].groupby(cb[R.clean], observed=True).size()
print(t.round(2)); out['by_canopy'] = t.round(3).reset_index().astype(str).to_dict('records')
# tests
def tests(D, tag):
    o = {'n': len(D)}
    for c in ['canopy', 'litter', 'mapfuel', 'grass', 'teak', 'burnt_last_season', 'doy', 'n_pix']:
        ok = D[[c, 'fuel_corr']].dropna(); o[f'rho_{c}'] = round(spearmanr(ok[c], ok.fuel_corr)[0], 3)
    # partial: within scar-size fifths and month
    D = D.copy(); D['sz'] = pd.qcut(np.log(D.scar_ha if 'scar_ha' in D else D.n_pix), 5, labels=False)
    w = [spearmanr(g.mapfuel, g.fuel_corr)[0] for _, g in D.groupby(['sz', 'month']) if len(g) >= 15]
    o['rho_mapfuel_within_size_and_month'] = round(float(np.nanmean(w)), 3) if w else None
    # power: expected rho if map were the truth, noise = extra spread (generous) and 2-sat repeatability
    lm, lf = np.log(D.mapfuel), np.log(D.fuel_corr); rng = np.random.default_rng(0)
    for lab, nz in [('generous', np.sqrt(max(lf.var() - lm.var(), 1e-6))), ('sat', lf.std() * np.sqrt(.5))]:
        r = [spearmanr(lm, lm + nz * rng.standard_normal(len(lm)))[0] for _ in range(200)]
        o[f'expected_if_map_right_{lab}'] = [round(float(np.mean(r)), 3), [round(float(x), 3) for x in np.percentile(r, [2.5, 97.5])]]
    obs = spearmanr(lm, lf)[0]
    # bootstrap of observed
    b = [spearmanr(*D[['mapfuel', 'fuel_corr']].sample(frac=1, replace=True, random_state=i).values.T)[0] for i in range(300)]
    o['observed_mapfuel'] = [round(obs, 3), [round(float(x), 3) for x in np.percentile(b, [2.5, 97.5])]]
    print(tag, o); return o
out['all'] = tests(R, 'ALL'); out['clean'] = tests(R[R.clean], 'CLEAN')
# held-out model: does ground add to corrected fuel, seasons held out (clean set and all)
for tag, D in [('all', R), ('clean', R[R.clean])]:
    D = D.dropna(subset=['tmax', 'rh', 'burnt_last_season']).copy(); D['lf'] = np.log(D.fuel_corr); D['la'] = np.log(D.n_pix)
    base = ['la', 'doy', 'tmax', 'rh', 'n_pass']; ground = ['canopy', 'litter', 'grass', 'teak', 'slope', 'burnt_last_season']
    def cv(feats, DD):
        pred = np.zeros(len(DD))
        for s in DD.season.unique():
            tr, te = DD.season != s, DD.season == s
            if tr.sum() < 20: continue
            pred[te.values] = LinearRegression().fit(DD.loc[tr, feats], DD.loc[tr, 'lf']).predict(DD.loc[te, feats])
        return round(float(1 - ((DD.lf - pred) ** 2).sum() / ((DD.lf - DD.lf.mean()) ** 2).sum()), 3)
    rng = np.random.default_rng(1); D2 = D.copy(); D2[ground] = D2[ground].values[rng.permutation(len(D2))]
    out[f'heldout_{tag}'] = {'n': len(D), 'size+season+weather': cv(base, D), '+ground': cv(base + ground, D), '+ground shuffled': cv(base + ground, D2)}
    print(tag, out[f'heldout_{tag}'])
json.dump(out, open(f'{RES}/corrected_tests.json', 'w'), indent=1, default=float)

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(12, 4.3))
x = np.arange(len(t)); w = .2
for i, (c, col, lab) in enumerate([('raw', 'lightcoral', 'heat, raw'), ('corrected', 'tab:red', 'heat, corrected'),
                                   ('corrected_clean', 'darkred', 'heat, corrected, clean fires'), ('map_fuel', 'tab:green', 'fuel map v3')]):
    ax[0].bar(x + (i - 1.5) * w, t[c], w, color=col, label=lab)
ax[0].set_xticks(x, ['0-20', '20-40', '40-60', '60+']); ax[0].set_xlabel('canopy cover under the scar (%)'); ax[0].set_ylabel('t/ha')
ax[0].legend(fontsize=8); ax[0].set_title('Fuel burnt per hectare from heat, after the corrections', fontsize=10)
ks = [('observed_mapfuel', 'OBSERVED'), ('expected_if_map_right_generous', 'if map right\n(generous)'), ('expected_if_map_right_sat', 'if map right\n(sat. noise)')]
for j, (tag, off) in enumerate([('all', -.2), ('clean', .2)]):
    vals = [out[tag][k][0] for k, _ in ks]; err = [[out[tag][k][0] - out[tag][k][1][0] for k, _ in ks], [out[tag][k][1][1] - out[tag][k][0] for k, _ in ks]]
    ax[1].bar(np.arange(3) + off, vals, .4, yerr=err, capsize=3, label=f"{tag} fires (n={out[tag]['n']})", color=['tab:blue', 'tab:orange'][j])
ax[1].axhline(0, color='k', lw=.8); ax[1].set_xticks(range(3), [l for _, l in ks], fontsize=8); ax[1].legend(fontsize=8)
ax[1].set_ylabel('rank corr: corrected heat per ha vs fuel map'); ax[1].set_title('Does corrected heat follow the fuel map?', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/corrected_fuel.png', dpi=110)
