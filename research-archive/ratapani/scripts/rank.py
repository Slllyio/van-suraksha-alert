import pickle, glob, pandas as pd, numpy as np, json
from shapely.ops import unary_union
from shapely import contains_xy
from pyproj import Geod
G=Geod(ellps='WGS84')
o=pickle.load(open('pa.pkl','rb'))
by=lambda nm,st='MADHYA PRADESH':[x['geom'] for x in o if x['name']==nm and x.get('state_name')==st][0]
TR={'Kanha':o[826]['geom'],'Bandhavgarh':o[816]['geom'],'Panna':o[841]['geom'],'Satpura':o[852]['geom'],
    'Pench':o[844]['geom'],'Sanjay-Dubri':o[848]['geom'],'Madhav':unary_union([o[807]['geom'],o[808]['geom']]),
    'Veerangana Durgavati':unary_union([by('Noradehi'),by('Veerangna Durgavati')]),'Ratapani':by('Ratapani')}
pickle.dump(TR,open('tr.pkl','wb'))
df=pd.concat([pd.read_csv(f) for f in sorted(glob.glob('firms/mp_*.csv'))])
df['date']=pd.to_datetime(df.acq_date); df['month']=df.date.dt.month; df['year']=df.date.dt.year
rows=[]
for k,g in TR.items():
    m=contains_xy(g,df.longitude.values,df.latitude.values)
    d=df[m]; area=abs(G.geometry_area_perimeter(g)[0])/1e6
    s=d[d.month.between(2,6)]
    fd=s.drop_duplicates('acq_date').shape[0]
    rows.append(dict(reserve=k,area_km2=round(area),detections=len(d),season_det=len(s),fire_days=fd,
        det_per_100km2_yr=round(len(d)/area*100/12,1),low_conf=round((d.confidence=='l').mean(),2),
        by_year=d.groupby('year').size().reindex(range(2013,2025),fill_value=0).tolist()))
    d.assign(reserve=k).to_parquet(f'det_{k.replace(" ","_")}.parquet')
r=pd.DataFrame(rows).sort_values('detections',ascending=False)
pd.set_option('display.width',250); pd.set_option('display.max_colwidth',80)
print(r.to_string(index=False)); r.to_json('rank.json',orient='records')
