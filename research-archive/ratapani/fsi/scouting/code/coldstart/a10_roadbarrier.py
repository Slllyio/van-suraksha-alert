# Among valid cell-days with a 1-km neighbour scar seen in the last 7 days, does a road inside the cell lower the burn rate?
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree; import scipy.sparse as sp
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/'
n=3614; G=json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']; xy=np.zeros((n,2))
for f in G: p=f['properties']; xy[p['cell_id']]=(p['x0']+250,p['y0']+250)
pr=cKDTree(xy).query_pairs(501,output_type='ndarray'); A=sp.coo_matrix((np.ones(len(pr)*2),(np.r_[pr[:,0],pr[:,1]],np.r_[pr[:,1],pr[:,0]])),(n,n)).tocsr()  # rook neighbours
m=pd.read_parquet(W+'merged.parquet')
rd=pd.read_parquet('/mnt/project-files/ratapani/scoring/features/roads_features_v2.parquet').set_index('cell_id')
cs=pd.read_csv('/mnt/project-files/research/ratapani-ignition/cells_static.csv').set_index('cell_id')
m['road']=rd.road_km_in_cell.reindex(m.cell_id).values>0; m['elig']=cs.elig_ha.reindex(m.cell_id).values
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_end'])
fb=b[b.burned==1].sort_values('window_end').drop_duplicates(['season','cell_id'])
m['nb7']=0.0
for Y in m.season.unique():
    d0=pd.Timestamp(f'{Y-1}-12-01'); days=pd.date_range(d0,f'{Y}-06-30'); ev=np.zeros((len(days),n))
    g=fb[fb.season==Y]; ev[(g.window_end-d0).dt.days.values,g.cell_id.values]=1
    cum=np.cumsum(ev,0); nbc=(A@cum.T).T; k=(m.season==Y).values; ti=(m.date[k]-d0).dt.days.values; c=m.cell_id[k].values
    m.loc[k,'nb7']=nbc[ti-1,c]-nbc[ti-8,c]
q=m[(m.nb7>0)&(m.elig>=15)]
print(q.groupby('road').pos_main.agg(['size','mean']).round(4).to_string())
q=m[(m.nb7==0)&(m.elig>=15)]; print('unexposed'); print(q.groupby('road').pos_main.agg(['size','mean']).round(4).to_string())
