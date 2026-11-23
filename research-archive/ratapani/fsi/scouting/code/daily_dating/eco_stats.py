import pandas as pd, sys
d=pd.read_csv(sys.argv[1]); d['t']=pd.to_datetime(d.time_start)+pd.Timedelta(hours=5.5)
d=d.drop_duplicates('t')
d['orbit']=d.title.str.split('_').str[3]
d=d.drop_duplicates('orbit')
d['h']=d.t.dt.hour+d.t.dt.minute/60
s=d[d.t.dt.month.isin([1,2,3,4,5,6])].copy(); s['yr']=s.t.dt.year
print('all overpasses',len(d),'fire season',len(s))
s['slot']=pd.cut(s.h,[0,6,10,12,16,19,24],labels=['00-06','06-10','10-12','12-16','16-19','19-24'])
print(pd.crosstab(s.yr,s.slot,margins=True))
ma=s[s.t.dt.month.isin([3,4])]
print('Mar-Apr 12-19 IST per year:',ma[(ma.h>=12)&(ma.h<19)].groupby('yr').size().to_dict())
