import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
from sklearn.metrics import roc_auc_score
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/'
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv')
B=(b[b.burned==1].groupby(['season','cell_id']).size().unstack(0).reindex(range(3614)).fillna(0)>0).astype(int)
m=pd.read_parquet(W+'merged.parquet')
m['oth']=0
for Y in range(2017,2025):
    k=m.season==Y; m.loc[k,'oth']=B[[s for s in range(2017,2025) if s!=Y]].sum(axis=1).values[m.cell_id[k]]
def rec(d,col,lab,S):
    s=d[col].fillna(-1e9); r=s.groupby([d.season,d.date,d.beat]).rank('first',ascending=False); hit=(r<=5)&d[lab]
    return 100*hit[S].sum()/max(d[lab][S].sum(),1), int(d[lab][S].sum())
for lab,valid in (('pos_main',None),('pos','valid_strict'),('pos','valid_lenient')):
    d=m if valid is None else m[m[valid]]
    tot=d[lab].sum()
    for nm,S in (('LOSO-cold oth=0',d.oth==0),('oth=1',d.oth==1),('oth=2',d.oth==2),('oth>=3',d.oth>=3),('past-only cold 2020+',(d.np==0)&(d.season>=2020))):
        r1=rec(d,'pipeline_lean',lab,S); r2=rec(d,'rnd',lab,S)
        print(lab,valid,'%-22s lean %.1f%% random %.1f%% positives %d (%.1f%% of all)'%(nm,r1[0],r2[0],r1[1],100*r1[1]/tot))
    q=d[d.oth==0]
    if q[lab].sum()>5: print('   AUC within LOSO-cold: %.3f; mean pred %.4f obs %.4f'%(roc_auc_score(q[lab],q.pipeline_lean),q.pipeline_lean.mean(),q[lab].mean()))
# Who burns among LOSO-cold: per season
print(m[(m.oth==0)].groupby('season').agg(cells=('cell_id','nunique'),pos=('pos_main','sum')).to_string())
