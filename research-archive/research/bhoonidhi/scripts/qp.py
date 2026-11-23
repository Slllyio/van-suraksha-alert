import json, urllib.parse, urllib.request, sys, time
U="https://bhoonidhi.nrsc.gov.in/bhoonidhi/ProductSearch"
H={"Content-Type":"application/json","token":"null","User-Agent":"Mozilla/5.0"}
def enc(d): return {k: urllib.parse.quote(str(v), safe='') for k,v in d.items()}
def search(sats, sd, ed, tl=(26.9,74.0), br=(21.0,82.9), offset=0):
    a=dict(userId="T",prod="Standard",selSats=",".join(sats),offset=offset,sdate=sd,edate=ed,query="area",queryType="polygon",isMX="No",tllat=tl[0],tllon=tl[1],brlat=br[0],brlon=br[1],filters="{}")
    for k in range(8):
        try:
            r=urllib.request.Request(U,data=json.dumps(enc(a)).encode(),headers=H)
            return json.load(urllib.request.urlopen(r,timeout=180))
        except Exception as e:
            print("retry",e,file=sys.stderr); time.sleep(15*(k+1))
    raise SystemExit("failed")
