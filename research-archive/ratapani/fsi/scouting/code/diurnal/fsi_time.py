import pandas as pd, glob
P='/mnt/project-files/ratapani/fsi/fsi_portal/'
fs=[f for f in glob.glob(P+'fsi_pts_*.csv')]+[P+'obd_2026.csv']
d=pd.concat([pd.read_csv(f).assign(src=f.split('/')[-1]) for f in fs])
d=d.reset_index(drop=True); print(d.shape); d=d.drop_duplicates(['Fire_Date','Fire_Time','Lat','Lon'])
d=d.reset_index(drop=True); print('unique',d.shape)
d['dt']=pd.to_datetime(d.Fire_Date+' '+d.Fire_Time)
print(d.dt.min(),d.dt.max())
d['h']=d.dt.dt.hour+d.dt.dt.minute/60
print(d.groupby('Source_Type').h.describe())
d['hb']=(d.h//1).astype(int)
print(pd.crosstab(d.hb,d.Source_Type))
d['m']=d.dt.dt.month
d['slot']=pd.cut(d.h,[-1,5,12,18,24],labels=['night01','morn10','aft13','eve'])
print(pd.crosstab([d.Source_Type,d.slot],d.m))
print(d.Division.value_counts().head())
print(d[d.Source_Type=='MODIS'].h.round(1).value_counts().sort_index())
print(d[d.Source_Type=='VIIRS'].h.round(0).value_counts().sort_index())
