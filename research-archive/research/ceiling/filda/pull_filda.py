"""FILDA-2 night fire pixels (VNP47IMG S-NPP, VJ147IMG NOAA-20; LP DAAC cloud, 375 m) over MP, season windows.
Usage: python3 pull_filda.py YEAR  -> filda_YEAR.csv (one row per fire pixel). Raw granules are deleted after reading.
Auth: the environment proxy adds the Earthdata header on *.nasa.gov; no credentials here."""
import sys, os, json, urllib.request, h5py, numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor
Y = int(sys.argv[1]); OUT = os.path.dirname(os.path.abspath(__file__)) + f'/filda_{Y}.csv'; TMP = '/tmp/claude-0/filda/raw/'
os.makedirs(TMP, exist_ok=True); BB = '74.0,21.0,82.9,26.9'
COLS = {'VNP47IMG': 'C3365190240-LPCLOUD', 'VJ147IMG': 'C3365180216-LPCLOUD'}
FIELDS = ['FP_Latitude', 'FP_Longitude', 'FP_confidence', 'FP_Power', 'FP_MCE', 'FP_Land_Type', 'FP_Gas_Flaring', 'FP_Status', 'FP_DNB_POS', 'FP_I04_BT', 'FP_I05_BT', 'Sensor_Zenith', 'FP_VEF']
def granules():
    g = []
    for sn, cid in COLS.items():
        page = 1
        while True:
            u = f'https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id={cid}&bounding_box={BB}&temporal={Y}-02-10T00:00:00Z,{Y}-06-01T00:00:00Z&page_size=200&page_num={page}'
            e = json.load(urllib.request.urlopen(u))['feed']['entry']
            for x in e:
                h = [l['href'] for l in x['links'] if l['href'].startswith('https://data.lpdaac') and l['href'].endswith('.nc')]
                if h: g.append((sn, x['title'], h[0]))
            if len(e) < 200: break
            page += 1
    return g
def one(a):
    sn, title, url = a; p = TMP + title + '.nc'
    for k in range(4):
        try:
            urllib.request.urlretrieve(url, p); f = h5py.File(p, 'r'); n = f['FP_Latitude'].shape[0]
            d = pd.DataFrame({c: f[c][:] for c in FIELDS}) if n else pd.DataFrame(columns=FIELDS)
            f.close(); os.remove(p); d['sat'] = sn; d['granule'] = title; return d
        except Exception as ex:
            err = ex
    print('FAIL', title, err, flush=True); return None
if __name__ == '__main__':
    G = granules(); print(Y, 'granules', len(G), flush=True)
    with ThreadPoolExecutor(6) as ex: R = [r for r in ex.map(one, G) if r is not None]
    D = pd.concat(R, ignore_index=True)
    D = D[(D.FP_Longitude >= 74) & (D.FP_Longitude <= 82.9) & (D.FP_Latitude >= 21) & (D.FP_Latitude <= 26.9)]
    D['utc'] = pd.to_datetime(D.granule.str.split('.').str[1:3].str.join('.'), format='A%Y%j.%H%M')
    D.to_csv(OUT, index=False); print('DONE', Y, len(D), 'pixels from', len(R), 'granules', flush=True)
