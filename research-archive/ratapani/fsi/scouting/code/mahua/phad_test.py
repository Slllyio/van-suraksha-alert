"""Distance from each forest cell to the nearest geocoded tendu phad (2026 list) vs burn frequency and timing."""
import numpy as np, pandas as pd, geopandas as gpd
from scipy.stats import spearmanr
from numpy.linalg import lstsq
p=pd.read_csv('out/phads_geocoded.csv').dropna(subset=['lat'])
P=gpd.GeoDataFrame(p,geometry=gpd.points_from_xy(p.lon,p.lat),crs=4326).to_crs(32643).drop_duplicates(subset=['osm_name','lat'])
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643); c=g.geometry.centroid
from scipy.spatial import cKDTree
t=cKDTree(np.c_[P.geometry.x,P.geometry.y]); X=np.c_[c.x,c.y]
dd,_=t.query(X); n5=np.array([len(v) for v in t.query_ball_point(X,5000)])
o=pd.DataFrame({'cell_id':g.cell_id,'d_phad':dd,'n_phad5':n5})
F=pd.read_csv('out/compare_cells.csv').merge(o,on='cell_id').merge(pd.read_csv('out/topo_cells.csv'),on='cell_id')
print('unique phad points',len(P),'| inside 10 km of any forest cell',(t.query(X,1)[0]<1e9).sum())
for x in ['d_phad','n_phad5','d_ob','bld4']:
    print(x,'rho bfreq %.3f  rho doy %.3f'%(spearmanr(F[x],F.bfreq).statistic,spearmanr(F[x],F.doy,nan_policy='omit').statistic))
def partial(df,x,y,ctrl):
    Z=df[[x,y]+ctrl].dropna(); R=Z.rank(); A=np.c_[np.ones(len(R)),R[ctrl].values]
    rx=R[x]-A@lstsq(A,R[x],rcond=None)[0]; ry=R[y]-A@lstsq(A,R[y],rcond=None)[0]; return np.corrcoef(rx,ry)[0,1]
print('partial d_phad | d_ob,bld4: %.3f'%partial(F,'d_phad','bfreq',['d_ob','bld4']))
print('partial n_phad5 | d_ob,bld4: %.3f'%partial(F,'n_phad5','bfreq',['d_ob','bld4']))
F['bin']=pd.cut(F.d_phad/1000,[0,1,2,3,4,5,6,8,30])
print(F.groupby('bin',observed=True).agg(n=('cell_id','size'),bfreq=('bfreq','mean'),doy=('doy','mean'),d_ob=('d_ob','median')).round(3).to_string())
F.to_csv('out/compare_cells_phad.csv',index=False)
