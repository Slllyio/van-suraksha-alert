"""Combine S3 (2019-23, 2026), Landsat-7 (2017-23) and MCD64A1 into one soft date per burned cell-season (first burned window).
Confidence = hit rate against the first VIIRS detection in the same cell (pooled over seasons, by method class)."""
import sys, os, glob, numpy as np, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); from common import *
OUT=sys.argv[1]; S3_SEASONS=[2019,2020,2021,2022,2023,2026]
w=pd.read_csv(f'{BW}/burn_windows.csv'); w=w[w.burned==1].copy()
w['nw']=w.groupby(['season','cell_id']).cell_id.transform('size')
w=w.sort_values(['season','cell_id','window_start','window_end']).drop_duplicates(['season','cell_id'])
j1=pd.to_datetime(w.season.astype(str)+'-01-01')
w['s']=(pd.to_datetime(w.window_start)-j1).dt.days; w['e']=(pd.to_datetime(w.window_end)-j1).dt.days
key=['season','cell_id','s','e']
s3=pd.concat([pd.read_csv(f) for f in sorted(glob.glob('../r9data/s3soft_*.csv'))]); s3=s3[s3.season.isin(S3_SEASONS)]
l7=pd.concat([pd.read_csv(f) for f in sorted(glob.glob('../r9data/l7soft_*.csv'))])
mc=pd.read_csv('../r9data/mcd64_cells.csv'); mc['bd0']=mc.bd-1
V=viirs_first(); V['season']=V.t.dt.year
def vfirst(df,lo_pad,hi_pad):
    m=df.merge(V,on=['season','cell_id'])
    m['vd']=[ist_doy(t,y) for t,y in zip(m.t,m.season)]
    m=m[(m.vd>m.s+10.7/24-lo_pad)&(m.vd<=m.e+10.7/24+hi_pad)]
    return m.sort_values('vd').drop_duplicates(key)[key+['vd']]
VF=vfirst(w[key],0,0.25)                    # VIIRS inside the window: truth for narrowing methods
VW=vfirst(w[key],10,10)                     # VIIRS within +-10 d: for the window's own reliability
def hit(df,lo,hi):  # inclusive integer days
    m=df.merge(VF,on=key); f=np.floor(m.vd); return m.assign(hit=(f>=m[lo])&(f<=m[hi]))
# ---- S3 candidates
s3=s3[s3.snr.notna()&(s3.n_inside>0)].copy()
s3['lo']=np.floor(s3.cut_lo).astype(int); s3['hi']=np.floor(s3.cut_hi).astype(int)
s3['fbc']=pd.cut(s3.burned_frac,[0,0.1,0.3,1.01],labels=['<0.1','0.1-0.3','>=0.3']).astype(str)
s3['snc']=pd.cut(s3.snr,[-99,2,3,99],labels=['<=2','2-3','>3']).astype(str)
h=hit(s3,'lo','hi'); cal3=h.groupby(['snc','fbc']).hit.agg(['size','mean']).reset_index()
s3=s3.merge(cal3.rename(columns={'mean':'conf','size':'cal_n'}),on=['snc','fbc'],how='left')
s3ok=s3[(s3.snr>2)&(s3.conf>=0.75)&(s3.cal_n>=10)].copy(); s3ok['method']='s3'
# ---- L7
l7=l7[(l7.decided>0)&(l7.consistent==True)].copy()
l7['lo']=np.floor(l7.cut_lo).astype(int); l7['hi']=np.floor(l7.cut_hi).astype(int)
l7['ref']=np.where(l7.has_pre==True,'pre','post')
h7=hit(l7,'lo','hi'); cal7=h7.groupby('ref').hit.agg(['size','mean']).reset_index()
l7=l7.merge(cal7.rename(columns={'mean':'conf','size':'cal_n'}),on='ref',how='left'); l7=l7[(l7.conf>=0.75)&(l7.cal_n>=10)]; l7['method']='l7'
# ---- MCD64
m=w[key].merge(mc,on=['season','cell_id']); m=m[(m.bd0>=m.s)&(m.bd0<=m.e)]
m['lo']=np.maximum(m.bd0-m.unc,m.s); m['hi']=np.minimum(m.bd0+m.unc,m.e)
m=m.sort_values('unc').drop_duplicates(key)
hm=hit(m,'lo','hi'); confm=hm.hit.mean(); m['conf']=confm; m['method']='mcd64'
# ---- choose
w['lo']=w.s; w['hi']=w.e
cand=pd.concat([s3ok[key+['lo','hi','conf','method','burned_frac']],l7[key+['lo','hi','conf','method']]])
cand['lo']=np.maximum(cand.lo,cand.s); cand['hi']=np.minimum(cand.hi,cand.e)
cand=cand[(cand.hi>=cand.lo)&((cand.hi-cand.lo)<(cand.e-cand.s))]
cand['width']=cand.hi-cand.lo
best=cand.sort_values(['width','conf'],ascending=[True,False]).drop_duplicates(key)
m=m[(m.hi-m.lo)<(m.e-m.s)]
rest=m.merge(best[key],on=key,how='left',indicator=True); rest=rest[rest._merge=='left_only'].drop(columns='_merge')
pick=pd.concat([best,rest[key+['lo','hi','conf','method']]])
# window reliability
vw=w[key].merge(VW,on=key); confw=((np.floor(vw.vd)>=vw.s)&(np.floor(vw.vd)<=vw.e)).mean()
R=w.merge(pick,on=key,how='left',suffixes=('_w',''))
R['method']=R.method.fillna('window'); R['lo']=R.lo.fillna(R.s).astype(int); R['hi']=R.hi.fillna(R.e).astype(int); R['conf']=R.conf.fillna(confw)
d=lambda y,x: (pd.to_datetime(y.astype(str)+'-01-01')+pd.to_timedelta(x,unit='D')).dt.strftime('%Y-%m-%d')
out=pd.DataFrame(dict(cell_id=R.cell_id,season=R.season,date_lo=d(R.season,R.lo),date_hi=d(R.season,R.hi),method=R.method,
    burned_frac=np.where(R.method=='s3',R.burned_frac.round(3),np.nan),confidence=R.conf.round(3),orig_lo=R.window_start,orig_hi=R.window_end,
    n_windows=R.nw,burned_ha=R.burned_ha))
out=out.sort_values(['season','cell_id']); os.makedirs(os.path.dirname(OUT),exist_ok=True); out.to_csv(OUT,index=False)
# ---- report
out['w_new']=(pd.to_datetime(out.date_hi)-pd.to_datetime(out.date_lo)).dt.days; out['w_old']=(pd.to_datetime(out.orig_hi)-pd.to_datetime(out.orig_lo)).dt.days
print('rows',len(out)); print(out.method.value_counts(normalize=True).round(3).to_dict())
print('median width new/old (days, hi-lo):',out.w_new.median(),out.w_old.median(),' narrowed rows median new width:',out[out.method!='window'].w_new.median())
print(out.groupby(['season','method']).size().unstack(fill_value=0).to_string())
print('S3 calibration:'); print(cal3.to_string())
print('L7 calibration:'); print(cal7.to_string()); print('MCD64 conf',round(confm,3),'n',len(hm),' window conf',round(confw,3),'n',len(vw))
hh=hit(out.rename(columns={})[[]].assign(**{}),'lo','hi') if False else None
# per-season VIIRS hit rate of the chosen interval
o=out.copy(); j1=pd.to_datetime(o.season.astype(str)+'-01-01')
o['s']=(pd.to_datetime(o.orig_lo)-j1).dt.days; o['e']=(pd.to_datetime(o.orig_hi)-j1).dt.days
o['lo']=(pd.to_datetime(o.date_lo)-j1).dt.days; o['hi']=(pd.to_datetime(o.date_hi)-j1).dt.days
ho=hit(o,'lo','hi'); ho['base']=np.minimum((ho.hi-ho.lo+1)/(ho.e-ho.s+1),1)
print('per-season VIIRS check of chosen intervals (narrowed rows only):')
print(ho[ho.method!='window'].groupby(['season']).agg(n=('hit','size'),hit=('hit','mean'),uniform=('base','mean')).round(3).to_string())
print(ho[ho.method!='window'].groupby(['method']).agg(n=('hit','size'),hit=('hit','mean'),uniform=('base','mean')).round(3).to_string())
ho.to_csv('../r9data/viirs_check.csv',index=False)
o2=out.copy(); o2['narrowed']=o2.method!='window'
print('share narrowed by method:',o2.method.value_counts(normalize=True).round(3).to_dict())
print('narrowed: median width hi-lo',o2[o2.narrowed].w_new.median(),'(inclusive days',o2[o2.narrowed].w_new.median()+1,'); orig median of same rows',o2[o2.narrowed].w_old.median())
print(o2[o2.narrowed].groupby('method').agg(n=('w_new','size'),new=('w_new','median'),old=('w_old','median'),mean_new=('w_new','mean'),mean_old=('w_old','mean')).round(2).to_string())
print('all rows mean width',o2.w_old.mean().round(2),'->',o2.w_new.mean().round(2))
print(o2.groupby('season').agg(narrowed=('narrowed','mean'),old=('w_old','mean'),new=('w_new','mean')).round(3).to_string())
