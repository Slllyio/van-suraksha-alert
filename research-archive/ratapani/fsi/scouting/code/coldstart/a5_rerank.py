import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree; import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/'
n=3614; G=json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
xy=np.zeros((n,2))
for f in G: p=f['properties']; xy[p['cell_id']]=(p['x0']+250,p['y0']+250)
pr=cKDTree(xy).query_pairs(1001,output_type='ndarray'); A1=sp.coo_matrix((np.ones(len(pr)*2),(np.r_[pr[:,0],pr[:,1]],np.r_[pr[:,1],pr[:,0]])),(n,n)).tocsr()
deg=np.asarray(A1.sum(1)).ravel()
m=pd.read_parquet(W+'merged.parquet'); m=m[m.season>=2019].copy()
cs=pd.read_csv('/mnt/project-files/research/ratapani-ignition/cells_static.csv').set_index('cell_id')
m['elig']=cs.elig_ha.reindex(m.cell_id).values
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_end'])
fb=b[b.burned==1].sort_values('window_end').drop_duplicates(['season','cell_id'])
m['nb7']=0.0; m['nbs']=0.0
for Y in m.season.unique():
    d0=pd.Timestamp(f'{Y-1}-12-01'); days=pd.date_range(d0,f'{Y}-06-30'); ev=np.zeros((len(days),n))
    g=fb[fb.season==Y]; ev[(g.window_end-d0).dt.days.values,g.cell_id.values]=1
    cum=np.cumsum(ev,0); nbc=(A1@cum.T).T  # neighbours seen by day
    k=(m.season==Y).values; ti=(m.date[k]-d0).dt.days.values; c=m.cell_id[k].values
    m.loc[k,'nbs']=nbc[ti-1,c]/deg[c]; m.loc[k,'nb7']=nbc[ti-1,c]-nbc[ti-8,c]
m['lg']=np.log(np.clip(m.pipeline_lean,1e-5,1)/(1-np.clip(m.pipeline_lean,1e-5,1)))
nh=m.np==0
for lab,valid in (('pos_main',None),('pos','valid_lenient')):
    d=m if valid is None else m[m[valid]]
    q=d[(d.np==0)]
    print(lab,'nohist rows',len(q),'pos',int(q[lab].sum()),'AUC lean %.3f nbs %.3f nb7 %.3f elig %.3f'%tuple(roc_auc_score(q[lab],q[c]) for c in ('pipeline_lean','nbs','nb7','elig')))
    print('  calib: nohist mean lean %.4f obs %.4f | hist mean lean %.4f obs %.4f'%(q.pipeline_lean.mean(),q[lab].mean(),d[d.np>0].pipeline_lean.mean(),d[d.np>0][lab].mean()))
    # LOSO logistic on nohist rows
    d=d.copy(); d['new']=d.pipeline_lean
    X=['lg','nbs','nb7','elig']
    for Y in sorted(d.season.unique()):
        tr=(d.season!=Y)&(d.np==0); te=(d.season==Y)&(d.np==0)
        if d.loc[tr,lab].sum()<5 or te.sum()==0: continue
        lr=LogisticRegression(C=1.0,max_iter=500).fit(np.c_[d.loc[tr,X].values,np.log1p(d.loc[tr,'nb7'].values)],d.loc[tr,lab])
        d.loc[te,'new']=lr.predict_proba(np.c_[d.loc[te,X].values,np.log1p(d.loc[te,'nb7'].values)])[:,1]
    def rec(col,S):
        s=d[col].fillna(-1e9); r=s.groupby([d.season,d.date,d.beat]).rank('first',ascending=False); hit=(r<=5)&d[lab]
        return 100*hit[S].sum()/d[lab][S].sum()
    for nm,S in (('all 2019-24',d.season>=2019),('nohist',d.np==0),('nohist 2020+',(d.np==0)&(d.season>=2020)),('hist',d.np>0)):
        print('  %-14s lean %.2f  rerank %.2f  random %.2f'%(nm,rec('pipeline_lean',S),rec('new',S),rec('rnd',S)))
