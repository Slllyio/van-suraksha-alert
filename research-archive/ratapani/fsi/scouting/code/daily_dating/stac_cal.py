"""List every S2 / Landsat / HLS item over the Ratapani bbox, Dec-Jun 2016-2026, any cloud cover, from Planetary Computer STAC."""
import requests, json, sys, pandas as pd
API="https://planetarycomputer.microsoft.com/api/stac/v1/search"
BBOX=[77.337,22.816,78.068,23.107]
def search(col, dt):
    body={"collections":[col],"bbox":BBOX,"datetime":dt,"limit":500}
    rows=[]; url=API
    while True:
        r=requests.post(url,json=body,timeout=120); r.raise_for_status(); j=r.json()
        for f in j["features"]:
            p=f["properties"]
            rows.append(dict(col=col,id=f["id"],datetime=p.get("datetime"),platform=p.get("platform"),
                 cloud=p.get("eo:cloud_cover"),tile=p.get("s2:mgrs_tile") or p.get("landsat:wrs_path","")+"/"+str(p.get("landsat:wrs_row","")),
                 nodata=p.get("s2:nodata_pixel_percentage"),geom=json.dumps(f["geometry"])))
        nxt=[l for l in j.get("links",[]) if l.get("rel")=="next"]
        if not nxt: break
        body=nxt[0].get("body",body); url=nxt[0]["href"]
    return rows
out=[]
cols=sys.argv[1].split(",")
for col in cols:
    for y in range(2016,2027):
        dt=f"{y}-12-01T00:00:00Z/{y+1}-06-20T23:59:59Z" if False else f"{y-1}-12-01T00:00:00Z/{y}-06-20T23:59:59Z"
        rr=search(col,dt); print(col,y,len(rr),flush=True); out+=rr
pd.DataFrame(out).to_csv(sys.argv[2],index=False)
