import json, numpy as np, geopandas as gpd
from shapely.geometry import shape
exec(open('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9code_barrier/layers_fn.py').read())
rows=[json.loads(l.split('\t',1)[1]) for l in open('/mnt/project-files/ratapani/fsi/scouting/data/ms_roads_rata.tsv')]
ms=gpd.GeoDataFrame([r['properties'] for r in rows],geometry=[shape(r['geometry']) for r in rows],crs=4326).to_crs(32643)
ms['w']=ms.WidthMeters.astype(float); print(ms.w.describe())
out={}
for nm,lo,hi in [('ms_w_lt7',0,7),('ms_w_7_10',7,10),('ms_w_ge10',10,999)]:
    m,a=rast(list(ms[(ms.w>=lo)&(ms.w<hi)].geometry)); out[nm+'_m']=m; out[nm+'_a']=a.astype(np.float16); print(nm,m.sum()*0.02,'km')
np.savez_compressed(D+'layers20_ms.npz',**out)
