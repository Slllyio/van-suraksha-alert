"""All-MP VIIRS fire points (S-NPP, NOAA-20, NOAA-21; standard-processing archive) Jan 1 - Jun 30 of each season, from the
NASA FIRMS area API (bbox 74.0,21.0,82.9,26.9, 5-day requests). Key from env FIRMS_MAP_KEY (never written to files).
Output: /mnt/project-files/fire-alert-scars/alerts_mp/{source}_{year}.csv"""
import os, io, time, sys, pandas as pd, requests
K = os.environ['FIRMS_MAP_KEY']; OUT = '/mnt/project-files/fire-alert-scars/alerts_mp/'; BB = '74.0,21.0,82.9,26.9'
SRC = {'VIIRS_SNPP_SP': ('viirs-snpp', 2014, '2012-01-20'), 'VIIRS_NOAA20_SP': ('viirs-jpss1', 2018, '2018-04-01'), 'VIIRS_NOAA21_SP': ('viirs-noaa21', 2023, '2023-03-01')}
S = requests.Session()
for src, (name, y0, dmin) in SRC.items():
    for Y in range(y0, 2027):
        f = f'{OUT}{name}_{Y}.csv'
        if os.path.exists(f): continue
        parts = []
        for d in pd.date_range(max(pd.Timestamp(f'{Y}-01-01'), pd.Timestamp(dmin)), f'{Y}-06-30', freq='5D'):
            for k in range(5):
                try:
                    r = S.get(f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{K}/{src}/{BB}/5/{d.date()}', timeout=120); r.raise_for_status()
                    if r.text.startswith('Invalid') or 'error' in r.text[:80].lower(): raise RuntimeError(r.text[:120])
                    parts.append(pd.read_csv(io.StringIO(r.text))); break
                except Exception as e:
                    print('  retry', src, d.date(), str(e)[:120].replace(K, '[key]'), flush=True); time.sleep(10 * (k + 1))
            else: raise RuntimeError(f'chunk failed after 5 tries: {src} {d.date()}')
        a = pd.concat(parts, ignore_index=True).drop_duplicates()
        a = a[(a.acq_date >= f'{Y}-01-01') & (a.acq_date <= f'{Y}-06-30')]
        a.to_csv(f, index=False); print(name, Y, len(a), flush=True)
print('FIRMS_MP_DONE')
