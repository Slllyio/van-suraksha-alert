"""Power check: if fuel map v3 were the true fuel, how strongly SHOULD heat per hectare follow it, given the noise we
measured? Per fire: log(heat t/ha) = log(map fuel) + noise. Noise is taken from the data itself. Two estimates:
 (a) all of the observed spread minus the map's spread is noise (most generous to the map),
 (b) the noise implied by the two-satellite repeatability (S-NPP vs NOAA-20, rho ~0.5).
Expected rank correlation is simulated; observed is from h4. Same for the place-memory test (h9).
Out: results/power.json"""
import json, numpy as np, pandas as pd
from scipy.stats import spearmanr
from h0_lib import RES
R = pd.read_csv(f'{RES}/fire_fuel.csv')[['fire', 'n_pass', 'fuel_tha']].merge(pd.read_csv(f'{RES}/fire_cov.csv'), on='fire')
D = R[(R.n_pass >= 2) & R.month.between(2, 6)].dropna(subset=['litter', 'grass'])
lm = np.log(D.litter + D.grass); lf = np.log(D.fuel_tha)
out = {'n': len(D), 'sd_log_map': round(lm.std(), 3), 'sd_log_heat': round(lf.std(), 3), 'observed_rho': round(spearmanr(lm, lf)[0], 3)}
rng = np.random.default_rng(0)
def sim(noise_sd, share_true=1.0):
    r = []
    for _ in range(200):
        truth = share_true * (lm - lm.mean()) + np.sqrt(1 - share_true ** 2) * lm.std() * rng.standard_normal(len(lm))
        r.append(spearmanr(lm, truth + noise_sd * rng.standard_normal(len(lm)))[0])
    return round(float(np.mean(r)), 3), [round(float(x), 3) for x in np.percentile(r, [2.5, 97.5])]
noise_a = np.sqrt(max(lf.var() - lm.var(), 1e-6))
noise_b = lf.std() * np.sqrt(1 - 0.5)       # repeatability 0.5 -> half the variance is noise
for lab, nz in [('noise = all extra spread', noise_a), ('noise from 2-satellite repeatability', noise_b)]:
    out[f'expected_rho_map_fully_right ({lab})'] = sim(nz, 1.0)
    out[f'expected_rho_map_half_right ({lab})'] = sim(nz, 0.5)
print(json.dumps(out, indent=1)); json.dump(out, open(f'{RES}/power.json', 'w'), indent=1)
