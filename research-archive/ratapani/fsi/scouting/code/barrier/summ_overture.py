import geopandas as gpd, pandas as pd
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
aoi=gpd.read_file('/mnt/project-files/ratapani/ratapani_aoi.geojson').to_crs(32643)
print(aoi.shape, aoi.area.sum()/1e6, list(aoi.columns))
A=aoi.union_all()
for typ in ['segment','water','land_use','infrastructure','land']:
    g=gpd.read_file(D+f'overture_{typ}.geojson').to_crs(32643)
    gi=g[g.intersects(A)].copy(); gi['geometry']=gi.intersection(A)
    gi['len_km']=gi.length/1000; gi['area_ha']=gi.area/1e4
    print('==',typ,len(g),'in AOI',len(gi))
    print(gi.groupby(['src','subtype','class'],dropna=False)[['len_km','area_ha']].agg(['count','sum']).round(1).to_string())
