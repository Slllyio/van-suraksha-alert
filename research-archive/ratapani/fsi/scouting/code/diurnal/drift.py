import pandas as pd, numpy as np
P='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r7_diurnal/'
m=pd.read_parquet(P+'modis_aoi.parquet'); n=pd.read_parquet(P+'n20_aoi.parquet')
n['yr']=n.acq_date.dt.year
a=m[(m.satellite=='Aqua')&(m.daynight=='D')]; t=m[(m.satellite=='Terra')&(m.daynight=='D')]
nd=n[n.daynight=='D']
y=pd.DataFrame({'aqua':a.groupby('yr').size(),'terra':t.groupby('yr').size(),'n20day':nd.groupby('yr').size(),'aqua_ist':a.groupby('yr').ist.median().round(2),'terra_ist':t.groupby('yr').ist.median().round(2)})
y['aqua_per_100n20']=(100*y.aqua/y.n20day).round(1); y['terra_per_100n20']=(100*y.terra/y.n20day).round(1)
print(y.loc[2018:])
# per-pass time bin: Aqua detections per day vs N20 same day, binned by aqua ist
