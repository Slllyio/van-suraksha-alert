"""Blind sample for the eye check: real scar outlines mixed with decoys (the same outline and point moved
3 km to forest with no alert within 1.5 km / 30 days, on the same post-fire image). Labels in key.csv
(not looked at while judging). Out: sample.csv, key.csv"""
import json, numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import shape, Point, mapping
from shapely.affinity import translate
from pyproj import Transformer
D = "/mnt/project-files/fire-alert-scars/wayback/"; R = "/mnt/project-files/fire-alert-scars/"
TO = Transformer.from_crs(4326, 32643, always_xy=True); BK = Transformer.from_crs(32643, 4326, always_xy=True)
M = pd.read_csv(D + "matches.csv")
M = M[M.scar_geom.notna() | (M.status == "no_scar_seen")]
rng = np.random.default_rng(3)
take = lambda df, n: df.sample(min(len(df), n), random_state=3)
S = pd.concat([take(M[M.age <= 7], 200), take(M[M.age.between(8, 15)], 60), take(M[M.age > 15], 40),
               M[M.status != "scar"]]).drop_duplicates(["src", "event_id"])
F = gpd.read_file(D + "footprints_clip.geojson")
grid = gpd.read_file("/mnt/project-files/ratapani/grid_500m.geojson").to_crs(32643)
forest = grid[grid.forest_frac >= 0.7].union_all()
A = pd.read_csv(R + "alert_scar_lookup.csv", usecols=["latitude", "longitude", "acq_date"])
A["x"], A["y"] = TO.transform(A.longitude.values, A.latitude.values); A["d"] = pd.to_datetime(A.acq_date)
dec = []
for r in take(S[S.scar_geom.notna()], 90).itertuples():
    x, y = TO.transform(r.lon, r.lat); d = pd.Timestamp(r.d)
    fp = F[(F.release == r.release) & (F.layer == r.layer) & (pd.to_datetime(F.SRC_DATE.astype(str), format="%Y%m%d") == pd.Timestamp(r.img))]
    for _ in range(30):
        th = rng.uniform(0, 2 * np.pi); dx, dy = 3000 * np.cos(th), 3000 * np.sin(th)
        nx, ny = x + dx, y + dy
        if not forest.contains(Point(nx, ny)):
            continue
        lo, la = BK.transform(nx, ny)
        if not len(fp) or not fp.geometry.iloc[0].contains(Point(lo, la)):
            continue
        near = A[(A.d - d).abs() <= pd.Timedelta("30D")]
        if len(near) and np.hypot(near.x - nx, near.y - ny).min() < 1500:
            continue
        g = shape(json.loads(r.scar_geom))
        from shapely.ops import transform
        g2 = transform(lambda a, b, z=None: BK.transform(*[v + w for v, w in zip(TO.transform(a, b), (dx, dy))]), g)
        row = S.loc[r.Index].copy(); row["lat"], row["lon"] = la, lo; row["scar_geom"] = json.dumps(mapping(g2))
        row["kind"] = "decoy"; row["status"] = "decoy"; dec.append(row); break
S = S.assign(kind="real")
X = pd.concat([S, pd.DataFrame(dec)], ignore_index=True).sample(frac=1, random_state=11).reset_index(drop=True)
X[["src", "event_id", "kind", "status", "age", "scar_ha", "d", "img"]].rename_axis("chip").to_csv(D + "key.csv")
X.drop(columns=["kind", "status"]).to_csv(D + "sample.csv", index=False)
print(len(X), X.kind.value_counts().to_dict(), S.status.value_counts().to_dict())
