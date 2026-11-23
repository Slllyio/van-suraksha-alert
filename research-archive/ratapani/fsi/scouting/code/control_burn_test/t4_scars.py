"""t4: burn-scar shape and line alignment at 20-30 m as independent evidence for the control-burn flag.
Sets: (R) Ratapani scar outlines v2 (2026-10-16), all months 2017-26 incl. Jan-14 Feb; (M) all-MP 15 Feb-15 Jun scars
(tiger-reserve history, MP sample, rest-of-MP history run so far; method v1/v2 mix as listed in fire-alert-scars/mp/README.md).
Links each scar event to our VIIRS burn-day clusters (t1) through its alerts, then measures per scar:
  area_ha; compactness (4 pi A / P^2); aspect (long/short side of the minimum rotated rectangle); core30 = share of area left after a
  30 m inward buffer (strips < 60 m wide -> ~0); beat30 / road30 = share of the outline within 30 m of a beat boundary / Overture road;
  the same two for a decoy copy of the outline moved 2-4 km (chance level).
Output: scratch r21_cb/scar_shapes.parquet; out/scar_shape_by_class.csv; out/scar_lag.csv."""
import numpy as np, pandas as pd, geopandas as gpd, shapely, json, gzip, sys
from shapely import wkb
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
FAS = '/mnt/project-files/fire-alert-scars/'
CRS = 7755
pts = pd.read_parquet(S + 'r15_firms_nd/pts_feat2.parquet', columns=['latitude', 'longitude', 'acq_date', 'acq_time', 'sat', 'cid'])
pts['k'] = pts.acq_date.astype(str) + '_' + pts.acq_time.astype(int).astype(str) + '_' + pts.latitude.round(3).astype(str) + '_' + pts.longitude.round(3).astype(str)
pk = pts.drop_duplicates('k').set_index('k').cid
fl = pd.read_parquet(S + 'r21_cb/cluster_flags.parquet')
cl = pd.read_parquet(S + 'r21_cb/clusters_t1.parquet', columns=['cid', 'n', 'frp_max', 'day_only', 'fday', 'season', 'date', 'fire_ndays'])
cl = cl.merge(fl[['cid', 'grp', 'fn', 'flag_cur', 'flag_live', 'fire_id']], on='cid')


def akey(df, lat='latitude', lon='longitude', date='acq_date', time='acq_time'):
    return df[date].astype(str) + '_' + df[time].astype(float).fillna(-1).astype(int).astype(str) + '_' + df[lat].round(3).astype(str) + '_' + df[lon].round(3).astype(str)


from scipy.spatial import cKDTree
pts['xx'] = np.radians(pts.longitude) * 6371000 * np.cos(np.radians(23.5)); pts['yy'] = np.radians(pts.latitude) * 6371000
pday = {d_: (cKDTree(g[['xx', 'yy']].values), g.cid.values) for d_, g in pts.groupby(pts.acq_date.astype(str))}


def event_cluster(al):
    """alerts (with event_id, key k) -> per event: main cluster = cluster holding most of its VIIRS alerts.
    Exact FIRMS match first; else nearest of our points on the same date within 400 m (2026 Earth Engine centroids)."""
    al = al.assign(cid=al.k.map(pk))
    miss = al.cid.isna()
    if miss.any():
        q = al[miss]; xx = np.radians(q.longitude) * 6371000 * np.cos(np.radians(23.5)); yy = np.radians(q.latitude) * 6371000
        res = np.full(len(q), np.nan)
        for d_, ii in pd.Series(np.arange(len(q))).groupby(q.acq_date.astype(str).values).indices.items():
            if d_ not in pday: continue
            t, cc = pday[d_]; dist, j = t.query(np.c_[xx.values[ii], yy.values[ii]], distance_upper_bound=400)
            ok = np.isfinite(dist); res[ii[ok]] = cc[j[ok]]
        al.loc[miss, 'cid'] = res
    al = al.dropna(subset=['cid'])
    al['cid'] = al.cid.astype(int)
    return al.groupby('event_id').cid.agg(lambda s: s.value_counts().index[0]).rename('cid').reset_index()


# ---------------- Ratapani v2 ----------------
lk = pd.read_csv(FAS + 'reference/v2_2026-10-16/firms_alert_scar_lookup.csv')
lk['k'] = akey(lk)
ecR = event_cluster(lk[lk.sensor != 'modis'])
evR = lk.groupby('event_id').agg(scar_found=('scar_found', 'first'), scar_ha=('scar_ha', 'first'), gap_days=('gap_days', 'first'),
                                 post_date=('post_date', 'first'), acq_date=('acq_date', 'min'), severity=('severity', 'first'),
                                 rdnbr=('rdnbr_median', 'first')).reset_index()
evR = evR.merge(ecR, on='event_id', how='inner'); evR['set'] = 'R'
gR = gpd.read_file(FAS + 'reference/v2_2026-10-16/firms_event_scars.geojson')
print('Ratapani events', len(evR), 'linked of', lk.event_id.nunique(), 'polygons', len(gR), gR.columns.tolist()[:10])
gR = gR[['event_id', 'geometry']]
# ---------------- all-MP 15 Feb-15 Jun ----------------
ae = pd.read_csv(FAS + 'mp/out/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'sensor', 'event_id'])
ae = ae[ae.sensor != 'modis']; ae['k'] = akey(ae)
ecM = event_cluster(ae)
parts = []
h = pd.read_csv(FAS + 'mp/out/scars_mp_hist.csv'); import io, subprocess
# the history geometry file is being appended by the scar thread: copy to scratch, decode what is readable, drop the last line
raw = subprocess.run(f"cp {FAS}mp/out/scars_mp_hist_geom.csv.gz {S}r21_cb/hg.gz; zcat {S}r21_cb/hg.gz 2>/dev/null", shell=True, capture_output=True).stdout
hg = pd.read_csv(io.BytesIO(raw[:raw.rstrip(b'\n').rfind(b'\n')]), on_bad_lines='skip', engine='python')
print('hist geometries readable', len(hg))
parts.append(h.merge(hg, on='event_id', how='left').assign(src='rest-of-MP history'))
parts.append(pd.read_csv(FAS + 'mp/out/scars_tiger_reserves.csv').assign(src='tiger reserves'))
sm = pd.read_csv(FAS + 'mp/out/scars_sample.csv'); parts.append(sm.assign(src='MP sample'))
rr = pd.read_csv(FAS + 'mp/out/scars_rest_of_mp.csv'); parts.append(rr.assign(src='rest-of-MP run'))
M = pd.concat(parts, ignore_index=True).drop_duplicates('event_id')
M = M.merge(ecM, on='event_id', how='inner')
M['scar_found'] = M.status.map({'scar': 'yes', 'scar_faint': 'faint', 'no_scar_seen': 'none_visible'}).fillna('unknown')
M['acq_date'] = pd.to_datetime(M.event_id.str[1:9], format='%Y%m%d').dt.strftime('%Y-%m-%d')
M = M[['event_id', 'scar_found', 'scar_ha', 'gap_days', 'post_date', 'acq_date', 'severity', 'rdnbr_median', 'geometry', 'cid', 'src']].rename(columns={'rdnbr_median': 'rdnbr'})
M['set'] = 'M'
print('MP events linked', len(M), M.src.value_counts().to_dict())
def _parse(g):
    if not isinstance(g, str): return None
    try: return shapely.from_geojson(g) if g.lstrip().startswith('{') else shapely.from_wkt(g)
    except Exception: return None


geomM = M.geometry.where(M.geometry.notna() & (M.geometry.astype(str).str.len() > 10))
gM = gpd.GeoDataFrame(M[['event_id']], geometry=[_parse(g) for g in geomM], crs=4326)
E = pd.concat([evR, M.drop(columns='geometry')], ignore_index=True).merge(cl, on='cid', how='left')
G = pd.concat([gR.assign(set='R'), gM.assign(set='M')], ignore_index=True)
G = gpd.GeoDataFrame(G, geometry='geometry', crs=4326).to_crs(CRS)
G = G[G.geometry.notna() & ~G.geometry.is_empty]
E = E.merge(pd.DataFrame({'event_id': G.event_id, 'set': G.set, 'gidx': np.arange(len(G))}), on=['event_id', 'set'], how='left')
# lag: days from fire to first post image
E['lag_days'] = (pd.to_datetime(E.post_date) - pd.to_datetime(E.acq_date)).dt.days
# ---------------- shape metrics ----------------
geo = G.geometry.values
geo = shapely.make_valid(geo)
A = shapely.area(geo); P = shapely.length(geo)
core = shapely.area(shapely.buffer(geo, -30)) / np.where(A > 0, A, 1)
mrr = shapely.oriented_envelope(geo)


def sides(r):
    cc = np.array(r.exterior.coords) if r.geom_type == 'Polygon' else None
    if cc is None or len(cc) < 4: return np.nan
    a, b = np.hypot(*(cc[1] - cc[0])), np.hypot(*(cc[2] - cc[1]))
    return max(a, b) / max(min(a, b), 20)


asp = np.array([sides(r) for r in mrr])
shp = pd.DataFrame({'gidx': np.arange(len(G)), 'area_ha': A / 1e4, 'compact': 4 * np.pi * A / np.where(P > 0, P, 1) ** 2, 'aspect': asp, 'core30': core})
# lines: beat boundaries and roads
beats = gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson').to_crs(CRS)
bl = shapely.get_parts(shapely.boundary(beats.geometry.values))
bl = bl[~shapely.is_empty(bl)]
import pyarrow.parquet as pq
tb = pq.read_table(S + 'r15_firms_nd/roads_mp.parquet')
rcls = tb.column('class').to_pandas()
keep = ~rcls.isin(['residential', 'footway', 'pedestrian', 'steps', 'cycleway', 'sidewalk', 'crosswalk', 'living_street', 'driveway', 'parking_aisle', 'alley'])
rg = shapely.from_wkb(np.array(tb.column('geometry').to_pylist(), dtype=object)[keep.values])
rg = gpd.GeoSeries(rg, crs=4326).to_crs(CRS).values
del tb


def near_share(lines, geoms, dist=30):
    tree = shapely.STRtree(lines)
    out = np.full(len(geoms), np.nan)
    bnd = shapely.boundary(geoms)
    for i, (gg, bb) in enumerate(zip(geoms, bnd)):
        if gg is None or shapely.is_empty(gg): continue
        idx = tree.query(gg, predicate='dwithin', distance=dist)
        L = shapely.length(bb)
        if len(idx) == 0 or L == 0: out[i] = 0.0; continue
        zone = shapely.buffer(shapely.union_all(lines[idx]), dist)
        out[i] = shapely.length(shapely.intersection(bb, zone)) / L
    return out


rng = np.random.default_rng(4)
ang = rng.uniform(0, 2 * np.pi, len(geo)); dd = rng.uniform(2000, 4000, len(geo))
decoy = np.array([shapely.affinity.translate(gg, xoff=r * np.cos(a), yoff=r * np.sin(a)) for gg, a, r in zip(geo, ang, dd)])
for nm, lines in [('beat30', bl), ('road30', rg)]:
    shp[nm] = near_share(lines, geo); shp[nm + '_decoy'] = near_share(lines, decoy); print(nm, 'done', flush=True)
E = E.merge(shp, on='gidx', how='left')
E.drop(columns=[]).to_parquet(S + 'r21_cb/scar_shapes.parquet')
print(E.groupby(['set', 'fn', 'flag_cur']).size())
