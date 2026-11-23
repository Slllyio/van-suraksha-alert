"""Widen the ML set (Akkshay 16 Oct 21:06Z): every fire with 3 or more separately timed passes, any sensor, any scar size.
Then test a small neural network against trees, a logistic model and the simple rules, season held out.

Rows.
  PASS STEPS: every pass k >= 2 (S-NPP, NOAA-20, NOAA-21, Terra/Aqua MODIS, Sentinel-2/Landsat hot pixels) whose detections
  include "new burning" = detections more than 400 m from every earlier detection of the fire (any sensor). Direction =
  bearing from the centre of everything seen before to the centre of the new burning. Each step x 8 compass sectors, with
  what lies 300-1500 m out in each sector (same features as sectors_ml.csv; burn history from earlier seasons only).
  FIRE SPEED: Theil-Sen fit of front distance against hours through all passes (3+ passes, span > 3 h).
Models (train on other seasons, test on held-out season): rules, logistic, LightGBM (6 leaves), MLP neural net (2 x 32).
Out: results/ml/all_fires_steps.csv, all_fires_sectors.csv, all_fires_speed.csv, all_fires_nn.json, figures/5_all_fires_nn.png
"""
import json, os, sys
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy.stats import theilslopes, spearmanr
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
sys.path.insert(0, os.path.dirname(__file__)); import feats as FT
R = '/mnt/project-files/research/big-fires/results'; D = f'{R}/ml'; FG = '/mnt/project-files/research/big-fires/figures'
P = pd.read_csv(f'{R}/passes.csv', parse_dates=['t']); DT = pd.read_csv(f'{R}/detections.csv', parse_dates=['t'])
F = pd.read_csv(f'{R}/fires.csv').set_index('fire'); rng = np.random.default_rng(0)
npass = P.groupby('fire').t.nunique(); SELF = npass[npass >= 3].index
print('fires with >=3 timed passes:', len(SELF), '| big among them:', int(F.loc[SELF].eval('area_ha>=200 & n_looks>=4 & n_viirs>=10 & ~still_at_edge').sum()))

def comp(dx, dy): return np.degrees(np.arctan2(dx, dy)) % 360
def season_of(t): return t.year if t.month >= 10 else t.year - 1

steps, sectors, speed = [], [], []
for fid in SELF:
    d = DT[DT.fire == fid].sort_values('t'); p = P[P.fire == fid].sort_values('t'); f = F.loc[fid]
    big = int(f.area_ha >= 200 and f.n_looks >= 4 and f.n_viirs >= 10 and not f.still_at_edge)
    t0 = p.t.min(); season = season_of(t0); year = t0.year if t0.month < 10 else t0.year + 1  # burn raster year = calendar year of the fire season end
    st = d[d.t <= t0 + pd.Timedelta(hours=2)]; ox, oy = st.x.mean(), st.y.mean()
    # --- speed: front distance per pass through all passes
    hrs, front = [], []
    for pid, g in d.groupby('pass_id', sort=False):
        hrs.append((g.t.min() - t0).total_seconds() / 3600); front.append(np.hypot(g.x - ox, g.y - oy).max())
    hrs, front = np.array(hrs), np.array(front); o = np.argsort(hrs); hrs, front = hrs[o], front[o]
    if len(hrs) >= 3 and np.ptp(hrs) > 3:
        s, i, lo, hi = theilslopes(front, hrs)
        w = FT.wx(t0); sx, sy = d.x.values, d.y.values
        speed.append(dict(fire=fid, big=big, season=season, n_passes=len(hrs), span_h=np.ptp(hrs), speed_m_per_h=s, speed_lo=lo, speed_hi=hi, ci_width=hi - lo,
                          area_ha=f.area_ha, n_det=len(d), n_sensors=d.sensor.nunique(), frp_sum=d.frp.sum(), night_share=(d.daynight == 'N').mean(),
                          elev=np.nanmean(FT.s20(FT.ELEV, sx, sy)), slope=np.nanmean(FT.s20(FT.SLOPE, sx, sy)), relief=np.nanpercentile(FT.s20(FT.ELEV, sx, sy), 95) - np.nanpercentile(FT.s20(FT.ELEV, sx, sy), 5),
                          canopy=np.nanmean(FT.s10('canopy', sx, sy)), teak=np.nanmean(FT.s10('teak', sx, sy)), litter_v3=np.nanmean(FT.s10('litter_v3', sx, sy)), grass_v3=np.nanmean(FT.s10('grass_v3', sx, sy)),
                          burn_prior=np.nanmean(np.sum([FT.s20((FT.BURN[y_] > 0).astype(np.float32), sx, sy) for y_ in range(2017, year)], axis=0)) if year > 2017 else 0.0,
                          wc_tree=np.nanmean(FT.s20(FT.WC, sx, sy) == 10), d_building=np.nanmean(FT.cell(sx, sy, 'd_ob')), d_road=np.nanmean(FT.cell(sx, sy, 'dist_road')), doy=t0.dayofyear, **w))
    # --- direction steps, pass by pass
    seen = d.iloc[:0]; prev_b = None; k = 0
    for pid, g in d.groupby('pass_id', sort=False):
        if len(seen):
            dist = cKDTree(seen[['x', 'y']].values).query(g[['x', 'y']].values)[0]; new = g[dist > 400]
            if len(new):
                k += 1; cx, cy = seen.x.mean(), seen.y.mean(); b = comp(new.x.mean() - cx, new.y.mean() - cy)
                gap = (g.t.min() - seen.t.max()).total_seconds() / 3600; w = FT.wx(g.t.min()); night = int((g.daynight == 'N').any())
                upaz = FT.s20(FT.UPAZ, [cx], [cy])[0]
                steps.append(dict(fire=fid, big=big, season=season, k=k, sensor=g.sensor.iloc[0], t=g.t.min(), gap_h=gap, night=night, n_new=len(new), bearing_deg=b, prev_bearing_deg=prev_b,
                                  advance_m=np.hypot(new.x.mean() - cx, new.y.mean() - cy)))
                for sct in range(8):
                    sb = sct * 45; ff = FT.sector_feats(cx, cy, sb, year, g.t.min().dayofyear, seen[['x', 'y']].values)
                    sectors.append(dict(fire=fid, big=big, season=season, k=k, sensor=g.sensor.iloc[0], sector=sct, gap_h=gap, night=night, n_pass_so_far=len(seen.pass_id.unique()),
                                        target_main=int(((sb - b + 180) % 360 - 180).__abs__() <= 22.5), cos_prev=np.cos(np.radians(sb - prev_b)) if prev_b is not None else np.nan,
                                        cos_from_first=np.cos(np.radians(sb - comp(cx - ox, cy - oy))) if np.hypot(cx - ox, cy - oy) > 50 else np.nan,
                                        cos_upslope=np.cos(np.radians(sb - upaz)) if np.isfinite(upaz) else np.nan,
                                        cos_wind=np.cos(np.radians(sb - w['wx_wind_to_deg'])) if w else np.nan, wind_ms=w.get('wx_wind_ms', np.nan), **ff))
                prev_b = b
        seen = pd.concat([seen, g])
ST = pd.DataFrame(steps); SE = pd.DataFrame(sectors); SP = pd.DataFrame(speed)
ST.to_csv(f'{D}/all_fires_steps.csv', index=False); SE.to_csv(f'{D}/all_fires_sectors.csv', index=False); SP.to_csv(f'{D}/all_fires_speed.csv', index=False)
print('steps', len(ST), 'fires', ST.fire.nunique(), '| speed fires', len(SP))
