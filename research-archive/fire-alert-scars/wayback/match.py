# Fires (our per-alert events) that have a Wayback image soon after them. Out: matches.csv
import json, pandas as pd, numpy as np, geopandas as gpd
from shapely.geometry import shape
P = "/mnt/project-files/fire-alert-scars/"
F = gpd.read_file(P + "wayback/footprints_clip.geojson")
F["img"] = pd.to_datetime(F.SRC_DATE.astype(str).str[:8], format="%Y%m%d", errors="coerce")
F = F.dropna(subset=["img"])
# one row per acquisition date x release; keep the newest release that shows that acquisition there
E = pd.concat([pd.read_csv(P + "out/event_scars.csv").assign(src="firms"),
               pd.read_csv(P + "fsi/fsi_alert_events.csv").assign(src="fsi")], ignore_index=True)
E["d"] = pd.to_datetime(E.date)
E = E.rename(columns={"geometry": "scar_geom"})
G = gpd.GeoDataFrame(E[["src", "event_id", "d"]], geometry=gpd.points_from_xy(E.lon, E.lat), crs=4326)
J = gpd.sjoin(G, F[["img", "release", "SRC_RES", "SRC_DESC", "MaxMapLevel", "layer", "geometry"]], predicate="within")
J["age"] = (J.img - J.d).dt.days
J = J[J.age.between(-150, 40)]
post = J[(J.age >= 1) & (J.age <= 40)].sort_values(["age", "release"], ascending=[True, False]).drop_duplicates(["src", "event_id"])
pre = J[(J.age <= -1) & (J.age >= -150)].sort_values(["age", "release"], ascending=[False, False]).drop_duplicates(["src", "event_id"])
M = post.merge(pre[["src", "event_id", "img", "release", "MaxMapLevel", "age"]], on=["src", "event_id"], how="left", suffixes=("", "_pre"))
M = M.merge(E.drop(columns=["d"]), on=["src", "event_id"])
M = M.drop(columns=["geometry_left", "geometry_right", "geometry", "index_right"], errors="ignore")
M.to_csv(P + "wayback/matches.csv", index=False)
M["agebin"] = pd.cut(M.age, [0, 3, 7, 15, 40])
print(len(M), "fires with a post image;", M.img_pre.notna().sum(), "also a pre image")
print(pd.crosstab(M.agebin, M.status))
print(M.d.dt.year.value_counts().sort_index().to_dict())
