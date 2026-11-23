"""B step 1b: the per-fire model as a full Bayesian multilevel model (NumPyro, NUTS), as a check on b1's empirical Bayes.
Run 1 (pair level, argv 'pairs'): p_ij ~ StudentT(nu, f_i m_ij, sigma_ij), sigma from the static-site noise model x DE.
  On CPU it did not mix (12,000-fire subsample: tau stuck at its start value, ESS 6), so the check uses run 2.
Run 2 (default): f_hat_i ~ StudentT(nu, f_i, sqrt(DE_i s_i^2))  (f_hat_i, s_i^2 = b1's weighted fit of all the fire's pairs,
  DE_i = design effect for shared passes),  log f_i ~ Normal(-tau^2/2, tau) (mean factor 1), tau ~ HalfNormal(1),
  nu ~ Gamma(2, 0.1); 2 chains.
Fires with >= 2 pairs (a 1-pair fire carries no information on tau). Out: results/b1b_numpyro.json, scratch fires_post_nuts.parquet"""
import sys, os, json, pickle, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b1_hier import load, class_mean, per_fire, design_effect, nuisance
from b_lib import *
import jax, jax.numpy as jnp
import numpyro, numpyro.distributions as dist
from numpyro.infer import MCMC, NUTS
numpyro.set_host_device_count(1)
O, kap = load(); C = pickle.load(open(f'{SC}/class_model.pkl', 'rb'))
mu = class_mean(O, C['full']); m = mu * O.K.values; O['y'] = O.y - nuisance(O, C['full'])
fo = per_fire(O, mu); fp = per_fire(O, mu, col='yq'); DE, _ = design_effect(fo, fp)
fo['DE'] = DE
n = O.groupby('fire_mp').size(); keep = n[n >= 2].index
if 'ratapani' in sys.argv: keep = keep.intersection(O[O.fire_rt >= 0].fire_mp.unique())
if 'sub' in sys.argv:        # random 12,000 fires with >= 2 pairs (run time)
    keep = pd.Index(np.random.default_rng(0).choice(keep.values, 12000, replace=False))
sel = O.fire_mp.isin(keep).values
fi, fids = pd.factorize(O.fire_mp.values[sel])
sig = np.sqrt(O.sig2.values[sel] * fo.DE.reindex(O.fire_mp.values[sel]).values)
y = O.y.values[sel]; mm = m[sel]
def model(fi, mm, sig, y=None, nf=None):
    tau = numpyro.sample('tau', dist.HalfNormal(1.0)); nu = numpyro.sample('nu', dist.Gamma(2.0, 0.1))
    with numpyro.plate('fires', nf):
        z = numpyro.sample('z', dist.Normal(0, 1))
    logf = -tau ** 2 / 2 + tau * z
    numpyro.sample('y', dist.StudentT(nu + 1.0, jnp.exp(logf)[fi] * mm, sig), obs=y)
t0 = time.time()
if 'pairs' in sys.argv:
    mc = MCMC(NUTS(model, target_accept_prob=0.85), num_warmup=400, num_samples=400, num_chains=1, progress_bar=False)
    mc.run(jax.random.PRNGKey(0), fi=jnp.array(fi), mm=jnp.array(mm), sig=jnp.array(sig), y=jnp.array(y), nf=len(fids))
else:
    fs = fo.reindex(fids); fh = fs.f_hat.values; se = np.sqrt(fs.s2.values * fs.DE.values)
    fi = np.arange(len(fids)); mm = np.ones(len(fids)); sig = se; y = fh
    mc = MCMC(NUTS(model, target_accept_prob=0.9), num_warmup=600, num_samples=600, num_chains=2, chain_method='sequential', progress_bar=False)
    mc.run(jax.random.PRNGKey(1), fi=jnp.array(fi), mm=jnp.array(mm), sig=jnp.array(sig), y=jnp.array(y), nf=len(fids))
s = mc.get_samples(); tau = np.asarray(s['tau']); nu = np.asarray(s['nu']) + 1
logf = -tau[:, None] ** 2 / 2 + tau[:, None] * np.asarray(s['z']); f = np.exp(logf)
P = pd.DataFrame(dict(fire_mp=fids, f_mean=f.mean(0), f_lo=np.quantile(f, .05, 0), f_hi=np.quantile(f, .95, 0), f_sd=f.std(0))).set_index('fire_mp')
tag = ''.join(f'_{a}' for a in sys.argv[1:])
P.to_parquet(f'{SC}/fires_post_nuts{tag}.parquet')
ext = mc.get_extra_fields(); div = int(np.asarray(ext['diverging']).sum()) if 'diverging' in ext else None
res = dict(fires=len(fids), pairs=int(sel.sum()), seconds=round(time.time() - t0), tau_mean=round(float(tau.mean()), 3),
           tau_90=[round(float(np.quantile(tau, .05)), 3), round(float(np.quantile(tau, .95)), 3)],
           sd_of_factor_implied=round(float(np.sqrt(np.exp(tau.mean() ** 2) - 1)), 3), nu_mean=round(float(nu.mean()), 2),
           fires_90pct_interval_excludes_1=int(((P.f_lo > 1) | (P.f_hi < 1)).sum()),
           fires_clearly_fast=int((P.f_lo > 1).sum()), fires_clearly_slow=int((P.f_hi < 1).sum()),
           median_posterior_sd_of_factor=round(float(P.f_sd.median()), 3), divergences=div,
           r_hat_tau=None)
try:
    from numpyro.diagnostics import split_gelman_rubin, effective_sample_size
    st = np.asarray(mc.get_samples(group_by_chain=True)['tau'])
    res['ess_tau'] = round(float(effective_sample_size(st)), 1); res['r_hat_tau'] = round(float(split_gelman_rubin(st)), 3)
except Exception as e: res['ess_tau'] = str(e)
json.dump(res, open(f'{OUT}/b1b_numpyro{tag}.json', 'w'), indent=1); print(json.dumps(res, indent=1))
