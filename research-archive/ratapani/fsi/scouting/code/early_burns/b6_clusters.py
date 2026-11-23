"""Burn-day clusters (same fire-day, <=750 m, any satellite) with shape, timing, intensity, repeat-site features."""
import pandas as pd, numpy as np
from scipy.spatial import cKDTree
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
d=pd.read_parquet(W+'pts_feat2.parquet')
d['night']=~d.day
g=d.groupby('cid')
c=g.agg(Division=('Division','first'),beat=('beat_uid','first'),season=('season','first'),fday=('fday','first'),date=('date_ist','min'),
        win=('win','first'),n=('frp','size'),nsat=('sat','nunique'),frp_max=('frp','max'),frp_sum=('frp','sum'),
        any_night=('night','any'),night_near=('night_near','any'),persist=('persist','any'),prev2=('prev2','any'),
        x=('x','mean'),y=('y','mean'),d_road=('d_road','min'),d_track=('d_track','min'),d_res=('d_res','min'),d_edge=('d_beatedge','min'),
        snpp=('sat',lambda s:(s=='snpp').any()))
# elongation via PCA for n>=3
def el(idx):
    xy=d.loc[idx,['x','y']].values
    if len(xy)<3: return np.nan, np.nan
    cv=np.cov((xy-xy.mean(0)).T); w,v=np.linalg.eigh(cv); w=np.clip(w,1,None)
    return np.sqrt(w[1]/w[0]), np.degrees(np.arctan2(v[1,1],v[0,1]))%180
E=[el(ix) for ix in g.indices.values()]
c['elong']=[e[0] for e in E]; c['angle']=[e[1] for e in E]
c['length_m']=g.apply(lambda q: np.hypot(q.x.max()-q.x.min(),q.y.max()-q.y.min()))
# burstiness: clusters same division same day, relative to that division-season-window mean per active day
k=c.groupby(['Division','season','fday']).size().rename('div_day_n')
c=c.join(k,on=['Division','season','fday'])
# repeat site: other seasons with a cluster within 500 m and within +-20 season-days
c=c.reset_index()
tr=cKDTree(c[['x','y']].values)
pairs=tr.query_pairs(500,output_type='ndarray')
s=c.season.values; f=c.fday.values
ok=(s[pairs[:,0]]!=s[pairs[:,1]])&(np.abs(f[pairs[:,0]]-f[pairs[:,1]])<=20)
pp=pairs[ok]
rep=pd.DataFrame({'a':np.r_[pp[:,0],pp[:,1]],'sb':np.r_[s[pp[:,1]],s[pp[:,0]]]}).drop_duplicates().groupby('a').size()
c['repeat_seasons']=0; c.loc[rep.index,'repeat_seasons']=rep.values
c.to_parquet(W+'clusters.parquet')
print(len(c)); print(c.groupby('win')[['n','frp_max','any_night','night_near','persist','prev2','elong','length_m','div_day_n','repeat_seasons']].agg(['mean','median']).round(2).T.to_string())
