"""Where do estimated ignitions sit relative to roads, streams, barrier lines, settlements and the scar edge,
compared with random points inside the same scars?

Usage: python -I dist.py <prepdir> <ign.csv> <out_prefix>
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from shapely import STRtree, points, from_geojson
from shapely.geometry import shape
from rasterio.features import rasterize, geometry_mask
from scipy.ndimage import distance_transform_edt
from scipy.stats import binomtest
import ign

PREP, IGN, OUT = sys.argv[1:4]
SC = "/mnt/project-files/ratapani/fsi/scouting/data/"
BL = "/mnt/project-files/research/ratapani-burn-labels/"
S = pd.read_pickle(PREP + "/scars.pkl")
E = pd.read_csv(IGN)
E = E[E.status == "ok"].copy()
NR = 20
rng = np.random.default_rng(3)

# --- line layers
B = gpd.read_file(SC + "barriers_ratapani.geojson").to_crs(32643)
rows = []
with open(SC + "ms_roads_rata.tsv") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        g = json.loads(parts[-1])["geometry"]
        rows.append(shape(g))
msr = gpd.GeoSeries(rows, crs=4326).to_crs(32643)
LAYERS = {
    "road_any": pd.concat([B[B.cls.str.startswith("road")].geometry, msr], ignore_index=True),
    "road_osm": B[B.cls == "road_osm"].geometry,
    "stream_any": B[B.cls.str.startswith("stream")].geometry,
    "stream_ge1km2": B[B.cls.isin(["stream_dem_1_5km2", "stream_dem_5_25km2", "stream_dem_ge25km2"])].geometry,
    "barrier_any": B.geometry,
    "recurrent_edge": B[B.cls == "recurrent_scar_edge"].geometry,
}
TREES = {k: STRtree(np.asarray(v.values)) for k, v in LAYERS.items()}

# --- raster layers on the 20 m label grid: distance to cropland / built-up (WorldCover), cell id
with rasterio.open(BL + "rasters/burn_2021.tif") as r:
    TR, SH = r.transform, (r.height, r.width)
aoi = gpd.read_file("/mnt/project-files/ratapani/ratapani_aoi.geojson").to_crs(32643)
INSIDE = ~geometry_mask(aoi.geometry, SH, TR)
wc = np.zeros(SH, np.uint8); wc[INSIDE] = np.load(BL + "data/worldcover.npy")
D_CROP = distance_transform_edt(wc != 40) * 20.0
D_BUILT = distance_transform_edt(wc != 50) * 20.0
D_NONFOREST = distance_transform_edt(~np.isin(wc, [40, 50, 60])) * 20.0
grid = gpd.read_file("/mnt/project-files/ratapani/grid_500m.geojson").to_crs(32643)
CELL = rasterize(((g, int(c)) for g, c in zip(grid.geometry, grid.cell_id)), out_shape=SH, transform=TR, fill=-1, dtype="int32")
OB = pd.read_csv(SC + "openbuildings_cell_features.csv").set_index("cell_id")


def rsample(arr, x, y, fill=np.nan):
    col = ((x - TR.c) / TR.a).astype(int); row = ((y - TR.f) / TR.e).astype(int)
    ok = (row >= 0) & (row < SH[0]) & (col >= 0) & (col < SH[1])
    out = np.full(len(x), fill, float); out[ok] = arr[row[ok], col[ok]]
    ok2 = np.zeros(len(x), bool); ok2[ok] = INSIDE[row[ok], col[ok]]
    out[~ok2] = np.nan
    return out


def features(x, y, geoms):
    P = points(x, y)
    f = {}
    for k, t in TREES.items():
        _, dist = t.query_nearest(P, return_distance=True, all_matches=False)
        f["d_" + k] = dist
    f["d_scar_edge"] = np.array([g.boundary.distance(p) for g, p in zip(geoms, P)])
    # outer edge: holes filled, slivers closed by a 60 m close (scars are lacy 20 m pixel maps)
    f["d_outer_edge"] = np.array([OUTER[id(g)].boundary.distance(p) for g, p in zip(geoms, P)])
    f["d_crop"] = rsample(D_CROP, x, y); f["d_built"] = rsample(D_BUILT, x, y)
    f["d_nonforest"] = rsample(D_NONFOREST, x, y)
    cid = rsample(CELL.astype(float), x, y, -1)
    ob = OB.reindex(cid[~np.isnan(cid)].astype(int))
    for c in ["d_ob", "bld4"]:
        v = np.full(len(x), np.nan); v[~np.isnan(cid)] = ob[c].values; f[c] = v
    return pd.DataFrame(f)


OUTER = {}
for g in S.geometry.values:
    OUTER[id(g)] = g.buffer(60).buffer(-60)
    if OUTER[id(g)].is_empty:
        OUTER[id(g)] = g
    if OUTER[id(g)].geom_type == "Polygon":
        from shapely.geometry import Polygon
        OUTER[id(g)] = Polygon(OUTER[id(g)].exterior)
    else:
        from shapely.geometry import Polygon, MultiPolygon
        OUTER[id(g)] = MultiPolygon([Polygon(p.exterior) for p in OUTER[id(g)].geoms])
rec = []
for _, e in E.iterrows():
    g = S.geometry.iloc[int(e.scar)]
    xs, ys, res = ign.candidates(g, 40.0)
    j = rng.choice(len(xs), size=min(NR, len(xs)), replace=len(xs) < NR)
    rec.append(pd.DataFrame(dict(scar=int(e.scar), kind=["e2", "e1", "e0"] + ["rand"] * len(j),
                                 x=np.r_[e.e2_x, e.e1_x, e.e0_x, xs[j]], y=np.r_[e.e2_y, e.e1_y, e.e0_y, ys[j]])))
R = pd.concat(rec, ignore_index=True)
geoms = S.geometry.iloc[R.scar.values].values
F = features(R.x.values, R.y.values, geoms)
R = pd.concat([R, F], axis=1)
R.to_parquet(OUT + "_points.parquet")

meta = E.set_index("scar")
FEATS = [c for c in F.columns]


def summarise(Rs, label):
    out = []
    rnd = Rs[Rs.kind == "rand"].groupby("scar")[FEATS].median()
    rall = Rs[Rs.kind == "rand"]
    for kind in ["e2", "e1", "e0"]:
        k = Rs[Rs.kind == kind].set_index("scar")[FEATS]
        idx = k.index.intersection(rnd.index)
        for c in FEATS:
            a, b = k.loc[idx, c], rnd.loc[idx, c]
            ok = a.notna() & b.notna()
            a, b = a[ok], b[ok]
            if len(a) < 20:
                continue
            closer = int((a < b).sum()); further = int((a > b).sum())
            p = binomtest(closer, closer + further).pvalue if closer + further else np.nan
            out.append(dict(subset=label, est=kind, feature=c, n=len(a), med_est=a.median(), med_rand=b.median(),
                            share_closer=closer / max(closer + further, 1), p_sign=p,
                            share_est_le100=(a <= 100).mean(),
                            share_rand_le100=(rall.loc[rall.scar.isin(a.index), c] <= 100).mean(),
                            share_est_le300=(a <= 300).mean(),
                            share_rand_le300=(rall.loc[rall.scar.isin(a.index), c] <= 300).mean()))
    return out


subsets = {
    "all": meta.index,
    "single_ign_v60": meta.index[meta.n_ign_v60 == 1],
    "well_localised_r90le300": meta.index[meta.e2_r90 <= 300],
    "multi_det_ge3": meta.index[meta.n_det >= 3],
    "forest_only_dnonforest_gt300": None,
}
res = []
for lab, ids in subsets.items():
    if ids is None:
        ok = R[R.kind == "e2"].set_index("scar").d_nonforest
        ids = ok.index[ok > 300]
    res += summarise(R[R.scar.isin(ids)], lab)
T = pd.DataFrame(res)
T.to_csv(OUT + "_summary.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
print(T[(T.est == "e2") & (T.subset != "all")].round(3).to_string())
print(T[(T.subset == "all")].round(3).to_string())
