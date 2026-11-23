"""Build the per-scar ignition table and compare it with the crude 'new ignition' rule.

Usage: python -I final.py <prepdir> <ign_all.csv> <out.csv>
"""
import sys
import numpy as np, pandas as pd, geopandas as gpd
from pyproj import Transformer
from scipy.spatial import cKDTree

PREP, IGN, OUT = sys.argv[1:4]
R = "/mnt/project-files/fire-alert-scars/"
BACK = Transformer.from_crs(32643, 4326, always_xy=True)
S = pd.read_pickle(PREP + "/scars.pkl")
E = pd.read_csv(IGN)
D = pd.read_pickle(PREP + "/dets.pkl")
EP = pd.Timestamp(0, tz="UTC")
D["th"] = (D.t - EP) / pd.Timedelta(hours=1)
sp = pd.read_csv(R + "out/event_scars_split.csv", usecols=["event_id", "share_kept", "n_rival_fires"])
E = E.merge(S[["event_id", "scar_ha", "date", "pre_date", "post_date", "n_alerts"]], on="event_id", how="left")
E = E.merge(sp, on="event_id", how="left")


def ist(h):
    return (pd.to_datetime(h * 3600, unit="s", utc=True) + pd.Timedelta(hours=5.5)).dt.strftime("%Y-%m-%d %H:%M")


ok = E.status == "ok"
for k in ["e2", "e1", "e0"]:
    lon, lat = BACK.transform(E[k + "_x"].values, E[k + "_y"].values)
    E[k + "_lat"], E[k + "_lon"] = np.round(lat, 5), np.round(lon, 5)
for c in ["t_first", "t_ign_med", "t_ign_05", "t_ign_95", "t_lo_soft"]:
    E[c + "_ist"] = np.where(ok, ist(E[c].fillna(0)), "")

# merged flag
kin = E.n_ign_v60.fillna(1) >= 2
resid = (E.max_resid_h.fillna(0) > 3) & (E.n_resid_gt2h.fillna(0) >= 2)
rival = E.share_kept.fillna(1) < 0.9
E["merge_evidence"] = (kin.astype(int).astype(str) + resid.astype(int).astype(str) + rival.astype(int).astype(str))
nev = kin.astype(int) + resid.astype(int) + rival.astype(int)
E["ignitions_flag"] = np.select([~ok, nev == 0, nev == 1], ["no_detection", "likely_single", "possibly_merged"],
                                "likely_merged")

# same fire across events: scars of different events that overlap and whose earliest detection is the same
Sg = gpd.GeoDataFrame(E[["event_id"]].merge(S[["event_id", "geometry"]], on="event_id"), crs=32643)
J = gpd.sjoin(Sg, Sg, predicate="intersects")
J = J[J.index != J.index_right]
par = np.arange(len(Sg))
def find(i):
    while par[i] != i:
        par[i] = par[par[i]]; i = par[i]
    return i
tf = E.t_first.values
for a, b in zip(J.index.values, J.index_right.values):
    if np.isfinite(tf[a]) and np.isfinite(tf[b]) and abs(tf[a] - tf[b]) < 0.01:
        ia, ib = find(a), find(b)
        if ia != ib:
            par[ia] = ib
E["fire_group"] = [f"G{find(i):05d}" for i in range(len(E))]
E["n_events_in_group"] = E.groupby("fire_group").event_id.transform("size")

# event role: is the event's own day the day the fire was first seen?
ev_day = pd.to_datetime(E.date)
first_day = pd.to_datetime(E.t_first.fillna(0) * 3600, unit="s").dt.normalize()  # UTC date, like the event date
E["event_role"] = np.select([~ok, first_day >= ev_day, first_day < ev_day],
                            ["unknown", "first_day_of_fire", "later_day_of_fire"], "unknown")

# crude rule used by the 2-day threads: no FIRMS detection within 1 km in the previous 7 days -> new ignition
F = D[D.src == "firms"].reset_index(drop=True)
tree = cKDTree(np.c_[F.x, F.y])
# evaluated at the event's own alert point and earliest alert time (what the threads see on the day)
Lk = pd.read_csv(R + "alert_scar_lookup.csv", usecols=["event_id", "acq_date", "acq_time"], dtype={"acq_time": str})
Lk = Lk[Lk.acq_time.notna()]
Lk["th"] = (pd.to_datetime(Lk.acq_date + " " + Lk.acq_time.str.zfill(4).str[:2] + ":" + Lk.acq_time.str.zfill(4).str[2:],
                           utc=True) - EP) / pd.Timedelta(hours=1)
ev_t = Lk.groupby("event_id").th.min()
ex, ey = Transformer.from_crs(4326, 32643, always_xy=True).transform(
    S.set_index("event_id").reindex(E.event_id).lon.values, S.set_index("event_id").reindex(E.event_id).lat.values)
E["ev_x"], E["ev_y"], E["ev_t"] = ex, ey, E.event_id.map(ev_t).values
crude = []
for _, e in E.iterrows():
    if e.status != "ok" or not np.isfinite(e.ev_t):
        crude.append(np.nan); continue
    x, y, t = e.ev_x, e.ev_y, e.ev_t
    idx = tree.query_ball_point([x, y], 1000.0)
    th = F.th.values[idx]
    crude.append(int(not ((th < t - 1.0) & (th >= t - 7 * 24)).any()))
E["crude_rule_new"] = crude

cols = ["event_id", "fire_group", "n_events_in_group", "event_role", "date", "pre_date", "post_date", "scar_ha",
        "n_det", "n_firms", "n_af", "first_src", "first_sensor", "n_first", "n_days",
        "t_first_ist", "t_ign_med_ist", "t_ign_05_ist", "t_ign_95_ist", "t_lo_soft_ist",
        "e2_lat", "e2_lon", "e2_r50", "e2_r90", "p_in_first_fp",
        "e1_lat", "e1_lon", "e1_r", "e1_area_ha", "e0_lat", "e0_lon", "v_med",
        "max_resid_h", "n_resid_gt2h", "n_ign_v60", "n_ign_v150", "share_kept", "n_rival_fires",
        "merge_evidence", "ignitions_flag", "crude_rule_new", "status"]
T = E[cols].rename(columns={"e2_lat": "ign_lat", "e2_lon": "ign_lon", "e2_r50": "ign_r50_m", "e2_r90": "ign_r90_m",
                            "e1_r": "fp_r_m", "e1_lat": "fp_lat", "e1_lon": "fp_lon", "e1_area_ha": "fp_area_ha",
                            "e0_lat": "first_det_lat", "e0_lon": "first_det_lon", "v_med": "v_med_m_per_burn_h",
                            "share_kept": "split_share_kept"})
# R90 is over-confident: 73% coverage in the synthetic test, 40% for the real fire-pixel proxy. Inflate by 2.8
# (synthetic 90%-coverage factors 2.4-3.2).
T.insert(T.columns.get_loc("ign_r90_m") + 1, "ign_r90_cal_m", (2.8 * T.ign_r90_m.clip(lower=40)).round(0))
for c in ["ign_r50_m", "ign_r90_m", "fp_r_m", "p_in_first_fp", "max_resid_h", "fp_area_ha"]:
    T[c] = T[c].round(2 if c in ("p_in_first_fp", "fp_area_ha") else 0)
T.to_csv(OUT, index=False)
o = T[T.status == "ok"]
print(len(T), "rows;", o.ignitions_flag.value_counts().to_dict())
print("merge evidence (kin,resid,rival):", o.merge_evidence.value_counts().to_dict())
print("event role:", o.event_role.value_counts().to_dict(), "groups:", o.fire_group.nunique())
print("crude rule new:", o.crude_rule_new.mean().round(3))
print(pd.crosstab(o.event_role, o.crude_rule_new, margins=True))
