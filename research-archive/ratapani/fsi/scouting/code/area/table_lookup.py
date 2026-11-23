import numpy as np, pandas as pd
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r12_area_code/'
F=pd.read_parquet(D+'features_750.parquet'); F=F[(F.month<=6)&~F.grew_large]
for x in ['d0_n','d0_fp_union_ha','d0_frp_sum','all_n']:
    b=np.polyfit(np.log(F[x]),np.log(F.scar_ha),1); r=np.log(F.scar_ha)-np.polyval(b,np.log(F[x]))
    print(x,'scar_ha = %.1f * x^%.2f, resid sd (log) %.2f -> factor %.2f'%(np.exp(b[1]),b[0],r.std(),np.exp(r.std())))
F['nb']=pd.cut(F.d0_n,[0,1,2,4,8,16,1000])
q=lambda p: (lambda s: np.percentile(s,p))
print(F.groupby('nb',observed=True).scar_ha.agg(n='size',p10=q(10),p50=q(50),p90=q(90),share_ge100=lambda s:(s>=100).mean()).round(2).to_string())
F['fb']=pd.qcut(F.d0_frp_sum,5)
print(F.groupby('fb',observed=True).scar_ha.agg(n='size',p10=q(10),p50=q(50),p90=q(90)).round(1).to_string())
# post (first image) target
for x in ['d0_n','all_n']:
    b=np.polyfit(np.log(F[x]),np.log(F.scar_ha_post),1); print('post',x,np.exp(b[1]).round(1),b[0].round(2))
# fraction of fires whose day-0 detections are at final count
print('share of fires with all detections on day 0:', (F.d0_n==F.all_n).mean().round(3))
