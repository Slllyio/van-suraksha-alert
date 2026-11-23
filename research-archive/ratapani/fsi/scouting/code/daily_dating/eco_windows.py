import pandas as pd, numpy as np
e=pd.read_csv('../r9data/eco_l2_lste.csv'); e['t']=pd.to_datetime(e.time_start).dt.tz_localize(None)+pd.Timedelta(hours=5.5)
e=e.drop_duplicates('t'); e['h']=e.t.dt.hour+e.t.dt.minute/60
w=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv'); w=w[(w.burned==1)&(w.season>=2019)]
# S2/Landsat look ~10:40 IST on ws and we. A pass inside (ws 10:40, we 10:40) splits the window if the scar is visible in LST.
ws=pd.to_datetime(w.window_start)+pd.Timedelta(hours=10.7); we=pd.to_datetime(w.window_end)+pd.Timedelta(hours=10.7)
for lab,sel in [('day 09-17 IST',(e.h>=9)&(e.h<=17)),('afternoon 12-17',(e.h>=12)&(e.h<=17)),('night 19-06',(e.h>=19)|(e.h<6))]:
    tt=np.sort(e[sel].t.values)
    n=np.searchsorted(tt,we.values)-np.searchsorted(tt,ws.values,side='right')
    print(lab,'share of burned windows 2019-26 with >=1 ECOSTRESS pass inside:',(n>0).mean().round(3),' by season:',pd.Series(n>0).groupby(w.season.values).mean().round(2).to_dict())
