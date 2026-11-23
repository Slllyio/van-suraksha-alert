"""Pull Sentinel-3 SLSTR L2 FRP (EUMETSAT Data Store EO:EUM:DAT:0417) fire pixels over Ratapani.
Credentials come only from env EUM_KEY / EUM_SECRET (never written anywhere).
Out: <out>/slstr_frp_fires.csv (one row per fire pixel in the box) and <out>/slstr_frp_passes.csv (every product that covers the box).
Resumable: products already in the passes file are skipped."""
import os, sys, json, time, zipfile, io, csv, urllib.request, urllib.parse, base64, tempfile, shutil
import h5py, numpy as np, threading
from concurrent.futures import ThreadPoolExecutor
LOCK = threading.Lock()
OUT = sys.argv[1]; Y0, Y1 = int(sys.argv[2]), int(sys.argv[3])
BOX = (77.3, 22.6, 78.4, 23.4)  # lon0, lat0, lon1, lat1 (Ratapani + margin)
API = 'https://api.eumetsat.int'
os.makedirs(OUT, exist_ok=True)
FP, PP = os.path.join(OUT, 'slstr_frp_fires.csv'), os.path.join(OUT, 'slstr_frp_passes.csv')
done = set()
if os.path.exists(PP):
    done = {r['product'] for r in csv.DictReader(open(PP))}
_tok = [None, 0]
def token():
    if time.time() < _tok[1] - 300: return _tok[0]
    a = base64.b64encode((os.environ['EUM_KEY'] + ':' + os.environ['EUM_SECRET']).encode()).decode()
    r = urllib.request.Request(API + '/token', data=b'grant_type=client_credentials', headers={'Authorization': 'Basic ' + a})
    d = json.load(urllib.request.urlopen(r, timeout=60)); _tok[:] = [d['access_token'], time.time() + d['expires_in']]
    return _tok[0]
def get(url, auth=False, tries=4):
    for k in range(tries):
        try:
            h = {'Authorization': 'Bearer ' + token()} if auth else {}
            return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=600).read()
        except Exception as e:
            print('retry', k, str(e)[:120], flush=True); time.sleep(5 * 2 ** k)
    return None
def search(d0, d1):
    out, si = [], 0
    while True:
        q = dict(format='json', pi='EO:EUM:DAT:0417', bbox='%g,%g,%g,%g' % BOX, dtstart=d0, dtend=d1, c=100, si=si)
        d = json.loads(get(API + '/data/search-products/1.0.0/os?' + urllib.parse.urlencode(q)))
        f = d.get('features', []); out += f; si += len(f)
        if not f or si >= d.get('totalResults', 0): return out
COLS = ['time', 'latitude', 'longitude', 'FRP_MWIR', 'FRP_SWIR', 'FRP_uncertainty_MWIR', 'confidence_MWIR', 'classification',
        'IFOV_area', 'sat_zenith', 'solar_zenith', 'n_cloud', 'n_window', 'used_channel']
newf = not os.path.exists(FP); fw = open(FP, 'a', newline=''); wf = csv.writer(fw)
if newf: wf.writerow(['product', 'platform'] + COLS)
newp = not os.path.exists(PP); pw = open(PP, 'a', newline=''); wp = csv.writer(pw)
if newp: wp.writerow(['product', 'start', 'n_fires_box', 'n_fires_product'])
for y in range(Y0, Y1 + 1):
    for m in range(1, 7):
        d0 = '%d-%02d-01T00:00:00Z' % (y, m); d1 = ('%d-%02d-01T00:00:00Z' % (y, m + 1))
        feats = search(d0, d1); print(y, m, len(feats), 'products', flush=True)
        def work(f):
            pid = f['id']
            if pid in done: return
            href = f['properties']['links']['data'][0]['href']
            raw = get(href, auth=True)
            if raw is None or raw[:2] != b'PK': print('fail', pid, flush=True); return
            tmp = tempfile.mkdtemp(dir=OUT)
            try:
                z = zipfile.ZipFile(io.BytesIO(raw)); name = [n for n in z.namelist() if n.endswith('FRP_in.nc') or n.endswith('FRP_MWIR1km_standard.nc')][0]
                p = os.path.join(tmp, 'f.nc'); open(p, 'wb').write(z.read(name))
                h = h5py.File(p, 'r'); lat, lon = h['latitude'][:], h['longitude'][:]
                k = np.where((lon >= BOX[0]) & (lon <= BOX[2]) & (lat >= BOX[1]) & (lat <= BOX[3]))[0]
                alias = {'FRP_uncertainty_MWIR': 'FRP_MWIR_uncertainty'}
                cols = {c: (h[c][:] if c in h else h[alias[c]][:] if (c in alias and alias[c] in h) else np.full(len(lat), np.nan)) for c in COLS}
                rows = [[pid, pid[:3]] + [cols[c][i] for c in COLS] for i in k]; h.close()
                with LOCK:
                    for r in rows: wf.writerow(r)
                    wp.writerow([pid, f['properties']['date'].split('/')[0], len(k), len(lat)]); fw.flush(); pw.flush(); done.add(pid)
            except Exception as e:
                print('parse fail', pid, str(e)[:120], flush=True)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        with ThreadPoolExecutor(8) as ex: list(ex.map(work, feats))
print('DONE', flush=True)
