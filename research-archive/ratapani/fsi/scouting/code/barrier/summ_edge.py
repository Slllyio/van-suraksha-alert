import sys, numpy as np, pandas as pd
from scipy.stats import binomtest
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
df=pd.read_parquet(D+f'edge_test_{sys.argv[1] if len(sys.argv)>1 else "main"}.parquet')
print('scars',len(df),'median perimeter pts',df.n.median(),'gap_frac mean',df.gap_frac.mean().round(3),'inforest_frac mean',df.inforest_frac.mean().round(3))
lays=sorted({c.rsplit('_',1)[0] for c in df.columns if c.endswith('_R30o')})
rng=np.random.default_rng(0)
rows=[]
for k in lays:
    for s in ['R30','R60','S30','RF','A30']:
        o,n=f'{k}_{s}o',f'{k}_{s}n'
        if o not in df: continue
        d=df[[o,n,'n']].dropna(); d=d[d[n]>0]
        if len(d)<10: continue
        w=d['n']; pooled=(d[o]*w).sum()/(d[n]*w).sum()
        bs=[]
        for _ in range(500):
            ii=rng.integers(0,len(d),len(d)); dd=d.iloc[ii]; bs.append((dd[o]*dd['n']).sum()/(dd[n]*dd['n']).sum())
        k1=(d[o]>d[n]).sum(); k0=(d[o]<d[n]).sum()
        p=binomtest(int(k1),int(k1+k0)).pvalue if k1+k0>0 else np.nan
        pit=df.loc[d.index,f'{k}_R30pit'].mean() if (s=='R30' and f'{k}_R30pit' in df) else np.nan
        rows.append(dict(layer=k,metric=s,mean_pit=round(pit,3),scars=len(d),obs=round((d[o]*w).sum()/w.sum(),4),null=round((d[n]*w).sum()/w.sum(),4),pooled_ratio=round(pooled,2),ci=f'{np.percentile(bs,2.5):.2f}-{np.percentile(bs,97.5):.2f}',above=int(k1),below=int(k0),p_sign=f'{p:.1e}'))
out=pd.DataFrame(rows); print(out.to_string(index=False)); out.to_csv(D+f'edge_summary_{sys.argv[1] if len(sys.argv)>1 else "main"}.csv',index=False)
