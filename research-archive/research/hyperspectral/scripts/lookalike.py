# Why do chronic-burning forest squares burn, and which look-alike squares (same vegetation + terrain) rarely burn?
import pandas as pd, numpy as np, geopandas as gpd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from scipy.ndimage import uniform_filter
P='/mnt/project-files/'
st=pd.read_parquet(P+'ratapani/mp_grid/static_gis_v1.parquet')
h=pd.read_csv(P+'fire-alert-scars/mp/burn_history/cell_burn_history.csv')[['cell','years_burned','mean_forest_share_burned']]
d=st.merge(h,on='cell',how='left').fillna({'years_burned':0,'mean_forest_share_burned':0})
print(d[['d_edge_in','d_road','d_village','villages_5k','road_km_5k','forest_5k','farm_5k']].describe().round(2).T)
# neighbours' burning: mean years_burned in 5x5 km window (11x11 cells) excluding the cell itself, over beat cells
G=np.zeros((1332,1829)); M=np.zeros_like(G)
G[d.row,d.col]=d.years_burned; M[d.row,d.col]=1
k=11; s=uniform_filter(G,k,mode='constant')*k*k-G; n=uniform_filter(M,k,mode='constant')*k*k-M
d['nbr_years']=(s/np.maximum(n,1))[d.row,d.col]
# reserve + division
xy=gpd.GeoDataFrame(d[['cell']],geometry=gpd.points_from_xy(399000+(d.col+0.5)*500,2996000-(d.row+0.5)*500),crs=32643).to_crs(4326)
res=gpd.read_file(P+'ratapani/mp_grid/reserves.geojson'); div=gpd.read_file(P+'fire-alert-scars/mp/out/mp_divisions.geojson')
d['reserve']=gpd.sjoin(xy,res[['reserve','geometry']],how='left',predicate='within').groupby(level=0).reserve.first().notna().astype(int).values
d['division']=gpd.sjoin(xy,div,how='left',predicate='within').groupby(level=0).Division.first().values
d=d[(d.lc_forest+d.lc_scrub>=0.5)&(d.beat_frac>=0.5)].copy()
d['chronic']=(d.years_burned>=5).astype(int); d['rare']=(d.years_burned<=1).astype(int)
print('forest beat squares',len(d),'chronic',d.chronic.sum(),'rare',d.rare.sum())
LOOK=['lc_forest','lc_scrub','lc_grass','lc_sal','lc_teak','lc_drymix','lc_moistmix','lc_bamboo','lc_degraded','elev','slope','rugged','rough_in','tpi5','south']
PEOPLE=['d_village','villages_5k','d_road','road_km_5k','d_major','farm_2k5','farm_5k','settle_5k','d_edge_in','forest_5k','d_forest_out']
s=d[(d.chronic==1)|(d.rare==1)].copy()
s['blk']=(s.row//20)*1000+s.col//20; rng=np.random.default_rng(0); b=s.blk.unique(); s['fold']=s.blk.map(dict(zip(b,rng.integers(0,5,len(b)))))
def cv(cols,y):
    p=np.zeros(len(s))
    for f in range(5):
        tr=(s.fold!=f).values
        m=lgb.LGBMClassifier(n_estimators=400,learning_rate=0.03,min_child_samples=100,subsample=0.8,subsample_freq=1,colsample_bytree=0.7,verbose=-1).fit(s.loc[tr,cols],y[tr])
        p[~tr]=m.predict_proba(s.loc[~tr,cols])[:,1]
    return p
y=s.chronic.values
s['look']=cv(LOOK,y)
print('chronic vs rare AUC: vegetation+terrain only',round(roc_auc_score(y,s.look),3))
for nm,c in [('people/access only',PEOPLE),('look+people',LOOK+PEOPLE),('look+people+reserve',LOOK+PEOPLE+['reserve']),('look+people+neighbours',LOOK+PEOPLE+['reserve','nbr_years'])]:
    print(f'  {nm:28s}',round(roc_auc_score(y,cv(c,y)),3))
# look-alikes: rare squares whose vegetation+terrain score is as high as a typical chronic square
thr=s.loc[s.chronic==1,'look'].median()
s['group']=np.where(s.chronic==1,'chronic',np.where(s.look>=thr,'lookalike','rare_other'))
# compare chronic vs look-alike on same look score: match each look-alike to chronic squares in same division and look-score decile
s['lbin']=pd.qcut(s.look,20,labels=False,duplicates='drop')
cmp=s[s.group.isin(['chronic','lookalike'])]
num=PEOPLE+['reserve','nbr_years','lc_teak','lc_sal','lc_bamboo','lc_degraded','slope','elev']
rows=[]
for v in num:
    a=cmp[cmp.group=='chronic'][v]; l=cmp[cmp.group=='lookalike'][v]
    # within division x look-bin difference (weights = lookalikes)
    g=cmp.groupby(['division','lbin','group'])[v].median().unstack()
    g=g.dropna(); w=cmp[cmp.group=='lookalike'].groupby(['division','lbin']).size().reindex(g.index).fillna(0)
    within=np.average(g['chronic']-g['lookalike'],weights=w) if w.sum()>0 else np.nan
    rows.append(dict(factor=v,chronic_median=a.median(),lookalike_median=l.median(),within_div_diff=within))
T=pd.DataFrame(rows); print(T.round(3).to_string())
# which factors separate chronic from look-alikes (same look) - model + importance
c2=cmp.copy(); yy=(c2.group=='chronic').astype(int).values
fac=PEOPLE+['reserve','nbr_years']
p=np.zeros(len(c2))
for f in range(5):
    tr=(c2.fold!=f).values
    p[~tr]=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.03,min_child_samples=100,verbose=-1).fit(c2.loc[tr,fac],yy[tr]).predict_proba(c2.loc[~tr,fac])[:,1]
print('chronic vs lookalike AUC from people/access/reserve/neighbours',round(roc_auc_score(yy,p),3))
fac2=PEOPLE+['reserve']
p2=np.zeros(len(c2))
for f in range(5):
    tr=(c2.fold!=f).values
    p2[~tr]=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.03,min_child_samples=100,verbose=-1).fit(c2.loc[tr,fac2],yy[tr]).predict_proba(c2.loc[~tr,fac2])[:,1]
print('  without neighbours',round(roc_auc_score(yy,p2),3))
m=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.03,min_child_samples=100,verbose=-1,importance_type='gain').fit(c2[fac],yy)
imp=pd.Series(m.feature_importances_,fac); print((imp/imp.sum()).sort_values(ascending=False).round(3))
# by division
dv=s.groupby('division').agg(squares=('cell','size'),chronic=('chronic','sum'),lookalikes=('group',lambda g:(g=='lookalike').sum()))
dv['lookalike_per_chronic']=dv.lookalikes/dv.chronic.clip(lower=1)
print(dv.sort_values('lookalikes',ascending=False).head(15)); print(dv.sort_values('chronic',ascending=False).head(15))
s[['cell','row','col','division','years_burned','group','look','nbr_years','reserve']+PEOPLE+LOOK].to_parquet('lookalike_cells.parquet')
T.to_csv('lookalike_compare.csv',index=False); dv.to_csv('lookalike_by_division.csv')
