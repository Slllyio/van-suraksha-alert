# Power for a DETERRENCE outcome: satellite-detected first-day fires per beat in the pilot season,
# compared between flexible (calendar+forecast) and fixed arms, using the locked beat_arms.csv.
import pandas as pd, numpy as np, geopandas as gpd, json
rng=np.random.default_rng(1)
ip=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv')
ip=ip[(ip.event_role=='first_day_of_fire')&(ip.status=='ok')].copy()
ip['date']=pd.to_datetime(ip.date); ip['yr']=ip.date.dt.year
md=ip.date.dt.month*100+ip.date.dt.day
ip=ip[(md>=215)&(md<=615)]
grid=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')
cb=pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv')
pts=gpd.GeoDataFrame(ip,geometry=gpd.points_from_xy(ip.ign_lon,ip.ign_lat),crs=4326).to_crs(grid.crs)
j=gpd.sjoin(pts,grid[['cell_id','geometry']],how='inner',predicate='within').merge(cb,on='cell_id')
arms=pd.read_csv('/mnt/project-files/research/reframe/pilot/beat_arms.csv')
c=j.groupby(['beat_uid','yr']).size().unstack(fill_value=0)
c=c.reindex(arms.beat_uid,fill_value=0)
yrs=list(range(2017,2027))
c=c.reindex(columns=yrs,fill_value=0)
print('first-day fires in season, total per year:',c.sum().to_dict())
print('per beat per season: mean %.2f, median %.1f, share of beat-seasons with 0: %.2f'%(c.values.mean(),np.median(c.values),(c.values==0).mean()))
# year-to-year correlation of beat counts
r=[np.corrcoef(c[y],c[y+1])[0,1] for y in yrs[:-1]]
print('lag-1 beat count correlation by year:',np.round(r,2))
A=arms.set_index('beat_uid')
flex=(A.arm!='fixed').values; block=A.block.values
def stat(y,base,lab):
    # log rate ratio flexible vs fixed, adjusted by baseline (ratio of sums of y / ratio of sums of base)
    f=lab!='fixed'
    return np.log((y[f].sum()/base[f].sum())/(y[~f].sum()/base[~f].sum()))
def perm_p(y,base,lab,nperm=500):
    obs=stat(y,base,lab); cnt=0
    for _ in range(nperm):
        l=lab.copy()
        for b in np.unique(block):
            m=block==b; l[m]=rng.permutation(l[m])
        if stat(y,base,l)<=obs: cnt+=1
    return (cnt+1)/(nperm+1)
lab=A.arm.values
res={}
for eff in [0.0,0.1,0.2,0.3,0.4]:
    sig=0;n=0
    for y in yrs[2:]:
        base=c[[y-2,y-1]].sum(1).values+0.5
        for rep in range(4):
            yy=c[y].values.astype(float)
            # thin flexible-arm fires by eff (binomial), i.e. deterrence removes eff of starts
            yy=np.where(flex,rng.binomial(yy.astype(int),1-eff),yy)
            p=perm_p(yy,base,lab,300); sig+=p<0.05; n+=1
    res[eff]=sig/n
    print('deterrence %.0f%% in flexible arms -> power %.2f (one-sided 5%%, %d sims over seasons 2019-26)'%(eff*100,sig/n,n))
json.dump({'power_by_effect':res,'lag1_corr':r},open('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_patrol_code/deter_power.json','w'))
