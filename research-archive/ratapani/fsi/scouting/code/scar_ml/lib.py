"""Shared code for the burn-scar ML experiment (r16, 16 Oct 2026).
Chip reader (all Sentinel-2 L2A + Landsat 8/9 looks, 4 bands), the current rule re-implemented on the same stack,
two simple baselines, per-pixel features for the learned model, and per-pixel burn dating.
Reading/masking/scaling copies fire-alert-scars/scripts/alert_scar.py (imported, not edited)."""
import os, sys, datetime as dt, numpy as np
from concurrent.futures import ThreadPoolExecutor
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from scipy.ndimage import binary_dilation, label, uniform_filter
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/scripts')
import alert_scar as A  # catalog(), read(), P (rule parameters)

CRS, RES = 'EPSG:32643', 20.0
SCR = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r16_exp_code/'
CODE = '/mnt/project-files/ratapani/fsi/scouting/code/scar_ml/'
B = {'s2': dict(red='B04', nir='B8A', swir1='B11', swir2='B12', qa='SCL'),
     'ls': dict(red='red', nir='nir08', swir1='swir16', swir2='swir22', qa='qa_pixel')}
S2_TO_LS = dict(red=1.0, nir=0.955, swir1=0.91, swir2=0.88)  # red factor 1.0 is an assumption
BANDS = ('red', 'nir', 'swir1', 'swir2')


def chip_grid(x, y, half_m=1500.0):
    x0, y1 = np.floor((x - half_m) / RES) * RES, np.ceil((y + half_m) / RES) * RES
    n = int(2 * half_m / RES)
    return rasterio.transform.from_origin(x0, y1, RES, RES), n


def look(items, s, tr, n):
    b = B[s]; out = np.full((4, n, n), np.nan, np.float32); filled = np.zeros((n, n), bool)
    for it in items:
        qa = A.read(it.assets[b['qa']].href, tr, n, Resampling.nearest)
        if s == 's2':
            ok = np.isin(qa, [2, 3, 4, 5, 6, 7]) & ~binary_dilation(np.isin(qa, [8, 9, 10]), iterations=25)
        else:
            cl = (qa & (1 << 1) > 0) | (qa & (1 << 3) > 0) | (qa & (1 << 4) > 0)
            ok = (qa > 0) & (qa & 1 == 0) & ~binary_dilation(cl, iterations=17)
        ok &= ~filled
        if not ok.any():
            continue
        r = {}
        for k in BANDS:
            a = A.read(it.assets[b[k]].href, tr, n, Resampling.bilinear).astype(np.float32)
            if s == 's2':
                off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
                r[k] = (a - off) / 10000.0 * S2_TO_LS[k]
            else:
                r[k] = a * 0.0000275 - 0.2
        ok &= (r['nir'] + r['swir2']) > 0.02
        for i, k in enumerate(BANDS):
            out[i][ok] = r[k][ok]
        filled |= ok
    return out


def read_stack(x, y, date, half_m=1500.0, before=30, after=40):
    """All looks (one per date+sensor) of a chip around (x, y) from date-before to date+after."""
    from pyproj import Transformer
    tr, n = chip_grid(x, y, half_m)
    d = dt.date.fromisoformat(str(date)[:10])
    bbox = Transformer.from_crs(CRS, 'EPSG:4326', always_xy=True).transform_bounds(tr.c, tr.f - n * RES, tr.c + n * RES, tr.f)
    groups = {}
    for col, s in (('sentinel-2-l2a', 's2'), ('landsat-c2-l2', 'ls')):
        q = {'eo:cloud_cover': {'lt': 80}}
        if s == 'ls':
            q['platform'] = {'in': ['landsat-8', 'landsat-9']}
        for it in A.catalog().search(collections=[col], bbox=bbox, datetime=f'{d - dt.timedelta(before)}/{d + dt.timedelta(after)}', query=q).items():
            groups.setdefault((it.datetime.date(), s), []).append(it)
    keys = sorted(groups)
    with ThreadPoolExecutor(8) as ex:
        arr = list(ex.map(lambda k: look(groups[k], k[1], tr, n), keys))
    keep = [i for i, a in enumerate(arr) if np.isfinite(a[1]).mean() > 0.02]
    return dict(dates=np.array([keys[i][0].isoformat() for i in keep]), sensors=np.array([keys[i][1] for i in keep]),
                X=np.stack([arr[i] for i in keep]).astype(np.float16) if keep else np.zeros((0, 4, n, n), np.float16),
                tr=np.array(tr)[:6], n=n, x=x, y=y, date=str(date)[:10])


# ---------------------------------------------------------------- indices
def idx(L):
    """L: (4, n, n) red, nir, swir1, swir2 -> dict of bands + indices."""
    red, nir, s1, s2 = [L[i].astype(np.float32) for i in range(4)]
    with np.errstate(divide='ignore', invalid='ignore'):
        return dict(red=red, nir=nir, swir1=s1, swir2=s2, nbr=(nir - s2) / (nir + s2), nbr2=(s1 - s2) / (s1 + s2),
                    mirbi=10 * s2 - 9.8 * s1 + 2, ndvi=(nir - red) / (nir + red))


def best_looks(st, exclude_dates=()):
    """One look per date (clearer one), optionally excluding dates (e.g. the scene used as truth)."""
    ex = set(str(e) for e in exclude_dates); best = {}
    for i, (d, s) in enumerate(zip(st['dates'], st['sensors'])):
        if d in ex:
            continue
        c = np.isfinite(st['X'][i, 1].astype(np.float32)).mean()
        if d not in best or c > best[d][1]:
            best[d] = (i, c)
    ds = sorted(best)
    return ds, [best[d][0] for d in ds]


def centre_disk(n, r_m=300.0):
    yy, xx = np.mgrid[0:n, 0:n]; c = n / 2 - 0.5
    return (xx - c) ** 2 + (yy - c) ** 2 <= (r_m / RES) ** 2


def pick_pair(st, exclude_dates=(), clear=0.7, region=None):
    """pre = last clear look on/before the anchor date, post = first clear after, check = next clear within 25 d."""
    d = dt.date.fromisoformat(st['date']); ds, ii = best_looks(st, exclude_dates)
    n = st['n']; reg = centre_disk(n) if region is None else region
    cl = {dd: np.isfinite(st['X'][i, 1].astype(np.float32))[reg].mean() for dd, i in zip(ds, ii)}
    good = [dd for dd in ds if cl[dd] >= clear]
    pre = [t for t in good if dt.date.fromisoformat(t) <= d and (d - dt.date.fromisoformat(t)).days <= 30]
    post = [t for t in good if dt.date.fromisoformat(t) > d]
    if not pre or not post:
        return None
    t0, t1 = pre[-1], post[0]
    later = [t for t in good if t > t1 and (dt.date.fromisoformat(t) - dt.date.fromisoformat(t1)).days <= 25]
    m = dict(zip(ds, ii))
    return dict(pre=str(t0), post=str(t1), check=str(later[0]) if later else None, i0=m[t0], i1=m[t1], i2=m[later[0]] if later else None)


def rel(x, ok):
    return x - np.nanmedian(x[ok]) if ok.sum() > 200 else np.full_like(x, np.nan)


def patches(mask, min_ha=0.5):
    lab, _ = label(mask, structure=np.ones((3, 3))); s = np.bincount(lab.ravel())
    big = np.where(s * RES * RES / 1e4 >= min_ha)[0]; big = big[big > 0]
    return np.isin(lab, big), lab


# ---------------------------------------------------------------- rule (re-implemented on the stack) and baselines
def rule_parts(st, pair, month):
    P = A.P; X = st['X']
    a0, a1 = idx(X[pair['i0']]), idx(X[pair['i1']])
    ok = np.isfinite(a0['nbr']) & np.isfinite(a1['nbr'])
    rdn = rel(a0['nbr'] - a1['nbr'], ok); rdr = rel(a0['nir'] - a1['nir'], ok)
    thr = P['dnbr_jan'] if month == 1 else P['dnbr']
    burn = ok & (rdn >= thr) & (rdr >= P['dnir'])
    ok2 = np.zeros_like(ok); rdf = np.zeros_like(rdn)
    if pair['i2'] is not None:
        a2 = idx(X[pair['i2']]); ok2 = np.isfinite(a0['nbr']) & np.isfinite(a2['nbr'])
        rdf = rel(a0['nbr'] - a2['nbr'], ok2); burn &= ~ok2 | (rdf >= P['persist'])
    return dict(ok=ok, ok2=ok2, rdn=np.nan_to_num(rdn, nan=-9), rdr=np.nan_to_num(rdr, nan=-9), rdf=np.nan_to_num(rdf, nan=-9), burn=burn,
                dnbr=np.nan_to_num(a0['nbr'] - a1['nbr'], nan=-9))


def rule_v2(parts, disk, grow_to_check=True):
    """The current rule: pass 1 core patches touching an alert disk, pass 2 growth, growth to the check look, faint fallback.
    Returns (scar mask, core mask, status)."""
    P = A.P; ok, ok2, rdn, rdr, rdf, burn = (parts[k] for k in ('ok', 'ok2', 'rdn', 'rdr', 'rdf', 'burn'))
    lab, _ = label(burn, structure=np.ones((3, 3))); s = np.bincount(lab.ravel())
    big = np.where(s * RES * RES / 1e4 >= P['min_ha'])[0]; big = big[big > 0]
    hit = np.intersect1d(np.unique(lab[disk]), big)
    if len(hit):
        core = np.isin(lab, hit)
        thr2 = max(P['grow_min'], P['grow_frac'] * float(np.median(rdn[core])))
        grow = ok & (rdn >= thr2) & (rdr >= 0) & (~ok2 | (rdf >= thr2 / 2)) | core
        glab, _ = label(grow, structure=np.ones((3, 3))); m = np.isin(glab, np.unique(glab[core]))
        if grow_to_check and ok2.any():
            g2 = ok2 & (rdf >= thr2) | m
            g2lab, _ = label(g2, structure=np.ones((3, 3))); m = np.isin(g2lab, np.unique(g2lab[m]))
        return m, core, 'scar'
    faint = ok & (rdn >= P['faint']) & (rdr >= 0) & (~ok2 | (rdf >= P['faint_persist']))
    flab, _ = label(faint, structure=np.ones((3, 3))); fs = np.bincount(flab.ravel())
    fbig = np.where(fs * RES * RES / 1e4 >= P['faint_ha'])[0]
    hit = np.intersect1d(np.unique(flab[disk]), fbig[fbig > 0])
    if len(hit):
        return np.isin(flab, hit), np.zeros_like(ok), 'scar_faint'
    return np.zeros_like(ok), np.zeros_like(ok), 'none'


def base_abs(parts):
    """Baseline 1: plain NBR drop pre->post >= 0.10, patches >= 0.5 ha, no alert tie."""
    return patches(parts['ok'] & (parts['dnbr'] >= 0.10))[0]


def base_nocircle(parts):
    """Baseline 2: the rule's pass-1 test (chip-relative drop, NIR, persistence) everywhere, no alert tie, no growth."""
    return patches(parts['burn'])[0]


def alert_disk(n, tr, xs, ys, radii):
    yy, xx = np.mgrid[0:n, 0:n]; disk = np.zeros((n, n), bool)
    for x, y, r in zip(xs, ys, radii):
        cx, cy = (x - tr[2]) / RES - 0.5, (tr[5] - y) / RES - 0.5
        if -40 < cx < n + 40 and -40 < cy < n + 40:
            disk |= (xx - cx) ** 2 + (yy - cy) ** 2 <= (r / RES) ** 2
    return disk


# ---------------------------------------------------------------- learned model features
FEATS = None


def features(st, pair, parts, static=None):
    X = st['X']; a0, a1 = idx(X[pair['i0']]), idx(X[pair['i1']])
    a2 = idx(X[pair['i2']]) if pair['i2'] is not None else {k: np.full_like(v, np.nan) for k, v in a1.items()}
    ok = parts['ok']; f = {}
    for k in a0:
        f[f'pre_{k}'] = a0[k]; f[f'post_{k}'] = a1[k]; f[f'chk_{k}'] = a2[k]
        f[f'd_{k}'] = a0[k] - a1[k]; f[f'd2_{k}'] = a0[k] - a2[k]
        f[f'rd_{k}'] = rel(a0[k] - a1[k], ok); f[f'rd2_{k}'] = rel(a0[k] - a2[k], ok)
        f[f'rr_{k}'] = (a0[k] - a1[k]) / (np.abs(a0[k]) + 0.05)
    for k in ('d_nbr', 'rd_nbr', 'd_nbr2', 'd_mirbi', 'rd2_nbr'):
        v = np.nan_to_num(f[k], nan=0.0)
        for w in (3, 7):
            m = uniform_filter(v, w); f[f'{k}_m{w}'] = m
            f[f'{k}_s{w}'] = np.sqrt(np.maximum(uniform_filter(v * v, w) - m * m, 0))
        f[f'{k}_x7'] = v - f[f'{k}_m7']
    d0, d1 = dt.date.fromisoformat(pair['pre']), dt.date.fromisoformat(pair['post'])
    n = st['n']
    f['gap_days'] = np.full((n, n), (d1 - d0).days, np.float32)
    f['chk_days'] = np.full((n, n), (dt.date.fromisoformat(pair['check']) - d1).days if pair['check'] else np.nan, np.float32)
    f['doy'] = np.full((n, n), d1.timetuple().tm_yday, np.float32)
    sen = {d: s for d, s in zip(st['dates'], st['sensors'])}
    f['post_is_s2'] = np.full((n, n), float(st['sensors'][pair['i1']] == 's2'), np.float32)
    f['pre_is_s2'] = np.full((n, n), float(st['sensors'][pair['i0']] == 's2'), np.float32)
    if static is not None:
        f.update(static)
    return f


def static_layers(tr, n):
    """Slope, WorldCover class (grid20.npz) and FSI-style canopy cover (fuel-map/ratapani/canopy_cover_10m.tif) on the chip grid."""
    G = _grid20(); T = G['transform']
    c0 = int(round((tr[2] - T[2]) / RES)); r0 = int(round((T[5] - tr[5]) / RES))
    out = {}
    for k in ('slope', 'wc'):
        a = np.full((n, n), np.nan, np.float32); src = G[k]
        rs, cs = slice(max(r0, 0), min(r0 + n, src.shape[0])), slice(max(c0, 0), min(c0 + n, src.shape[1]))
        if rs.start < rs.stop and cs.start < cs.stop:
            a[rs.start - r0:rs.stop - r0, cs.start - c0:cs.stop - c0] = src[rs, cs]
        out[k] = a
    try:
        with rasterio.open('/mnt/project-files/fuel-map/ratapani/canopy_cover_10m.tif') as s, \
                WarpedVRT(s, crs=CRS, transform=rasterio.Affine(*tr), width=n, height=n, resampling=Resampling.average) as v:
            cc = v.read(1).astype(np.float32); nd = s.nodata
            if nd is not None:
                cc[cc == nd] = np.nan
            out['canopy'] = cc
    except Exception:
        out['canopy'] = np.full((n, n), np.nan, np.float32)
    return out


_G = None


def _grid20():
    global _G
    if _G is None:
        z = np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); _G = {k: z[k] for k in ('slope', 'wc', 'transform')}
    return _G


# ---------------------------------------------------------------- per-pixel burn dating
def burn_dates(st, burned, exclude_dates=(), thr=0.08, keep=0.6):
    """For each burned pixel: first look whose chip-relative NBR sits >= thr below the pixel's own recent baseline
    (median of its last 3 clear looks) and stays >= keep*thr below at the next clear look.
    Returns (U, L) as day numbers (ordinal): burned in (L, U]; NaN if no such look."""
    ds, ii = best_looks(st, exclude_dates)
    if len(ds) < 3:
        n = st['n']; return np.full((n, n), np.nan), np.full((n, n), np.nan)
    nb = []
    for i in ii:
        a = idx(st['X'][i]); v = a['nbr']; okk = np.isfinite(v)
        nb.append(v - np.nanmedian(v[okk]) if okk.sum() > 200 else np.full_like(v, np.nan))
    nb = np.stack(nb)  # (T, n, n)
    T = len(ds); days = np.array([dt.date.fromisoformat(d).toordinal() for d in ds], float)
    n = st['n']; U = np.full((n, n), np.nan); L = np.full((n, n), np.nan)
    rr, cc = np.where(burned)
    S = nb[:, rr, cc]  # (T, m)
    fin = np.isfinite(S)
    o = np.argsort(~fin, axis=0, kind='stable')          # finite looks first, in time order
    V = np.take_along_axis(S, o, 0); Dd = days[o]; cnt = fin.sum(0)
    m = S.shape[1]; found = np.zeros(m, bool); u = np.full(m, np.nan); l = np.full(m, np.nan)
    for k in range(1, T):
        base = np.nanmedian(V[max(0, k - 3):k], axis=0)
        nxt = V[k + 1] if k + 1 < T else np.full(m, np.nan)
        hit = (~found) & (k < cnt) & (cnt >= 3) & (base - V[k] >= thr) & ((k + 1 >= cnt) | (base - nxt >= keep * thr))
        u[hit] = Dd[k, hit]; l[hit] = Dd[k - 1, hit]; found |= hit
    U[rr, cc] = u; L[rr, cc] = l
    return U, L


# ---------------------------------------------------------------- FIRMS alerts and per-chip pipeline
_AL = None


def alerts():
    """All raw FIRMS alerts (Ratapani bbox + 2 km): x, y, date, sensor, radius used by the rule."""
    global _AL
    if _AL is None:
        import glob, pandas as pd
        from pyproj import Transformer
        TO = Transformer.from_crs(4326, 32643, always_xy=True); al = []
        for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/*.csv'):
            if 'latitude' not in open(f).readline():
                continue
            a = pd.read_csv(f, usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'scan', 'track'])
            a['sensor'] = os.path.basename(f).split('_')[0]; al.append(a)
        a = pd.concat(al, ignore_index=True)
        a['d'] = pd.to_datetime(a.acq_date); a['x'], a['y'] = TO.transform(a.longitude.values, a.latitude.values)
        a['viirs'] = a.sensor.str.startswith('viirs')
        a['radius'] = np.where(a.viirs, 200.0, 600.0 * np.sqrt(np.maximum(np.maximum(a.scan.fillna(1), a.track.fillna(1)), 1)))
        _AL = a.drop_duplicates(['latitude', 'longitude', 'acq_date', 'acq_time', 'sensor'])
    return _AL


def chip_alerts(st, d0, d1, pad_m=500):
    """Alerts inside the chip (+pad) dated d0 <= date <= d1."""
    import pandas as pd
    a = alerts(); tr = st['tr']; n = st['n']
    x0, y1 = tr[2], tr[5]; x1, y0 = x0 + n * RES, y1 - n * RES
    return a[(a.x > x0 - pad_m) & (a.x < x1 + pad_m) & (a.y > y0 - pad_m) & (a.y < y1 + pad_m) &
             (a.d >= pd.Timestamp(str(d0))) & (a.d <= pd.Timestamp(str(d1)))]


def load_stack(chip):
    z = np.load(f'{SCR}stacks/{chip}.npz', allow_pickle=False)
    st = {k: z[k] for k in z.files}
    st['n'] = int(st['n']); st['date'] = str(st['date']); st['tr'] = np.asarray(st['tr'], float)
    st['dates'] = np.array([str(d) for d in st['dates']]); st['sensors'] = np.array([str(s) for s in st['sensors']])
    return st


def prepare(chip_row, exclude_dates=(), pretend_centre=False):
    """Stack -> pair, rule parts, alert disk, rule mask/core, baselines. pretend_centre: also put a VIIRS disk at the
    chip centre (decoys / controls: 'what would the rule draw if an alert sat here')."""
    import pandas as pd
    st = load_stack(chip_row['chip'])
    if len(st['dates']) < 2:
        return None
    pair = pick_pair(st, exclude_dates)
    if pair is None:
        return None
    month = dt.date.fromisoformat(st['date']).month
    parts = rule_parts(st, pair, month)
    a = chip_alerts(st, pair['pre'], (dt.date.fromisoformat(pair['post']) - dt.timedelta(1)).isoformat())
    n = st['n']; tr = st['tr']
    disk = alert_disk(n, tr, a.x.values, a.y.values, a.radius.values)
    if pretend_centre:
        disk = alert_disk(n, tr, [chip_row['x']], [chip_row['y']], [200.0])
    rule, core, status = rule_v2(parts, disk)
    return dict(st=st, pair=pair, parts=parts, disk=disk, rule=rule, core=core, rule_status=status,
                b_abs=base_abs(parts), b_nc=base_nocircle(parts), n_alerts=len(a))
