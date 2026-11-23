"""List CMR granules over the Ratapani bbox for a collection concept id; writes csv of start times."""
import requests, sys, csv
cid, out = sys.argv[1], sys.argv[2]
temporal = sys.argv[3] if len(sys.argv)>3 else "2018-07-01T00:00:00Z,2026-10-01T00:00:00Z"
url="https://cmr.earthdata.nasa.gov/search/granules.json"
params={"collection_concept_id":cid,"bounding_box":"77.337,22.816,78.068,23.107","temporal":temporal,"page_size":2000}
rows=[]; headers={}
while True:
    r=requests.get(url,params=params,headers=headers,timeout=120); r.raise_for_status()
    e=r.json()["feed"]["entry"]
    rows+= [(g["title"],g["time_start"],g.get("cloud_cover",""),g.get("day_night_flag","")) for g in e]
    sa=r.headers.get("CMR-Search-After")
    if not e or not sa: break
    headers={"CMR-Search-After":sa}
with open(out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["title","time_start","cloud","dn"]); w.writerows(rows)
print(len(rows))
