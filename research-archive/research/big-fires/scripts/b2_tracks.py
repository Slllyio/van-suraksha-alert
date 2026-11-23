"""Step 2: spread direction between consecutive looks, and what the scar shape says, for the big multi-look fires.

Big fires: scar (v2 union) >= 200 ha, >= 4 VIIRS looks with detections, >= 10 VIIRS alerts on the scar, not cut off at the
12 km chip edge. Smaller multi-look fires (>= 2 looks) are kept as a comparison group.
Coordinates are UTM 43N metres. Every direction test has a simple baseline (random direction, or shuffled look order).
Out: results/steps.csv (one row per look-to-look step), results/fire_shape.csv (one row per fire), printed tables.
"""
import pickle, json
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.spatial import cKDTree

R = '/mnt/project-files/research/big-fires/results'
F = pd.read_csv(f'{R}/fires.csv')
A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t', 'look_t'])
S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
V = A[A.sat != 'modis'].copy()
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
F['multi'] = F.n_looks >= 2
G = np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); TR = G['transform']
UPAZ, SLOPE = G['upslope_az'], G['slope']
def samp(arr, x, y):
    c = int((x - TR[2]) / TR[0]); r = int((y - TR[5]) / TR[4])
    return arr[r, c] if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1] else np.nan
E5 = pd.read_csv('/mnt/project-files/ratapani/ee/era5land_daily.csv', parse_dates=['time']).set_index('time')
rng = np.random.default_rng(0)

def scar_pixels(poly, res=30):
    x0, y0, x1, y1 = poly.bounds
    w, h = int((x1 - x0) / res) + 2, int((y1 - y0) / res) + 2
    tr = from_origin(x0 - res, y1 + res, res, res)
    m = rasterize([(poly, 1)], out_shape=(h + 2, w + 2), transform=tr).astype(bool)
    r, c = np.where(m)
    return tr[2] + (c + 0.5) * res, tr[5] - (r + 0.5) * res

steps, shapes = [], []
for _, f in F[F.multi].iterrows():
    v = V[V.fire == f.fire].sort_values('t')
    if v.look.nunique() < 2: continue
    looks = v.groupby('look').agg(t=('t', 'median'), x=('x', 'mean'), y=('y', 'mean'), n=('x', 'size'),
                                  nsat=('sat', 'nunique'), dn=('daynight', 'first')).sort_values('t').reset_index()
    # position noise inside one look: centroid of one satellite vs another
    noise = []
    for lk, g in v.groupby('look'):
        if g.sat.nunique() >= 2:
            c = g.groupby('sat')[['x', 'y']].mean().values
            noise.append(np.hypot(*(c[0] - c[1])))
    # steps between consecutive looks: (a) centroid to centroid, (b) previous centroid to NEW ground (alerts > 400 m from every earlier alert)
    pts = v[['x', 'y']].values
    for k in range(1, len(looks)):
        a, b = looks.iloc[k - 1], looks.iloc[k]
        earlier = v[v.look.isin(looks.look[:k])][['x', 'y']].values
        cur = v[v.look == b.look][['x', 'y']].values
        dnew = cKDTree(earlier).query(cur)[0]
        new = cur[dnew > 400]
        dt = (b.t - a.t).total_seconds() / 3600
        row = dict(fire=f.fire, big=f.big, k=k, dt_h=dt, dx=b.x - a.x, dy=b.y - a.y, n_new=len(new), n_cur=len(cur),
                   t=b.t, night=b.dn == 'N')
        if len(new):
            row.update(ndx=new[:, 0].mean() - a.x, ndy=new[:, 1].mean() - a.y)
        day = b.t.normalize()
        if day in E5.index:
            row.update(u=E5.loc[day, 'u_component_of_wind_10m'], v=E5.loc[day, 'v_component_of_wind_10m'])
        row.update(upaz=samp(UPAZ, a.x, a.y), slope=samp(SLOPE, a.x, a.y))
        steps.append(row)
    if not f.big and f.area_ha < 50: continue
    # scar shape
    poly = S[f.fire]
    X, Y = scar_pixels(poly)
    cx, cy = X.mean(), Y.mean()
    C = np.cov(np.c_[X - cx, Y - cy].T); ev, evec = np.linalg.eigh(C)
    ax = evec[:, 1]; elong = np.sqrt(ev[1] / max(ev[0], 1e-6))
    # part of the scar more than 600 m from every alert (grown ground, not tied to the 200 m alert circles)
    dall = cKDTree(pts).query(np.c_[X, Y])[0]; far = dall > 600
    far_share = far.mean()
    if far.sum() > 30:
        Cf = np.cov(np.c_[X[far] - X[far].mean(), Y[far] - Y[far].mean()].T); evf, evecf = np.linalg.eigh(Cf)
        axf = evecf[:, 1]
    else:
        axf = np.array([np.nan, np.nan])
    # alert-track axis (first look -> last look) and time gradient along scar axis
    first, last = looks.iloc[0], looks.iloc[-1]
    tv = np.array([last.x - first.x, last.y - first.y]); tlen = np.hypot(*tv)
    proj_a = (v.x - cx) * ax[0] + (v.y - cy) * ax[1]
    rho = spearmanr(v.t.astype('int64'), proj_a)[0] if v.look.nunique() >= 3 else np.nan
    # null: shuffle the order of looks (each look keeps its alerts together)
    null = []
    lk = looks.look.values
    for _ in range(200):
        perm = dict(zip(lk, rng.permutation(len(lk))))
        null.append(abs(spearmanr(v.look.map(perm), proj_a)[0]))
    p_rho = (np.sum(np.array(null) >= abs(rho)) + 1) / 201 if np.isfinite(rho) else np.nan
    # the "forward" direction along the scar axis = where later alerts lie
    fwd = ax * np.sign(rho) if np.isfinite(rho) and rho != 0 else ax
    P = (X - cx) * fwd[0] + (Y - cy) * fwd[1]; Q = -(X - cx) * fwd[1] + (Y - cy) * fwd[0]
    L = P.max() - P.min()
    pos_first = ((first.x - cx) * fwd[0] + (first.y - cy) * fwd[1] - P.min()) / L  # 0 = rear end, 1 = front end
    behind = (P < (first.x - cx) * fwd[0] + (first.y - cy) * fwd[1]).mean()        # scar share behind the first look
    # shape cues read from the outline alone (no alerts): width of each end third, and mass of each end half
    lo, hi = np.quantile(P, [1 / 3, 2 / 3])
    w_rear, w_front = np.std(Q[P <= lo]), np.std(Q[P >= hi])
    mass_skew = ((P - P.mean()) ** 3).mean() / P.std() ** 3   # >0: long thin tail toward the front
    # radial vs one-way: bearings from the first look to every later new-ground alert
    later = v[v.look != first.look]
    d0 = np.hypot(later.x - first.x, later.y - first.y); lv = later[d0 > 400]
    if len(lv) >= 3:
        b = np.arctan2(lv.y - first.y, lv.x - first.x)
        Rlen = np.hypot(np.cos(b).mean(), np.sin(b).mean())
        Rnull = np.median([np.hypot(*np.c_[np.cos(z), np.sin(z)].mean(0)) for z in rng.uniform(0, 2 * np.pi, (500, len(lv)))])
        # group by look so one look's cluster counts once
        bl = lv.groupby('look').apply(lambda g: np.arctan2(g.y.mean() - first.y, g.x.mean() - first.x))
        Rl = np.hypot(np.cos(bl).mean(), np.sin(bl).mean()) if len(bl) >= 2 else np.nan
        Rlnull = np.median([np.hypot(*np.c_[np.cos(z), np.sin(z)].mean(0)) for z in rng.uniform(0, 2 * np.pi, (500, len(bl)))]) if len(bl) >= 2 else np.nan
    else:
        Rlen = Rnull = Rl = Rlnull = np.nan; bl = []
    shapes.append(dict(fire=f.fire, big=f.big, area_ha=f.area_ha, n_viirs=f.n_viirs, n_looks=f.n_looks, hours=f.hours,
                       elong=elong, ax_az=np.degrees(np.arctan2(ax[0], ax[1])) % 180,
                       axf_az=np.degrees(np.arctan2(axf[0], axf[1])) % 180 if np.isfinite(axf[0]) else np.nan,
                       far_share=far_share, track_len=tlen,
                       track_az=np.degrees(np.arctan2(tv[0], tv[1])) % 360 if tlen > 0 else np.nan,
                       rho=rho, p_rho=p_rho, length_m=L, pos_first=pos_first, behind_first=behind,
                       w_rear=w_rear, w_front=w_front, skew=mass_skew, R_alerts=Rlen, R_null=Rnull, n_lv=len(lv),
                       R_looks=Rl, R_looks_null=Rlnull, n_lk=len(bl), noise_med=np.median(noise) if noise else np.nan,
                       fwd_az=np.degrees(np.arctan2(fwd[0], fwd[1])) % 360))
St = pd.DataFrame(steps); Sh = pd.DataFrame(shapes)
St.to_csv(f'{R}/steps.csv', index=False); Sh.to_csv(f'{R}/fire_shape.csv', index=False)
print('steps', len(St), 'fires with shape', len(Sh), 'big', Sh.big.sum())
