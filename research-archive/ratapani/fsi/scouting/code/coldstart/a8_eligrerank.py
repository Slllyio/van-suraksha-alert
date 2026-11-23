import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/'
m=pd.read_parquet(W+'merged.parquet')
cs=pd.read_csv('/mnt/project-files/research/ratapani-ignition/cells_static.csv').set_index('cell_id')
m['elig']=cs.elig_ha.reindex(m.cell_id).values
g=[m.season,m.date,m.beat]
nval=m.groupby(g).cell_id.transform('size'); r=m.pipeline_lean.groupby(g).rank('first',ascending=False); top=r<=5
low=m.elig<=10
print('low-elig picks in beat-days with >5 valid candidates: %.3f of all picks'%((top&low&(nval>5)).sum()/top.sum()))
# among those beat-days, were there unpicked candidates with elig>10?
unp_hi=(~top)&(~low); bd=m[unp_hi].groupby(g).size()
key=pd.MultiIndex.from_arrays(g); has_alt=pd.Series(key.isin(bd.index),index=m.index)
print('low-elig picks where a >10 ha candidate was left unpicked: %.3f of all picks'%((top&low&has_alt).sum()/top.sum()))
def rec(col,lab='pos_main',d=m):
    s=d[col]; rr=s.groupby([d.season,d.date,d.beat]).rank('first',ascending=False); h=(rr<=5)&d[lab]
    return 100*h.sum()/d[lab].sum(), (100*h.groupby(d.season).sum()/d[lab].groupby(d.season).sum()).round(1).tolist()
print('lean', rec('pipeline_lean')); print('ens',rec('lean_ensemble'))
for a in (0.25,0.5,1.0,2.0):
    m['x']=m.pipeline_lean*np.clip(m.elig/15,0.02,1)**a; m['xe']=m.lean_ensemble.rank(pct=True)*0+m.lean_ensemble*np.clip(m.elig/15,0.02,1)**a
    print('a=%.2f lean*f %s'%(a,rec('x')), ' strict %s'%(rec('x','pos',m[m.valid_strict])[0]), 'vs lean strict %.2f'%rec('pipeline_lean','pos',m[m.valid_strict])[0])
