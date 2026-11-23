import requests, pandas as pd, sys
API="https://earth-search.aws.element84.com/v1/search"
rows=[]
for col in sys.argv[1].split(','):
  for y in [2017,2018,2019]:
    body={"collections":[col],"bbox":[77.337,22.816,78.068,23.107],"datetime":f"{y-1}-12-01T00:00:00Z/{y}-06-20T23:59:59Z","limit":200}
    url=API
    while True:
        j=requests.post(url,json=body,timeout=120).json()
        for f in j.get('features',[]): p=f['properties']; rows.append((col,y,f['id'],p['datetime'][:10],p.get('platform'),p.get('eo:cloud_cover'),p.get('s2:processing_baseline')))
        nx=[l for l in j.get('links',[]) if l['rel']=='next']
        if not nx: break
        body=nx[0].get('body',body); url=nx[0]['href']
d=pd.DataFrame(rows,columns=['col','season','id','date','plat','cloud','pb'])
print(d.groupby(['col','season']).agg(items=('id','size'),dates=('date','nunique')))
d.to_csv('../r9data/e84.csv',index=False)
