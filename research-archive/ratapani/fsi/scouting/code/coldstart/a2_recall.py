import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv')
B=(b[b.burned==1].groupby(['season','cell_id']).burned_ha.sum().unstack(0).reindex(range(3614)).fillna(0)>0).astype(int)
def nprior(Y): return B[[s for s in B.columns if s<Y]].sum(axis=1)
def ysl(Y):  # years since last burn, 99 if none
    out=np.full(3614,99)
    for s in range(2017,Y):
        out[B[s].values==1]=Y-s
    return pd.Series(out)
TL=pd.read_parquet('/mnt/project-files/ratapani/fsi/true_lead_labels_v2.parquet'); print(TL.season.value_counts().sort_index().to_dict())
P=pd.read_parquet('/mnt/project-files/ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet')
E=pd.read_parquet('/mnt/project-files/research/ratapani-ignition/results/lean_ensemble_pred.parquet'); print(E.columns.tolist(), E.season.unique())
real=pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid
m=TL.merge(P,on=['season','date','cell_id'],how='left').merge(E[['season','date','cell_id','lean_ensemble']],on=['season','date','cell_id'],how='left')
m['beat']=m.cell_id.map(real); m=m[m.beat.notna()]
m['np']=0; m['ysl']=99
for Y in m.season.unique():
    k=m.season==Y; m.loc[k,'np']=nprior(Y).values[m.cell_id[k]]; m.loc[k,'ysl']=ysl(Y).values[m.cell_id[k]]
m['rnd']=np.random.default_rng(0).random(len(m))
m.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/merged.parquet')
def rec(d, col, lab, valid, sub, k=5):
    d=d[d[valid]] if valid else d
    s=d[col].fillna(-1e9); r=s.groupby([d.season,d.date,d.beat]).rank('first',ascending=False)
    hit=(r<=k)&d[lab]; S=sub(d)
    return 100*hit[S].sum()/max(d[lab][S].sum(),1), int(d[lab][S].sum())
for lab,valid in (('pos_main',None),('pos','valid_strict'),('pos','valid_lenient')):
  for nm,sub in (('all',lambda d:d.season>=2019),('nohist(np=0)',lambda d:(d.season>=2019)&(d.np==0)),('np=1',lambda d:(d.season>=2019)&(d.np==1)),('ysl>=3 incl never',lambda d:(d.season>=2019)&(d.ysl>=3)),('nohist 2020+',lambda d:(d.season>=2020)&(d.np==0))):
    print(lab,valid,nm, *['%s %.1f%% (n=%d)'%((c,)+rec(m,c,lab,valid,sub)) for c in ('pipeline_lean','lean_ensemble','rnd')])
