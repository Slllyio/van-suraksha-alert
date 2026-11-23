import json,urllib.request,datetime as dt,glob,csv
B="77.34,22.82,78.07,23.11"
G=[]
for yr in range(2019,2027):
    u=f"https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C2076090826-LPCLOUD&bounding_box={B}&temporal={yr}-02-15T00:00:00Z,{yr}-06-15T23:59:59Z&page_size=2000"
    for e in json.load(urllib.request.urlopen(u,timeout=120))['feed']['entry']:
        poly=e.get('polygons') or []; box=e.get('boxes') or []
        if box: s,w,n,ea=map(float,box[0].split())
        elif poly:
            v=list(map(float,poly[0][0].split())); la=v[0::2]; lo=v[1::2]; s,n,w,ea=min(la),max(la),min(lo),max(lo)
        else: continue
        G.append((e['time_start'],e['title'],s,w,n,ea))
json.dump(G,open('gran.json','w')); print(len(G))
