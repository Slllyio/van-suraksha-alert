import requests, io, json, tarfile, tifffile, numpy as np
NO=24
EV="""//VERSION=3
function setup(){return{input:[{bands:["F1","S8","dataMask"]}],output:[{id:"default",bands:%d,sampleType:"FLOAT32"}],mosaicking:"ORBIT"}}
function evaluatePixel(s,sc){var o=new Array(%d).fill(NaN);for(var i=0;i<s.length&&i<%d;i++){if(s[i].dataMask){o[2*i]=s[i].F1;o[2*i+1]=s[i].S8;}}return o}
function updateOutputMetadata(sc,inp,om){om.userData={dates:sc.orbits.map(o=>o.dateFrom)}}"""%(2*NO,2*NO,NO)
def fetch(bbox,fr,to,od,w,h):
    body={"input":{"bounds":{"bbox":bbox},"data":[{"type":"sentinel-3-slstr","dataFilter":{"timeRange":{"from":fr,"to":to},"orbitDirection":od}}]},
      "evalscript":EV,"output":{"width":w,"height":h,"responses":[{"identifier":"default","format":{"type":"image/tiff"}},{"identifier":"userdata","format":{"type":"application/json"}}]}}
    for a in range(4):
        r=requests.post('https://sh.dataspace.copernicus.eu/api/v1/process',json=body,headers={'Accept':'application/tar'},timeout=180)
        if r.status_code==429: import time; time.sleep(10*(a+1)); continue
        r.raise_for_status(); break
    tf=tarfile.open(fileobj=io.BytesIO(r.content))
    ud=json.load(tf.extractfile('userdata.json')); a=tifffile.imread(io.BytesIO(tf.extractfile('default.tif').read()))
    return ud['dates'],a
