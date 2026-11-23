# Same-day S-NPP vs NOAA-20 daytime passes: does the later pass see more fire pixels/FRP? (slope of the diurnal curve in 12:30-14:40 IST)
import pandas as pd, numpy as np, sys
F='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/geo_r8/firms/'
def load(f,box):
    d=pd.read_csv(f); S,N,W,E=box; d=d[d.latitude.between(S,N)&d.longitude.between(W,E)&(d.daynight=='D')&(d.type==0)].copy()
    d['ist']=(d.acq_time//100+(d.acq_time%100)/60+5.5); return d
out=[]
for nm,box in [('AOI',(22.82,23.10,77.34,78.07)),('centralMP',(21,25,75,81))]:
  for yr in ['2022','2024']:
    a=load(F+f'viirs-snpp_{yr}_India.csv',box); b=load(F+f'viirs-jpss1_{yr}_India.csv',box)
    a=a[pd.to_datetime(a.acq_date).dt.month.isin([2,3,4,5])]; b=b[pd.to_datetime(b.acq_date).dt.month.isin([2,3,4,5])]
    ga=a.groupby('acq_date').agg(na=('frp','size'),fa=('frp','sum'),ta=('ist','median')); gb=b.groupby('acq_date').agg(nb=('frp','size'),fb=('frp','sum'),tb=('ist','median'))
    g=ga.join(gb,how='inner'); g=g[(g.na>=3)&(g.nb>=3)]
    g['dt']=g.tb-g.ta  # N20 minus SNPP time (h)
    late_n=np.where(g.dt>0,g.nb,g.na); early_n=np.where(g.dt>0,g.na,g.nb)
    late_f=np.where(g.dt>0,g.fb,g.fa); early_f=np.where(g.dt>0,g.fa,g.fb)
    g['lr_n']=np.log(late_n/early_n); g['lr_f']=np.log(late_f/early_f); g['adt']=g.dt.abs(); g['late_is_N20']=g.dt>0
    print(nm,yr,'days',len(g),'median |dt| %.2f h'%g.adt.median(),'mean log(late/early) count %.3f (se %.3f), FRP %.3f (se %.3f)'%(g.lr_n.mean(),g.lr_n.std()/np.sqrt(len(g)),g.lr_f.mean(),g.lr_f.std()/np.sqrt(len(g))))
    for k,s in g.groupby('late_is_N20'): print('   late=N20' if k else '   late=SNPP',len(s),'mean log ratio count %.3f FRP %.3f, mean |dt| %.2f, mean early time %.2f'%(s.lr_n.mean(),s.lr_f.mean(),s.adt.mean(),np.minimum(s.ta,s.tb).mean()))
    out.append(g.assign(region=nm,yr=yr))
