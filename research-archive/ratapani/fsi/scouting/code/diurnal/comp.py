import pandas as pd, numpy as np, glob
P='/mnt/project-files/ratapani/fsi/fsi_portal/'
d=pd.concat([pd.read_csv(f) for f in glob.glob(P+'fsi_pts_*.csv')+[P+'obd_2026.csv']]).drop_duplicates(['Fire_Date','Fire_Time','Lat','Lon']).reset_index(drop=True)
d['m']=pd.to_datetime(d.Fire_Date).dt.month
d['s']=np.where(d.m.isin([11,12,1,2]),'NovFeb',np.where(d.m.isin([3,4,5,6]),'MarJun','other'))
d['comp']=d.Division+'|'+d.Compartment_No.astype(str)
for s,g in d.groupby('s'):
    vc=g.comp.value_counts()
    print(s,len(g),'compartments',len(vc),'top10 share',round(vc.head(10).sum()/len(g),3),'pts/comp',round(len(g)/len(vc),2), 'days',g.Fire_Date.nunique())
a=set(d[d.s=='NovFeb'].comp); b=set(d[d.s=='MarJun'].comp)
print('NovFeb compartments also burning MarJun:',round(len(a&b)/len(a),3))
print(d[d.s=='NovFeb'].groupby('Division').size())
print(d[d.s=='NovFeb'].Range.value_counts().head(8))
