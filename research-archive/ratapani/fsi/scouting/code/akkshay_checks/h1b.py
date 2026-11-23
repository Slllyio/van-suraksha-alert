import pandas as pd, geopandas as gpd, numpy as np
p=pd.read_csv('h1_ign_cells.csv')
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')[['cell_id','forest_frac']]
f=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/mahua/flush_cells.csv')
ob=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')
F=g.merge(f,on='cell_id').merge(ob,on='cell_id',how='left'); F=F[F.forest_frac>0.5].copy()
F['d_ob']=F.d_ob.fillna(F.d_ob.max())
F['zflush']=(F.flush_frac-F.flush_frac.mean())/F.flush_frac.std()
for c in ['feb_ndvi','apr_ndvi']: F['z'+c]=(F[c]-F[c].mean())/F[c].std()
F['logd']=np.log1p(F.d_ob); F['zd']=(F.logd-F.logd.mean())/F.logd.std()
res={}
for per in ['Jan-14Feb','15Feb-Mar','Apr','May-Jun']:
    y=p[p.per==per].groupby('cell_id').size().reindex(F.cell_id,fill_value=0).values
    for lab,cols in [('raw',['zflush']),('ctrl',['zflush','zd','zfeb_ndvi','forest_frac'])]:
        X=sm.add_constant(F[cols]); m=sm.GLM(y,X,family=sm.families.NegativeBinomial(alpha=1.0)).fit()
        b,se=m.params['zflush'],m.bse['zflush']
        print(f'{per:10s} {lab:4s} rate ratio per 1 SD flusher share: {np.exp(b):.2f} (95% CI {np.exp(b-1.96*se):.2f}-{np.exp(b+1.96*se):.2f})  n_ign={y.sum()}')
