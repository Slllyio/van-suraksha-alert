import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
n=3614; G=json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
xy=np.zeros((n,2))
for f in G: p=f['properties']; xy[p['cell_id']]=(p['x0']+250,p['y0']+250)
T=cKDTree(xy)
st=pd.read_parquet('/mnt/project-files/ratapani/scoring/features/static_features.parquet').set_index('cell_id').sort_index()
cs=pd.read_csv('/mnt/project-files/research/ratapani-ignition/cells_static.csv').set_index('cell_id').reindex(range(n))
el=st.elev_m.values
for R in (1000,2000):
    nb=T.query_ball_point(xy,R); st[f'tpi{R}']=[el[i]-el[[j for j in nb[i] if j!=i]].mean() for i in range(n)]
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv')
B=(b[b.burned==1].groupby(['season','cell_id']).size().unstack(0).reindex(range(n)).fillna(0)>0).astype(int)
S=list(range(2017,2027))
nb1=T.query_ball_point(xy,1001); nb2=T.query_ball_point(xy,2001)
rows=[]
for Y in S:
    oth=B[[s for s in S if s!=Y]].values; own=oth.mean(1)
    m1=np.array([oth[[j for j in nb1[i] if j!=i]].mean() for i in range(n)]); m2=np.array([oth[[j for j in nb2[i] if j!=i]].mean() for i in range(n)])
    past=B[[s for s in S if s<Y]].values if Y>2017 else np.zeros((n,1))
    for i in range(n): rows.append((Y,i,B.at[i,Y],own[i],m1[i],m2[i],past.sum(1)[i]))
D=pd.DataFrame(rows,columns=['season','cell','y','own','nbr1','nbr2','npast']).join(st[['tpi1000','tpi2000','slope_deg','elev_m']],on='cell').join(cs[['elig_ha']],on='cell')
D['abs_tpi2000']=D.tpi2000.abs(); D['abs_tpi1000']=D.tpi1000.abs()
ok=D.elig_ha>=10
for nm,k in (('LOSO-cold own=0',(D.own==0)),('LOSO-cold own=0 & elig>=10',(D.own==0)&ok),('own<=2/9',(D.own<=2/9)&ok),('all elig>=10',ok)):
    q=D[k]; print(nm,'n=%d burned=%d'%(len(q),q.y.sum()), ' '.join('%s %.3f'%(c,roc_auc_score(q.y,q[c])) for c in ('own','nbr1','nbr2','tpi1000','tpi2000','abs_tpi2000','slope_deg','elig_ha') if q[c].nunique()>1))
# shrinkage prior: compare own vs EB blend at all cells (season-level AUC)
for w in (0,0.25,0.5,0.75):
    q=D[ok]; s=(1-w)*q.own+w*q.nbr1; print('blend w=%.2f AUC %.4f'%(w,roc_auc_score(q.y,s)), end='; ')
print()
# burn frequency by tpi class (all seasons, elig>=10)
q=D[ok]; print(q.groupby(pd.qcut(q.tpi2000,5)).y.mean().round(3).to_string())
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
q=D[ok].copy()
for cols in (['own','nbr1','elev_m','slope_deg'],['own','nbr1','elev_m','slope_deg','tpi2000','tpi1000']):
    p=cross_val_predict(LogisticRegression(max_iter=1000),(q[cols]-q[cols].mean())/q[cols].std(),q.y,groups=q.season,cv=GroupKFold(5),method='predict_proba')[:,1]
    print(cols,'grouped-CV AUC %.4f'%roc_auc_score(q.y,p))
print('elev AUC %.3f'%roc_auc_score(q.y,q.elev_m))
