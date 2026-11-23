import numpy as np, geopandas as gpd
from shapely.ops import unary_union
import sys; sys.path.insert(0,'/mnt/project-files/ratapani/fsi/scouting/code/barrier')
from layers_fn import rast, T, H, W
from shapely.geometry import box
x0,y0=T*(0,0); x1,y1=T*(W,H)
bb=box(min(x0,x1)-2000,min(y0,y1)-2000,max(x0,x1)+2000,max(y0,y1)+2000)
g=gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson').to_crs(32643)
g=g[g.intersects(bb)].copy(); print(len(g), g.Division.unique(), g.Range.nunique())
g['geometry']=g.buffer(0)
g['rk']=g.DID+'-'+g.RID
def bnd(col):
    d=g.dissolve(col)
    lines=[p.boundary for p in d.geometry]
    # internal boundaries only: shared between two units
    out=[]
    for i in range(len(lines)):
        for j in range(i+1,len(lines)):
            s=lines[i].intersection(d.geometry.iloc[j].buffer(15))
            if not s.is_empty and s.length>50: out.append(s)
    return unary_union(out)
div=bnd('DID'); rng=bnd('rk'); beat=bnd('beat_uid')
rng_only=rng.difference(div.buffer(40)); beat_only=beat.difference(rng.buffer(40))
outer=unary_union(list(g.geometry)).boundary
res={}
for k,ln in [('div_line',div),('range_line',rng_only),('beat_line',beat_only),('forest_outer',outer)]:
    print(k, round(ln.length/1000,1),'km')
    m,a=rast([ln]); res[k+'_m']=m; res[k+'_a']=a
    gpd.GeoSeries([ln],crs=32643).to_crs(4326).to_file(f'{k}.geojson')
np.savez_compressed('admin20.npz',**res)
