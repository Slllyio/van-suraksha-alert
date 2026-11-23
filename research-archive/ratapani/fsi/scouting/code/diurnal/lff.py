import pandas as pd, numpy as np
d=pd.read_csv('/mnt/project-files/ratapani/fsi/fsi_portal/lff_mp.csv')
for c in ['F_T_D','L_T_D']: d[c]=pd.to_datetime(d[c],format='%Y%m%d_%H%M',errors='coerce')
b=d[(d.INSIDE_X.between(77.2,78.1))&(d.INSIDE_Y.between(22.7,23.3))]
for name,x in [('MP',d),('Ratapani box',b)]:
    print(name,len(x))
    print(' first-det hour',x.F_T_D.dt.hour.value_counts().sort_index().to_dict())
    dur=(x.L_T_D-x.F_T_D).dt.total_seconds()/3600
    print(' duration h quantiles',dur.quantile([.1,.25,.5,.75,.9,.95]).round(1).to_dict(), ' share single-detection', (dur==0).mean().round(3))
    print(' month',x.F_T_D.dt.month.value_counts().sort_index().to_dict())
    print(' first-det night share by month', x.assign(n=x.F_T_D.dt.hour<6).groupby(x.F_T_D.dt.month).n.mean().round(2).to_dict())
    print(' last-det hour', x.L_T_D.dt.hour.value_counts().sort_index().to_dict())
