"""Division-level: change in early (1 Jan-14 Feb) share 2014-22 -> 2023-26 vs change in Mar-May share of MP points (S-NPP)."""
import pandas as pd, numpy as np
from scipy.stats import spearmanr
d=pd.read_parquet('pts.parquet'); s=d[d.sat=='snpp'].copy()
s['post']=s.season>=2023
mp=s[s.mam].groupby('post').size()
g=s.groupby(['Division','post']).agg(n=('early','size'),early=('early','sum'),mam=('mam','sum')).unstack()
out=pd.DataFrame({'early_pre':g['early'][False]/g['n'][False],'early_post':g['early'][True]/g['n'][True],
  'mam_pre_per1000':g['mam'][False]/mp[False]*1000,'mam_post_per1000':g['mam'][True]/mp[True]*1000,'mam_pre_n':g['mam'][False],'mam_post_n':g['mam'][True]})
out['d_early']=out.early_post-out.early_pre
out['lr_mam']=np.log((out.mam_post_per1000+0.05)/(out.mam_pre_per1000+0.05))
o=out[(out.mam_pre_n>=200)]
print('divisions',len(o)); print('spearman d_early vs log-ratio MarMay',spearmanr(o.d_early,o.lr_mam))
o=o.sort_values('d_early',ascending=False); print(o.round(3).head(15).to_string())
print('median lr all',o.lr_mam.median(),'rank Satpura',(o.lr_mam<o.loc['Satpura_TR','lr_mam']).sum(),'of',len(o))
out.round(4).to_csv('division_did.csv')
