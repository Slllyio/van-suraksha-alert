"""Spread audit: recompute the spread thread's headline numbers from its saved per-fire / per-step result files and add
95% confidence intervals bootstrapped by FIRE EVENT (all steps / detections of a fire resampled together).
Reads /mnt/project-files/ratapani/spread/results (read only). Writes ../results/boot_headlines.json."""
import pandas as pd, numpy as np, glob, json
R = '/mnt/project-files/ratapani/spread/results'
OUT = '/mnt/project-files/research/spread-audit/results/boot_headlines.json'
B = 2000; rng = np.random.default_rng(0)


def load(pat):
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f'{R}/{pat}'))], ignore_index=True)


def boot_ratio(df, num_a, num_b, den):
    """pooled rate a = sum(num_a)/sum(den), b likewise; CI for a, b and a - b by resampling fires"""
    g = df.groupby('event')[[num_a, num_b, den]].sum()
    A, Bv, D = g[num_a].values, g[num_b].values, g[den].values
    n = len(g); idx = rng.integers(0, n, (B, n))
    ra = A[idx].sum(1) / D[idx].sum(1); rb = Bv[idx].sum(1) / D[idx].sum(1)
    pt = lambda x: round(100 * float(x), 1)
    ci = lambda x: [pt(np.percentile(x, 2.5)), pt(np.percentile(x, 97.5))]
    return dict(fires=n, n=int(D.sum()), a=pt(A.sum() / D.sum()), b=pt(Bv.sum() / D.sum()), diff=pt((A.sum() - Bv.sum()) / D.sum()),
                a_ci=ci(ra), b_ci=ci(rb), diff_ci=ci(ra - rb))


def boot_mean(df, a, b):
    """per-fire score means (one row per fire); CI for each mean and the paired difference"""
    d = df[[a, b, 'event']].dropna()
    A, Bv = d[a].values, d[b].values; n = len(d); idx = rng.integers(0, n, (B, n))
    ci = lambda x: [round(float(np.percentile(x, 2.5)), 3), round(float(np.percentile(x, 97.5)), 3)]
    return dict(fires=n, a=round(float(A.mean()), 3), b=round(float(Bv.mean()), 3), diff=round(float((A - Bv).mean()), 3),
                a_ci=ci(A[idx].mean(1)), b_ci=ci(Bv[idx].mean(1)), diff_ci=ci((A - Bv)[idx].mean(1)), a_better_share=round(float((A > Bv).mean()), 3))


out = {}
# 1. learned restart, next-pass head (README 4j: 86.3 vs 72.4 at the persistence area; raster-label run lr_*, polygon run lrg_*)
for tag, pat in [('restart_lr', 'lr_score_[0-3].parquet'), ('restart_lrg', 'lrg_score_[0-3].parquet')]:
    d = load(pat); st = d[d.lead_h.notna()].copy()
    st['band'] = pd.cut(st.lead_h, [0, 3, 9, 18, 72], labels=['<3h', '3-9h', '9-18h', '>18h'])
    r = dict(steps=len(st), median_lead_h=round(float(st.lead_h.median()), 1), median_area_pers_ha=round(float(st.area_pers.median() * .04), 1),
             all=boot_ratio(st, 'hit_learn', 'hit_pers', 'n_target'), new_ground=boot_ratio(st, 'hitnew_learn', 'hitnew_pers', 'n_new'),
             half_area_learn_vs_dist=boot_ratio(st, 'hit_learn_h', 'hit_dist_h', 'n_target'),
             own_area_learn_vs_dist=boot_ratio(st, 'hit_learn_e', 'hit_dist_e', 'n_target'))
    r['by_lead'] = {str(b): dict(steps=len(g), **boot_ratio(g, 'hit_learn', 'hit_pers', 'n_target')) for b, g in st.groupby('band', observed=True)}
    r['leads_3h_plus'] = boot_ratio(st[st.lead_h >= 3], 'hit_learn', 'hit_pers', 'n_target')
    end = d[d.lead_h.isna() & d.scar_px.ge(25)]
    r['end_footprint'] = dict(learn_vs_dist=boot_mean(end, 'sor_learn_end', 'sor_dist_end'), learn_vs_pers=boot_mean(end, 'sor_learn_end', 'sor_pers_end'),
                              median_scar_ha=float(end.scar_px.median() * .04))
    out[tag] = r
# 2. learned footprint on the grown outlines (README 4k: 0.517 vs 0.463 circle, 0.454 physics; later passes 55 vs 38 vs 41%)
f = load('foot_score_grown2_[0-3].parquet')
out['footprint_grown'] = dict(learn_vs_circle=boot_mean(f, 'sor_learn', 'sor_circle'), learn_vs_phys=boot_mean(f, 'sor_learn', 'sor_phys'),
                              phys_vs_circle=boot_mean(f, 'sor_phys', 'sor_circle'), own_area_learn_vs_circle=boot_mean(f, 'sor_learn_free', 'sor_circle_free'),
                              later_hits_learn_vs_circle=boot_ratio(f[f.n_later.notna()], 'hit_learn', 'hit_circle', 'n_later'),
                              later_hits_learn_vs_phys=boot_ratio(f[f.n_later.notna()], 'hit_learn', 'hit_phys', 'n_later'),
                              median_scar_ha=float(f.scar_px.median() * .04), median_pred_ha=float(f.n_pred.median() * .04))
f0 = load('foot_score_[0-3].parquet')
out['footprint_raster'] = dict(learn_vs_circle=boot_mean(f0, 'sor_learn', 'sor_circle'), phys_vs_circle=boot_mean(f0, 'sor_phys', 'sor_circle'))
# 3. physics final model (README 4b: 0.348 vs 0.345, better in 52%; scar >= 1 ha)
p = pd.read_parquet(f'{R}/res_loose_lfi_m2.parquet'); p = p[p.sor_model.notna()]
out['physics_final'] = dict(phys_vs_circle=boot_mean(p, 'sor_model', 'sor_iso'),
                            later_hits=boot_ratio(p[p.n_later.notna()], 'hit_model', 'hit_iso', 'n_later'))
json.dump(out, open(OUT, 'w'), indent=1)
print(json.dumps(out, indent=1))
