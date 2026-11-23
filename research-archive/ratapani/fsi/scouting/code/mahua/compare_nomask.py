"""Compare per-cell hot-season green-up features with burn history (cell_season.csv 2017-2026) and controls."""
import numpy as np, pandas as pd, geopandas as gpd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
f=pd.read_csv('out/flush_cells_nomask.csv')
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')[['cell_id','forest_frac']]
cs=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/cell_season.csv',parse_dates=['first_window_start','first_window_end'])
print('cell_season burned_ha min',cs.burned_ha_total.min(), 'rows',len(cs))
cs['doy']=cs.first_window_end.dt.dayofyear
cs['b']=cs.burned_ha_total>=1.0
bf=cs[cs.b].groupby('cell_id').agg(nburn=('season','nunique'),doy=('doy','mean'),ha=('burned_ha_total','mean'))
ob=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')
vt=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/vtm_roy2015_grid500m.csv')[['cell_id','vtm_major']]
sal=pd.read_csv('out/sal_cells.csv')
d=g.merge(f,on='cell_id',how='left').merge(bf,on='cell_id',how='left').merge(ob,on='cell_id',how='left').merge(vt,on='cell_id',how='left').merge(sal,on='cell_id',how='left')
d['nburn']=d.nburn.fillna(0); d['bfreq']=d.nburn/10
F=d[(d.forest_frac>=0.8)&(d.n_px>=300)].copy()
print('forest cells',len(F))
feats=['flush_frac','dam_mean','dam_p90','daf_mean','dre_mean','apr_ndvi','feb_ndvi','sal_frac','d_ob','bld4','forest_frac']
print('\nSpearman with burn frequency 2017-26 (forest cells):')
for c in feats:
    r=spearmanr(F[c],F.bfreq,nan_policy='omit'); print(f'  {c:12s} rho={r.statistic:+.3f}')
print('\nSpearman with mean first-burn DOY (burned cells):')
B=F[F.nburn>0]
for c in ['flush_frac','dam_mean','daf_mean','feb_ndvi','d_ob']:
    r=spearmanr(B[c],B.doy,nan_policy='omit'); print(f'  {c:12s} rho={r.statistic:+.3f}')
F['q']=pd.qcut(F.flush_frac.rank(method='first'),10,labels=False)
print('\nBy flush_frac decile:'); print(F.groupby('q').agg(flush=('flush_frac','mean'),bfreq=('bfreq','mean'),doy=('doy','mean'),feb=('feb_ndvi','mean'),d_ob=('d_ob','median'),n=('cell_id','size')).round(3).to_string())
# partial: rank-regress bfreq on controls, then correlate residual with flush
from numpy.linalg import lstsq
def partial(df,x,y,ctrl):
    Z=df[[x,y]+ctrl].dropna(); R=Z.rank()
    A=np.c_[np.ones(len(R)),R[ctrl].values]
    rx=R[x]-A@lstsq(A,R[x],rcond=None)[0]; ry=R[y]-A@lstsq(A,R[y],rcond=None)[0]
    return np.corrcoef(rx,ry)[0,1],len(Z)
for ctrl in [['feb_ndvi'],['d_ob','bld4'],['feb_ndvi','d_ob','bld4','apr_ndvi']]:
    for x in ['flush_frac','dam_mean','daf_mean']:
        r,n=partial(F,x,'bfreq',ctrl); print(f'partial {x} | {ctrl}: {r:+.3f} (n={n})')
print('\nWithin VTM class:')
for k,G in F.groupby('vtm_major'):
    if len(G)>100: print(f'  {k:15s} n={len(G)} rho(flush,bfreq)={spearmanr(G.flush_frac,G.bfreq,nan_policy="omit").statistic:+.3f}  rho(dam,bfreq)={spearmanr(G.dam_mean,G.bfreq,nan_policy="omit").statistic:+.3f}')
print('rho(sal_frac, flush_frac)=%.3f'%spearmanr(F.sal_frac,F.flush_frac,nan_policy='omit').statistic)
# leave-season-out: does flush add to history + access for predicting burn in season s?
cs2=cs[cs.b][['season','cell_id']].assign(y=1)
seasons=sorted(cs.season.unique())
rows=[]
for s in seasons:
    other=cs2[cs2.season!=s].groupby('cell_id').size().rename('hist')
    X=F[['cell_id']+feats].merge(other,on='cell_id',how='left').fillna({'hist':0})
    X['y']=X.cell_id.isin(cs2[cs2.season==s].cell_id).astype(int)
    rows.append(X.assign(season=s))
D=pd.concat(rows).dropna(subset=['flush_frac','feb_ndvi','d_ob'])
base=['hist','feb_ndvi','apr_ndvi','d_ob','bld4','forest_frac']
for name,cols in [('base',base),('base+flush',base+['flush_frac','dam_mean','daf_mean']),('no-hist',['feb_ndvi','apr_ndvi','d_ob','bld4','forest_frac']),('no-hist+flush',['feb_ndvi','apr_ndvi','d_ob','bld4','forest_frac','flush_frac','dam_mean','daf_mean'])]:
    aucs=[]
    for s in seasons:
        tr,te=D[D.season!=s],D[D.season==s]
        m=LogisticRegression(max_iter=2000).fit((tr[cols]-tr[cols].mean())/tr[cols].std(),tr.y)
        p=m.predict_proba((te[cols]-tr[cols].mean())/tr[cols].std())[:,1]; aucs.append(roc_auc_score(te.y,p))
    print(f'LOSO AUC {name:14s}: mean {np.mean(aucs):.4f}  per season {np.round(aucs,3)}')
F.to_csv('out/compare_cells_nomask.csv',index=False)
