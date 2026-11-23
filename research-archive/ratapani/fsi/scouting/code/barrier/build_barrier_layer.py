# Assemble one clean barrier layer (lines) for the spread model, with per-class hold rates measured on our scars.
import json, numpy as np, geopandas as gpd, pandas as pd, rasterio
from shapely.geometry import shape, LineString, box
from shapely.ops import linemerge
from affine import Affine
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); T=Affine(*z['transform']); H,W=[int(v) for v in z['shape']]
BOX=box(T.c,T.f-H*20,T.c+W*20,T.f)
# p_stop = (hold - null)/(1 - null): share of fire contacts the line stops beyond what a random line of the same layout would show
P={ # class: (hold_all, null_all, hold_far1km, null_far1km)
 'road_ms_7_10m':(0.563,0.374,0.679,0.393),'road_ms_ge10m':(0.665,0.368,0.808,0.396),
 'road_osm':(0.806,0.376,0.865,0.399),'road_tomtom':(0.570,0.418,0.765,0.432),'rail':(0.856,0.427,0.868,0.454),
 'power_line':(0.355,0.360,0.505,0.429),
 'stream_dem_0.25_1km2':(0.505,0.379,None,None),'stream_dem_1_5km2':(0.565,0.384,0.596,0.413),
 'stream_dem_5_25km2':(0.670,0.399,0.742,0.420),'stream_dem_ge25km2':(0.838,0.413,0.901,0.429),
 'drain_bhuvan':(0.456,0.386,None,None),'recurrent_scar_edge':(0.492,0.375,None,None)}
def ps(h,n): return None if h is None else round(max(0.0,(h-n)/(1-n)),2)
rows=[]
def add(geoms,cls,src,lic,extra=None):
    h,n,hf,nf=P[cls]
    for i,g in enumerate(geoms):
        if g is None or g.is_empty: continue
        g=g.intersection(BOX)
        if g.is_empty: continue
        r=dict(cls=cls,source=src,licence=lic,hold_rate=h,hold_null=n,p_stop=ps(h,n),p_stop_far=ps(hf,nf) if hf else None,geometry=g)
        if extra is not None: r.update(extra[i])
        rows.append(r)
# Microsoft roads
L=[json.loads(l.split('\t',1)[1]) for l in open('/mnt/project-files/ratapani/fsi/scouting/data/ms_roads_rata.tsv')]
ms=gpd.GeoDataFrame([r['properties'] for r in L],geometry=[shape(r['geometry']) for r in L],crs=4326).to_crs(32643); ms['w']=ms.WidthMeters.astype(float)
for cls,sel in [('road_ms_7_10m',ms.w<10),('road_ms_ge10m',ms.w>=10)]:
    s=ms[sel]; add(list(s.geometry),cls,'Microsoft Road Detections 2025-04-28','ODbL',[{'width_m':round(w,1)} for w in s.w])
seg=gpd.read_file(D+'overture_segment.geojson').to_crs(32643)
o=seg[(seg.subtype=='road')&(seg.src=='OpenStreetMap')]; add(list(o.geometry),'road_osm','Overture 2026-09-23.0 (OpenStreetMap)','ODbL',[{'osm_class':c} for c in o['class']])
o=seg[seg.src!='OpenStreetMap']; add(list(o.geometry),'road_tomtom','Overture 2026-09-23.0 (TomTom)','ODbL (Overture transportation)',[{'osm_class':c} for c in o['class']])
o=seg[seg.subtype=='rail']; add(list(o.geometry),'rail','Overture 2026-09-23.0 (OpenStreetMap)','ODbL')
inf=gpd.read_file(D+'overture_infrastructure.geojson').to_crs(32643); o=inf[inf['class'].isin(['power_line','minor_line'])]
add(list(o.geometry),'power_line','Overture 2026-09-23.0 (OpenStreetMap)','ODbL')
# DEM streams (Copernicus GLO-30, pysheds D8), class by upstream area at segment midpoint
st=gpd.read_file(D+'streams_0.25km2.geojson').set_crs(32643,allow_override=True)
with rasterio.open(D+'flowacc_utm30.tif') as src:
    mids=[g.interpolate(0.5,normalized=True) for g in st.geometry]
    acc=np.array([v[0] for v in src.sample([(p.x,p.y) for p in mids])])
akm=acc*900/1e6
for cls,lo,hi in [('stream_dem_0.25_1km2',0,1),('stream_dem_1_5km2',1,5),('stream_dem_5_25km2',5,25),('stream_dem_ge25km2',25,1e9)]:
    sel=(akm>=lo)&(akm<hi); add(list(st.geometry[sel]),cls,'derived: Copernicus GLO-30 DEM, D8 flow accumulation','Copernicus DEM licence (free, attribution)',[{'upstream_km2':round(a,2)} for a in akm[sel]])
# raster skeleton -> lines
def vectorize(mask,Tm):
    r,c=np.nonzero(mask); S=set(zip(r.tolist(),c.tolist())); segs=[]
    for (i,j) in S:
        for di,dj in ((0,1),(1,0),(1,1),(1,-1)):
            if (i+di,j+dj) in S:
                if di and dj and ((i+di,j) in S or (i,j+dj) in S): continue
                a=Tm*(j+0.5,i+0.5); b=Tm*(j+dj+0.5,i+di+0.5); segs.append(LineString([a,b]))
    m=linemerge(segs); return list(m.geoms) if hasattr(m,'geoms') else [m]
E=np.load(D+'layers20_extra.npz'); add(vectorize(E['bh_drain_m'],T),'drain_bhuvan','NRSC Bhuvan WMS hydrology:bdrain_qgs, rendered at ~10 m and skeletonised','NRSC/Bhuvan: government data, terms unclear; internal research use')
R=np.load(D+'recurrent_edges_5_0.5.npz'); add(vectorize(R['m_all'],T),'recurrent_scar_edge','derived: in-forest scar edges in >=5 of 10 seasons (event_scars 2017-2026)','project-derived')
g=gpd.GeoDataFrame(rows,crs=32643)
g['len_m']=g.length.round(0)
print(g.groupby('cls').agg(n=('len_m','size'),km=('len_m',lambda x: round(x.sum()/1000))).to_string())
g=g.to_crs(4326); g['geometry']=g.geometry.simplify(0.00002)
g.to_file(D+'barriers_ratapani.geojson',driver='GeoJSON',COORDINATE_PRECISION=6)
import os; print(os.path.getsize(D+'barriers_ratapani.geojson')/1e6,'MB')
