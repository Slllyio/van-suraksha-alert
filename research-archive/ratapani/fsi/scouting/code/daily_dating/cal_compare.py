import pandas as pd
s=pd.read_csv('../r9data/stac_cal.csv'); s['dt']=pd.to_datetime(s.datetime,format='ISO8601'); s['date']=s.dt.dt.date.astype(str)
s['season']=s.dt.dt.year+(s.dt.dt.month==12)
print(s.groupby(['col','platform']).size())
print(s[s.col=='sentinel-2-l2a'].groupby(['season','platform']).size().unstack(fill_value=0))
print(s[s.col=='landsat-c2-l2'].groupby(['season','platform']).size().unstack(fill_value=0))
c=pd.read_parquet('/mnt/project-files/research/ratapani-burn-labels/clear_calendar.parquet')
used=c.groupby(['season','date','sensor']).clear_frac.mean().reset_index()
print('used dates per season/sensor'); print(used.groupby(['season','sensor']).size().unstack())
# distinct acquisition dates per season by source
s['src']=s.col.map({'sentinel-2-l2a':'s2','landsat-c2-l2':'ls','hls2-s30':'hls_s','hls2-l30':'hls_l'})
sd=s.groupby(['season','src','date']).agg(cloud=('cloud','min'),plat=('platform','first')).reset_index()
print(sd.groupby(['season','src']).size().unstack())
sd.to_csv('../r9data/stac_dates.csv',index=False)
