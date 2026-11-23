"""Sentinel-3 SLSTR night (~22:20 IST) and day (~10:30 IST) hot pixels as extra looks in the 24 h MP big-fire map.
Truth, fires, area model exactly as mp_bigfire_apply.py (truth from VIIRS looks only). SLSTR pixels (1 km) added as extra points."""
import os, sys, json, pickle, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,'/mnt/project-files/ratapani/spread/scripts')
MED=24.1; LINK=750.0; RES=20.0; MB='/tmp/claude-0/mpbig'
so=lambda a,b: 2*(a&b).sum()/max(a.sum()+b.sum(),1)
from scipy.sparse import coo_matrix; from scipy.sparse.csgraph import connected_components
def clusters(xy):
    if len(xy)==1: return np.zeros(1,int)
    p=np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p)==0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)),(p[:,0],p[:,1])),shape=(len(xy),len(xy))),directed=False)[1]
R=pd.read_csv('/tmp/claude-0/unseen/area_model.csv')
FEAT=['doy','hour','n_dots','n_last','n_prev','n_fronts','n_act','age_h','gap_h','frp_last','frp_max','frp_all','ext_x','ext_y','foot_ha','day','sats_last']
AM=lgb.LGBMRegressor(n_estimators=300,learning_rate=.03,num_leaves=15,min_child_samples=30,n_jobs=1,verbose=-1).fit(R[FEAT],np.log1p(R.extra_true_ha))
C=pd.read_parquet('cand.parquet')
TH={'ASC':(6,12),'DES':(6,12)}
C=pd.concat([C[(C.od==o)&(C.zF>kz)&(C.zD>kz)&(C.dF>kd)&(C.dD>kd)] for o,(kz,kd) in TH.items()])
def one(seed):
    p=f'{MB}/fire_{seed}.pkl'
    if not os.path.exists(p): return []
    z=pickle.load(open(p,'rb')); x0,y1,W,H=z['box']; d=z['d']; dom=z['dom'].ravel(); Tg=z['Tg'].ravel().astype(float); th=z['th']
    rr,cc=np.mgrid[0:H,0:W]; Px=np.c_[(x0+(cc+.5)*RES).ravel(),(y1-(rr+.5)*RES).ravel()]
    s3=C[C.seed==seed]; s3=s3[(s3.x>x0-1000)&(s3.x<x0+W*RES+1000)&(s3.y>y1-H*RES-1000)&(s3.y<y1+1000)]
    tl=d.groupby('lk').t.min(); out=[]
    for k in tl.index[:-1]:
        kn=d[d.lk<=k]; xy=kn[['x','y']].values; lab=clusters(xy); last=kn[kn.lk==k]; prev=kn[kn.lk==k-1]; tk=kn.t.max()
        act=set(lab[(kn.lk>=k-1).values]); nact=len(act); truth=dom&(Tg<=th[k]+24)
        dd=cKDTree(xy).query(Px)[0]; foot=dd<=265; ext=xy.max(0)-xy.min(0)
        f=dict(doy=tk.dayofyear,hour=tk.hour,n_dots=len(xy),n_last=len(last),n_prev=len(prev),n_fronts=len(set(lab)),n_act=nact,
               age_h=(tk-kn.t.min()).total_seconds()/3600,gap_h=(tk-prev.t.max()).total_seconds()/3600 if len(prev) else -1,
               frp_last=last.frp.sum(),frp_max=last.frp.max(),frp_all=kn.frp.sum(),ext_x=ext[0],ext_y=ext[1],foot_ha=foot.sum()*.04,
               day=int((last.daynight=='D').any()),sats_last=last.sensor.nunique())
        la=float(np.expm1(AM.predict(pd.DataFrame([f])[FEAT]))[0])
        order=np.argsort(np.where(foot,-1,dd),kind='stable'); base=np.zeros(len(Px),bool); base[order[:int(foot.sum()+la/.04)]]=True
        row=dict(seed=seed,k=int(k),t=str(tk),learned=so(base,truth))
        tprev=prev.t.max() if len(prev) else tk-pd.Timedelta(hours=12)
        for name,sel in [('all',s3[(s3.t<=tk)&(s3.t>=d.t.min()-pd.Timedelta(days=1))]),('since_prev',s3[(s3.t<=tk)&(s3.t>tprev)])]:
            n_new=0
            if len(sel):
                ds=cKDTree(sel[['x','y']].values).query(Px)[0]; n_new=int((cKDTree(xy).query(sel[['x','y']].values)[0]>1000).sum())
            for rad in (265,500):
                if not len(sel): row[f'{name}_{rad}']=row['learned']; row[f'{name}_{rad}_same']=row['learned']; continue
                dmin=np.minimum(dd,ds); ft=(dd<=265)|(ds<=rad); o=np.argsort(np.where(ft,-1,dmin),kind='stable')
                m=np.zeros(len(Px),bool); m[o[:int(ft.sum()+la/.04)]]=True; row[f'{name}_{rad}']=so(m,truth)
                m=np.zeros(len(Px),bool); m[o[:base.sum()]]=True; row[f'{name}_{rad}_same']=so(m,truth)
            row[f'{name}_n']=len(sel); row[f'{name}_new']=n_new
            if len(sel): row[f'{name}_in_scar']=float(dom[cKDTree(Px).query(sel[['x','y']].values)[1]].mean())
        out.append(row)
    return out
F=pickle.load(open(f'{MB}/fires_list.pkl','rb'))
rows=[]
with ThreadPoolExecutor(8) as ex:
    for i,o in enumerate(ex.map(one,[f[0] for f in F])):
        rows+=o
        if i%100==0: print(i,flush=True)
U=pd.DataFrame(rows); U.to_csv('s3_map_rows.csv',index=False)
cols=[c for c in U.columns if c=='learned' or c.endswith(('_265','_500','_same'))]
fm=U.groupby('seed')[cols].mean()
res=dict(fires=len(fm),forecasts=len(U),mean_by_fire=fm.mean().round(4).to_dict(),
  forecasts_with_s3_since_prev=int((U.since_prev_n>0).sum()),forecasts_with_new_s3=int((U.since_prev_new>0).sum()),
  in_scar_share=round(float(U.since_prev_in_scar.mean()),3))
H=U[U.since_prev_n>0]; res['only_forecasts_with_fresh_s3']=H[cols].mean().round(4).to_dict()
H2=U[U.since_prev_new>0]; res['only_forecasts_with_new_area_s3']=dict(n=len(H2),**H2[cols].mean().round(4).to_dict())
rng=np.random.default_rng(0)
for c in ['all_500','since_prev_500','all_500_same']:
    dl=(fm[c]-fm.learned).values; res[c+'_minus_learned_ci']=[round(float(np.percentile([dl[rng.integers(0,len(dl),len(dl))].mean() for _ in range(2000)],q)),4) for q in (2.5,97.5)]
    res[c+'_better_worse']=[int((dl>.005).sum()),int((dl<-.005).sum())]
json.dump(res,open('s3_map.json','w'),indent=1); print(json.dumps(res,indent=1)); print('EXIT')
