import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from pyproj import Transformer
BW='/mnt/project-files/research/ratapani-burn-labels'
def burn(year):
    with rasterio.open(f'{BW}/rasters/burn_{year}.tif') as r: a=r.read(); T=r.transform
    return a,T
_cell={}
def cellraster(T,shape):
    k=(T.c,T.f,shape)
    if k not in _cell:
        g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643)
        _cell[k]=rasterize(((geom,int(c)) for geom,c in zip(g.geometry,g.cell_id)),out_shape=shape,transform=T,fill=-1,dtype='int32')
    return _cell[k]
def windows_px(year):
    """DataFrame of burned 20 m pixels: r, c, cell_id, s, e, mag"""
    a,T=burn(year); cr=cellraster(T,a.shape[1:])
    r,c=np.where((a[0]!=-999)&(cr>=0))
    return pd.DataFrame(dict(r=r,c=c,cell_id=cr[r,c],s=a[1][r,c],e=a[0][r,c],mag=a[2][r,c])),a,T,cr
def viirs_first():
    """VIIRS alerts mapped to cells with IST fractional day-of-year per season year"""
    L=pd.read_csv('/mnt/project-files/fire-alert-scars/alert_scar_lookup.csv',usecols=['latitude','longitude','acq_date','acq_time','sensor'])
    L=L[L.sensor.str.contains('viirs')].copy()
    g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')
    P=gpd.GeoDataFrame(L,geometry=gpd.points_from_xy(L.longitude,L.latitude),crs=4326)
    j=gpd.sjoin(P,g[['cell_id','geometry']],predicate='within')
    tm=j.acq_time.astype(float).astype(int)
    t=pd.to_datetime(j.acq_date)+pd.to_timedelta(tm//100,unit='h')+pd.to_timedelta(tm%100,unit='m')+pd.Timedelta(hours=5.5)
    j['t']=t; return j[['cell_id','t']].reset_index(drop=True)
def ist_doy(t,year):
    return (t-pd.Timestamp(f'{year}-01-01')).total_seconds()/86400
