"""Pipeline rule: tag likely control (managed) burns in VIIRS points. Input: points with lat, lon, IST datetime, daynight, frp
(any of S-NPP/NOAA-20/NOAA-21). Output: per-point column `burn_class` in {pre_season_control, likely_control, fire}.

Rule (r15 'burn' scouting, 16 Oct 2026):
  1. Burn-day clusters: points on the same fire-day (night points 00:00-05:59 IST belong to the previous day) within 750 m.
  2. core = no night detection within 1.5 km on that fire-day AND no detection within 1 km on the 3 following or 2 preceding days
            AND cluster has <= 2 points AND max FRP <= 5 MW.
  3. Date before 15 Feb (Oct-14 Feb)          -> pre_season_control (all points; out of the 15 Feb-15 Jun target, kept as fuel-removal input)
     15-28 Feb and core                       -> likely_control (drop from training positives / scoring; est. precision 64-73% MP-wide)
     otherwise                                -> fire
  In LIVE mode the 'following days' test is unknown: use day-only + <=2 points + FRP<=5 and give such 15-28 Feb alerts low priority instead of dropping.
"""
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
def xy(lat,lon):
    lat0=np.radians(23.5); return np.c_[np.radians(lon)*6371000*np.cos(lat0), np.radians(lat)*6371000]
def control_burn_flag(p, live=False):
    p=p.copy(); t=pd.to_datetime(p.t_ist)
    fd=(t.dt.normalize()-pd.Timedelta(days=0)).values.astype('datetime64[D]').astype(int)
    fd=fd-np.where((p.daynight.values=='N')&(t.dt.hour.values<6),1,0); p['fday']=fd
    X=xy(p.latitude.values,p.longitude.values); p['cid']=-1; off=0
    for k,idx in p.groupby('fday').indices.items():
        if len(idx)==1: p.iloc[idx,p.columns.get_loc('cid')]=off; off+=1; continue
        pr=cKDTree(X[idx]).query_pairs(750,output_type='ndarray')
        n,l=connected_components(coo_matrix((np.ones(len(pr)),(pr[:,0],pr[:,1])),shape=(len(idx),)*2),directed=False)
        p.iloc[idx,p.columns.get_loc('cid')]=l+off; off+=n
    trees={k:(cKDTree(X[i]),i) for k,i in p.groupby('fday').indices.items()}
    night=(p.daynight.values=='N'); nn=np.zeros(len(p),bool); other=np.zeros(len(p),bool)
    for k,(tr,i) in trees.items():
        ni=i[night[i]]
        if len(ni): nn[i]=[len(r)>0 for r in cKDTree(X[ni]).query_ball_point(X[i],1500)]
        if not live:
            for dd in (-2,-1,1,2,3):
                if k+dd in trees: other[i]|=[len(r)>0 for r in trees[k+dd][0].query_ball_point(X[i],1000)]
    p['nn']=nn; p['other']=other
    g=p.groupby('cid'); core=(~g.nn.transform('any'))&(~g.other.transform('any'))&(g.frp.transform('size')<=2)&(g.frp.transform('max')<=5)
    m=t.dt.month; d=t.dt.day
    pre=(m>=10)|(m==1)|((m==2)&(d<15)); late_feb=(m==2)&(d>=15)
    p['burn_class']=np.where(pre,'pre_season_control',np.where(late_feb&core,'likely_control','fire'))
    return p.drop(columns=['nn','other'])
if __name__=='__main__':
    import sys
    W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
    p=pd.read_parquet(W+'pts_feat2.parquet',columns=['latitude','longitude','t_ist','daynight','frp','Division','season','sat'])
    for dv in ['Obedullahganj','Kanha Tiger Reserve','Satpura_TR']:
        q=control_burn_flag(p[p.Division==dv])
        t=pd.to_datetime(q.t_ist); s=q[(t.dt.month.between(2,6))&~((t.dt.month==2)&(t.dt.day<15))&~((t.dt.month==6)&(t.dt.day>15))]
        print(dv, s.groupby('season').burn_class.apply(lambda x:(x=='likely_control').mean()).round(3).to_dict(), 'overall',round((s.burn_class=='likely_control').mean(),4),'n',len(s))
