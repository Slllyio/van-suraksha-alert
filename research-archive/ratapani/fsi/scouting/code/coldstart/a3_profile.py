import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
n=3614
G=json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
xy=np.zeros((n,2)); ff=np.zeros(n)
for f in G: p=f['properties']; xy[p['cell_id']]=(p['x0']+250,p['y0']+250); ff[p['cell_id']]=p['forest_frac']
tree=cKDTree(xy)
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_start','window_end'])
HA=b.groupby(['season','cell_id']).burned_ha.sum().unstack(0).reindex(range(n)).fillna(0)
B=(b[b.burned==1].groupby(['season','cell_id']).size().unstack(0).reindex(range(n)).fillna(0)>0).astype(int)
fb=b[b.burned==1].sort_values('window_end').drop_duplicates(['season','cell_id'])
st=pd.read_parquet('/mnt/project-files/ratapani/scoring/features/static_features.parquet').merge(pd.read_parquet('/mnt/project-files/ratapani/scoring/features/roads_features_v2.parquet'),on='cell_id').set_index('cell_id')
cs=pd.read_csv('/mnt/project-files/research/ratapani-ignition/cells_static.csv').set_index('cell_id')
ob=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/openbuildings_cell_features.csv').set_index('cell_id').reindex(range(n))
v=pd.read_parquet('/mnt/project-files/ratapani/fsi/scouting/data/viirs_cells.parquet')
v13=v[v.year<=2016].groupby('cell_id').size().reindex(range(n)).fillna(0)
vall=v.groupby(['season','cell_id']).size().unstack(0).reindex(range(n)).fillna(0)
s2=pd.read_parquet('/mnt/project-files/research/ratapani-ignition/s2_cells.parquet'); s2['m']=s2.date.dt.month
s2pre=s2[s2.m.isin([1,2])].groupby(['season','cell_id'])[['ndvi','ndmi','nbr']].median()
# clear look count per cell-season
cc=pd.read_parquet('/mnt/project-files/research/ratapani-burn-labels/clear_calendar.parquet')
ccn=cc[cc.clear_frac>=0.5].groupby(['season','cell_id']).size()
rows=[]
for Y in range(2020,2027):
    prior=[s for s in B.columns if s<Y]
    hist=B[prior].sum(axis=1).values; nh=np.where(hist==0)[0]
    hcells=np.where(hist>0)[0]; th=cKDTree(xy[hcells])
    ly=np.where(B[Y-1].values==1)[0]; tl=cKDTree(xy[ly])
    d_hist,_=th.query(xy[nh]); d_ly,_=tl.query(xy[nh])
    nb1=tree.query_ball_point(xy[nh],1001); nb2=tree.query_ball_point(xy[nh],2001)
    # this-season neighbour burning
    fbY=fb[fb.season==Y].set_index('cell_id')
    for i,c in enumerate(nh):
        o=dict(season=Y,cell_id=c,y=int(B.at[c,Y]),d_hist=d_hist[i],d_lastyr=d_ly[i],
               fr_hist1=np.mean(hist[[j for j in nb1[i] if j!=c]]>0), fr_hist2=np.mean(hist[[j for j in nb2[i] if j!=c]]>0),
               fr_ly1=np.mean(B[Y-1].values[[j for j in nb1[i] if j!=c]]), sub_ha_prior=HA.loc[c,prior].sum(),
               viirs_2013_16=v13[c], viirs_prior=vall.loc[c,[s for s in vall.columns if s<Y]].sum(),
               forest_frac=ff[c], nclear=ccn.get((Y,c),0), fr_thisseason1=np.mean(B[Y].values[[j for j in nb1[i] if j!=c]]))
        if o['y']==1:
            r=fbY.loc[c]; ws,we=r.window_start,r.window_end
            nbs=[j for j in nb1[i] if j!=c and j in fbY.index]
            ne=fbY.loc[nbs].window_end if nbs else pd.Series(dtype='datetime64[ns]')
            o['nb_burn_before7']=int(((ne<=we)&(ne>=ws-pd.Timedelta(days=7))).sum()) if nbs else 0
            o['nb_burn_same_or_before']=int((ne<=we).sum()) if nbs else 0
            o['month']=we.month; o['ha']=r.burned_ha
        rows.append(o)
D=pd.DataFrame(rows).join(st,on='cell_id').join(cs[['elig_ha','d_built','d_crop','d_aoi']],on='cell_id').join(ob,on='cell_id')
D=D.join(s2pre,on=['season','cell_id'])
D.to_csv('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/nohist_profile.csv',index=False)
print('cell-seasons',len(D),'burned',D.y.sum(),'unique never cells',D.cell_id.nunique())
cols=[c for c in D.columns if c not in ('season','cell_id','y','nb_burn_before7','nb_burn_same_or_before','month','ha')]
res=[]
for c in cols:
    x=D[c]; k=x.notna()
    if x[k].nunique()<2: continue
    a=roc_auc_score(D.y[k],x[k]); res.append((c,a,x[D.y==1].median(),x[D.y==0].median()))
res=sorted(res,key=lambda r:-abs(r[1]-0.5))
print('%-22s %6s %10s %10s'%('feature','AUC','med_burn','med_stay'))
for r in res: print('%-22s %6.3f %10.3f %10.3f'%r)
Bn=D[D.y==1]
print('first burns: share with a 1km neighbour burning in the 7 days before or same window: %.2f; any neighbour burned earlier this season: %.2f'%((Bn.nb_burn_before7>0).mean(),(Bn.nb_burn_same_or_before>0).mean()))
print('month',Bn.month.value_counts().sort_index().to_dict(),'median ha',Bn.ha.median())
