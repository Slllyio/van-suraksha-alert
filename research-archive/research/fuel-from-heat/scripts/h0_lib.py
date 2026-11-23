"""Shared helpers for the fuel-from-heat study (Akkshay 16 Oct 2026 21:00Z: "final scar + detection squares tell which part
is burning and how much; correlate with FRP and brightness; can it give fuel load?").

Physics used throughout
  FRP (MW) is the rate the fire radiates heat. Dry vegetation burnt per unit of radiated energy is ~0.368 kg per MJ
  (Wooster et al. 2005, lab burns; 0.41 +/- 0.04 in later work). So
      fuel burnt (kg)  = 0.368 x FRE (MJ),  FRE = integral of FRP over time
      fuel burnt per area (kg/m2) = 0.368 x FRE / burnt area;  t/ha = 10 x kg/m2
  A satellite sees FRP only at its pass time. Between passes we scale FRP with the burning clock (diurnal fire activity
  from Ratapani MODIS counts, research/fire-continuity/results/diurnal.json).
"""
import json, os, pickle
import numpy as np, pandas as pd, rasterio

ROOT = '/mnt/project-files'
HERE = f'{ROOT}/research/fuel-from-heat'
RES = f'{HERE}/results'
SCRATCH = os.environ.get('FH_SCRATCH', '/tmp/claude-0/-home-user/e474fd2b-d22f-56ab-a442-99e14c5c90d9/scratchpad')
BF = f'{ROOT}/research/big-fires/results'
K_FRE = 0.368          # kg dry matter per MJ radiated
VIIRS = ['S-NPP', 'NOAA-20', 'NOAA-21']

# ---------- burning clock ----------
_p = json.load(open(f'{ROOT}/research/fire-continuity/results/diurnal.json'))
def r_clock(t_utc):
    """Relative fire activity at UTC timestamps (mean over the day = 1)."""
    t = pd.to_datetime(pd.Series(np.atleast_1d(t_utc)))
    ist = (t.dt.hour + t.dt.minute / 60 + 5.5).values % 24
    dh = (ist - _p['peak_ist'] + 12) % 24 - 12
    r = _p['base'] + (1 - _p['base']) * np.exp(-dh ** 2 / (2 * _p['width_h'] ** 2))
    hh = (np.arange(0, 24, 1 / 60) - _p['peak_ist'] + 12) % 24 - 12
    mean = (_p['base'] + (1 - _p['base']) * np.exp(-hh ** 2 / (2 * _p['width_h'] ** 2))).mean()
    return r / mean

def clock_hours(t0, t1):
    """Fire-hours (integral of r_clock) between two UTC timestamps (t1 > t0), 2-minute steps."""
    if t1 <= t0: return 0.0
    n = max(int((t1 - t0).total_seconds() / 120), 1)
    ts = pd.date_range(t0, t1, periods=n + 1)
    return float(np.trapezoid(r_clock(ts), dx=(t1 - t0).total_seconds() / 3600 / n))

# ---------- rasters on the 20 m grid (grid20 = ratapani/spread/data_shared; 10 m rasters sit 100 rows/cols inside) ----------
G20 = np.load(f'{ROOT}/ratapani/spread/data_shared/grid20.npz')
X0, Y0 = G20['transform'][2], G20['transform'][5]
NR, NC = G20['elev'].shape
def rc_of(x, y):
    return np.floor((Y0 - np.asarray(y)) / 20).astype(int), np.floor((np.asarray(x) - X0) / 20).astype(int)

def to20(path, scale=1.0, nod=None):
    """Average a 10 m fuel-map raster onto the 20 m grid. NaN outside."""
    with rasterio.open(path) as r:
        a = r.read(1).astype(float); nd = r.nodata if nod is None else nod
    if nd is not None: a[a == nd] = np.nan
    a = a[: a.shape[0] // 2 * 2, : a.shape[1] // 2 * 2]
    a = np.nanmean(a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2), axis=(1, 3)) * scale
    out = np.full((NR, NC), np.nan); out[100:100 + a.shape[0], 100:100 + a.shape[1]] = a
    return out

def layers():
    f = f'{SCRATCH}/layers20.npz'
    if os.path.exists(f): return dict(np.load(f))
    FM = f'{ROOT}/fuel-map/ratapani'
    L = dict(canopy=to20(f'{FM}/canopy_cover_10m.tif', 0.1),                     # % cover
             litter=to20(f'{FM}/v3/litter_potential_central_10m.tif', 0.01),       # t/ha end-April potential
             grass=to20(f'{FM}/v3/grass_potential_central_10m.tif', 0.01),
             teak=to20(f'{FM}/teak_probability_10m.tif', 1.0),                     # % probability
             slope=G20['slope'].astype(float), elev=G20['elev'].astype(float),
             tree=(G20['wc'] == 10).astype(float))
    np.savez_compressed(f, **L)
    return L

def scars():
    f = f'{SCRATCH}/fire_scars.pkl'
    return pickle.load(open(f, 'rb'))
