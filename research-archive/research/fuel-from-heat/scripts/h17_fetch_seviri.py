"""Fetch LSA SAF MSG-IODC FRP-PIXEL lists for given days, keep detections in the MP box. Creds from env LSA_U/LSA_P."""
import os, sys, io, datetime as dt, concurrent.futures as cf
import h5py, numpy as np, pandas as pd, requests
U, P = os.environ['LSA_U'], os.environ['LSA_P']
BASE = 'https://datalsasaf.lsasvcs.ipma.pt/PRODUCTS/MSG-IODC/FRP-PIXEL/HDF5'
OUT = sys.argv[1]; days = [l.strip() for l in open(sys.argv[2]) if l.strip()]
BOX = (21.0, 27.0, 74.0, 83.0)
S = requests.Session(); S.auth = (U, P)
VARS = ['FRP', 'FRP_UNCERTAINTY', 'FIRE_CONFIDENCE', 'PIXEL_SIZE', 'PIXEL_VZA', 'BT_MIR', 'BT_TIR', 'ACQTIME', 'ABS_LINE', 'ABS_PIXEL']
def one(day, hhmm):
    y, m, d = day[:4], day[4:6], day[6:]
    url = f'{BASE}/{y}/{m}/{d}/HDF5_LSASAF_MSG-IODC_FRP-PIXEL-ListProduct_IODC-Disk_{day}{hhmm}'
    for k in range(3):
        try:
            r = S.get(url, timeout=60)
            if r.status_code == 404: return None, 'miss'
            r.raise_for_status(); break
        except Exception as e:
            if k == 2: return None, f'err {e}'
    f = h5py.File(io.BytesIO(r.content))
    if 'LATITUDE' not in f or f['LATITUDE'].shape[0] == 0: return None, 'ok'
    sc = lambda v: f[v][:].astype(float) / f[v].attrs['SCALING_FACTOR']
    lat, lon = sc('LATITUDE'), sc('LONGITUDE')
    k = (lat >= BOX[0]) & (lat <= BOX[1]) & (lon >= BOX[2]) & (lon <= BOX[3])
    if not k.any(): return None, 'ok'
    D = pd.DataFrame({'lat': lat[k], 'lon': lon[k], **{v.lower(): sc(v)[k] for v in VARS if v in f}})
    D['slot'] = pd.Timestamp(f'{day}{hhmm}'); D['sat'] = f.attrs['SATELLITE'][0].decode()
    return D, 'ok'
jobs = [(d, f'{h:02d}{mi:02d}') for d in days for h in range(24) for mi in (0, 15, 30, 45)]
res, stat = [], {}
with cf.ThreadPoolExecutor(24) as ex:
    for D, s in ex.map(lambda j: one(*j), jobs):
        stat[s[:4]] = stat.get(s[:4], 0) + 1
        if D is not None: res.append(D)
out = pd.concat(res) if res else pd.DataFrame()
out.to_csv(OUT, index=False); print(len(jobs), stat, len(out))
