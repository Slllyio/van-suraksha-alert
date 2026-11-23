import pandas as pd, geopandas as gpd, glob, numpy as np
fs=[f for f in glob.glob("/tmp/firms/*_20*.csv")]
D=[]
for f in fs:
    d=pd.read_csv(f)
    if len(d)==0: continue
    s=f.split("/")[-1].rsplit("_",1)[0]; d["sensor"]=s
    D.append(d)
D=pd.concat(D,ignore_index=True)
md=D.acq_date.str[5:]
D=D[(md>="02-15")&(md<="06-15")]
print("season pts in box",len(D))
B=gpd.read_file("/mnt/project-files/ratapani/beats/mp_beats.geojson")
print(B.columns.tolist()[:20], len(B))
P=gpd.GeoDataFrame(D,geometry=gpd.points_from_xy(D.longitude,D.latitude),crs=4326)
B=B.to_crs(4326)
J=gpd.sjoin(P,B[["geometry"]],predicate="within",how="inner")
J=J[~J.index.duplicated()]
print("in beats",len(J))
print(J.groupby([J.acq_date.str[:4],"sensor"]).size().unstack())
J.drop(columns=["geometry","index_right"]).to_csv("/tmp/firms/mp_season_beats.csv",index=False)
