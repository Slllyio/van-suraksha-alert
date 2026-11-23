"""Do later updates help most where fires come later? For the 10 test regions: share of burnt ha after 15 Apr (own labels, 2022-25) and
half-burnt date of the main division, against (1) PC 5-frame March gain, (2) cloud in-season dryness gain (dynamic-cutoff Part C), by region."""
import json, numpy as np, pandas as pd
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'; R = '/mnt/project-files/research/fire-timing/results/'
L = pd.read_parquet(f'{SP}/mp/labels_phase.parquet'); L = L[~L.early]
s = L.groupby(['region', 'season', 'phase']).share.sum().unstack('phase'); s = s.div(s.sum(1), axis=0)
late = s.groupby('region').P3.mean(); late_sd = s.groupby('region').P3.std(); early = s.groupby('region').P1.mean()
T = pd.read_csv(R + 't1_division_timing.csv').set_index('Division')
main = {'Khandwa': 'Khandwa', 'Dewas': 'Dewas', 'South_Betul': 'South_Betul', 'South_Chhindwara': 'South_Chhindwara', 'South_Balaghat': 'South_Balaghat',
        'Dindori': 'Dindori', 'Umaria': 'Umaria', 'Chhatarpur': 'Chhatarpur', 'Panna_TR': 'Panna_TR', 'Satpura_TR': 'Satpura_TR'}
V = '/home/user/vanagni/prithvi_finetune/'
pre = json.load(open(V + 'out_mid_pre/results.json'))['frozen']; a5 = json.load(open(V + 'out_mid_all5/results.json'))['frozen']
C = json.load(open('/mnt/project-files/research/dynamic-cutoff/results/c_dryness.json'))
D = pd.DataFrame({'late_share': late.round(3), 'late_share_sd': late_sd.round(3), 'early_share': early.round(3),
                  'half_burnt_by': [T.loc[main[r], 'half_burnt_by'] for r in late.index], 'd50': [T.loc[main[r], 'd50'] for r in late.index],
                  'march_gain_after15Mar': [round(a5['by_region'][r] - pre['by_region'][r], 3) for r in late.index],
                  'march_gain_late': [round(a5['late_by_region'][r] - pre['late_by_region'][r], 3) for r in late.index],
                  'dryness_gain_all': [C['gain_by_region'][r] for r in late.index], 'dryness_gain_late': [C['gain_by_region_late'][r] for r in late.index]}).sort_values('d50')
D.to_csv(R + 't2_gain_vs_timing.csv')
rho = {c: round(float(D[c].corr(D.late_share, method='spearman')), 2) for c in ['march_gain_after15Mar', 'march_gain_late', 'dryness_gain_all', 'dryness_gain_late']}
rho_d50 = {c: round(float(D[c].corr(D.d50, method='spearman')), 2) for c in rho}
# null: shuffle regions
rng = np.random.default_rng(0); null = {c: float(np.mean([abs(pd.Series(rng.permutation(D[c].values)).corr(pd.Series(D.late_share.values), method='spearman')) >= abs(rho[c]) for _ in range(5000)])) for c in rho}
out = dict(spearman_vs_late_share=rho, spearman_vs_half_burnt_date=rho_d50, perm_p_vs_late_share=null)
json.dump(out, open(R + 't2_summary.json', 'w'), indent=1); print(D.to_string()); print(json.dumps(out, indent=1))
