import requests, pandas as pd, sys
U="https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
poly="POLYGON((74 21,82.9 21,82.9 26.9,74 26.9,74 21))"
rows=[]
for pt in ['S2MSI1C','S2MSI2A']:
  for m0,m1 in [('2026-02-15','2026-03-15'),('2026-03-15','2026-04-15'),('2026-04-15','2026-05-15'),('2026-05-15','2026-06-15'),('2025-03-01','2025-04-01')]:
    skip=0
    while True:
        f=(f"Collection/Name eq 'SENTINEL-2' and Attributes/OData.CSC.StringAttribute/any(a:a/Name eq 'productType' and a/OData.CSC.StringAttribute/Value eq '{pt}') "
           f"and OData.CSC.Intersects(area=geography'SRID=4326;{poly}') and ContentDate/Start gt {m0}T00:00:00.000Z and ContentDate/Start lt {m1}T00:00:00.000Z")
        r=requests.get(U,params={'$filter':f,'$top':1000,'$skip':skip,'$select':'Name,ContentDate,PublicationDate,OriginDate'},timeout=120); r.raise_for_status()
        v=r.json()['value']
        for x in v: rows.append(dict(type=pt,name=x['Name'],sensing=x['ContentDate']['Start'],origin=x.get('OriginDate'),pub=x['PublicationDate']))
        if len(v)<1000: break
        skip+=1000
    print(pt,m0,len(rows),flush=True)
D=pd.DataFrame(rows); D.to_csv('cdse_latency.csv',index=False)
