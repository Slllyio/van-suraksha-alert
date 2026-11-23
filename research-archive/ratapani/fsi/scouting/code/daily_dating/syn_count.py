import requests
for y in range(2019,2027):
    out=[]
    for col in ['sentinel-3-synergy-syn-l2-netcdf','sentinel-3-olci-lfr-l2-netcdf']:
        body={"collections":[col],"bbox":[77.34,22.82,78.07,23.11],"datetime":f"{y}-02-01T00:00:00Z/{y}-05-31T23:59:59Z","limit":1000}
        n=0; url="https://planetarycomputer.microsoft.com/api/stac/v1/search"; days=set()
        while True:
            j=requests.post(url,json=body,timeout=120).json(); n+=len(j['features']); days|={f['properties']['datetime'][:10] for f in j['features']}
            nx=[l for l in j.get('links',[]) if l['rel']=='next']
            if not nx: break
            body=nx[0].get('body',body); url=nx[0]['href']
        out.append(f"{col.split('-')[2]}: {n} items/{len(days)} days")
    print(y,'Feb-May',' | '.join(out),flush=True)
