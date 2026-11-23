import pandas as pd, numpy as np, lightgbm as lgb
from scipy.stats import spearmanr
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r12_area_code/'
S=pd.read_csv('/mnt/project-files/fire-alert-scars/out/event_scars_split.csv', usecols=['event_id','scar_ha','scar_ha_split'])
F=pd.read_parquet(D+'features_750.parquet'); F=F[(F.month<=6)&~F.grew_large].merge(S[['event_id','scar_ha_split']],on='event_id')
F=F[F.scar_ha_split>0]
print('n',len(F),'median split',F.scar_ha_split.median())
for c in ['d0_n','d0_fp_union_ha','d0_frp_sum','all_n']:
    print(c,'spearman grown',round(spearmanr(F[c],F.scar_ha)[0],3),'split',round(spearmanr(F[c],F.scar_ha_split)[0],3))
y=np.log(F.scar_ha_split.values); cols=[c for c in F.columns if c.startswith('d0_')]+['month']; X=F[cols].values
p=np.full(len(F),np.nan)
for s in sorted(F.year.unique()):
    te=(F.year==s).values
    p[te]=lgb.LGBMRegressor(n_estimators=300,learning_rate=0.03,num_leaves=15,min_child_samples=40,verbose=-1).fit(X[~te],y[~te]).predict(X[te])
lr=(p-y)/np.log(2); print('LOYO d0 LightGBM on split target: spearman %.3f within x2 %.3f'%(spearmanr(p,y)[0],np.mean(np.abs(lr)<=1)))
cls=pd.cut(F.scar_ha_split,[0,10,30,100,300,1e9],right=False)
print(pd.DataFrame({'c':cls,'ok':np.abs(lr)<=1,'r':lr}).groupby('c',observed=True).agg(n=('ok','size'),x2=('ok','mean'),ratio=('r',lambda s:2**s.median())).round(2))
