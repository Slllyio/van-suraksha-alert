"""Score S3 cell-window intervals against first VIIRS detection in the same cell inside the window."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); from common import *
V=viirs_first()
def score(df):
    out=[]
    for y,d in df.groupby('season'):
        v=V[V.t.dt.year==y].copy(); v['vd']=[ist_doy(t,y) for t in v.t]
        m=d.merge(v[['cell_id','vd']],on='cell_id')
        m=m[(m.vd>m.s+10.7/24)&(m.vd<=m.e+10.7/24+0.25)]
        m=m.sort_values('vd').drop_duplicates(['cell_id','s','e'])
        out.append(m)
    m=pd.concat(out)
    # inclusive-date interval [floor(cut_lo), floor(cut_hi)] like the output file
    m['hit']=(np.floor(m.vd)>=np.floor(m.cut_lo))&(np.floor(m.vd)<=np.floor(m.cut_hi))
    L=(m.e-m.s); seg=np.floor(m.cut_hi)-np.floor(m.cut_lo)+1
    m['pbase']=np.minimum(seg/(L+1),1)
    return m
if __name__=='__main__':
    d=pd.concat([pd.read_csv(f) for f in sys.argv[1:]]); d=d[d.snr.notna()&(d.n_inside>0)]
    m=score(d)
    m['sc']=pd.cut(m.snr,[-99,1,2,3,99]); m['fb']=pd.cut(m.burned_frac,[0,0.1,0.3,0.5,1.01])
    print(m.groupby(['sc','fb']).agg(n=('hit','size'),hit=('hit','mean'),base=('pbase','mean')).round(2).to_string())
    print(m.groupby('season').agg(n=('hit','size'),hit=('hit','mean'),base=('pbase','mean')).round(3))
