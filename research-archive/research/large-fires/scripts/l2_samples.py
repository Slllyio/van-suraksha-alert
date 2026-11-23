"""Step 2. Square-day inputs for every 500 m square of the 87 divisions, issue days 13 Feb-30 May, seasons 2018-25.
Inputs = round-22 B0 set (recent fires, VIIRS history, calendar, HLS dryness, division) + static GIS (terrain, land cover,
roads, villages; static_gis_v1) + NEW scar-history inputs from earlier seasons only (2017 onwards):
  bf_all_r{0,3}: mean yearly burned share of the square (all scar fires), own square / 7x7 box mean (3.5 km)
  bf_big_r{0,3,7}: the same for fires of 200 forest ha or more; bf_b500_r3 for 500 ha or more
  bst_r7: starts of 200 ha+ fires per year in the 15x15 box (7.5 km); n_scar_yrs: earlier scar seasons available.
Labels per issue day t: y_any = VIIRS fire point in the square on t+1 or t+2 (round-22 label, the all-fire list's target);
lsz = biggest scar fire (forest ha) whose first look falls in the square and starts (IST) on t+1 or t+2 (0 = none).
Usage: python l2_samples.py YEAR -> scratch samp_YEAR.parquet (all positives of either label + 1% of the rest, w=100)."""
import sys, pickle, numpy as np, pandas as pd
from scipy.ndimage import uniform_filter
import lf_sr
C, Fe, L = lf_sr.C, lf_sr.Fe, lf_sr.L
QNEG = 0.01
_F = {}


def fires():
    if 'f' not in _F: _F['f'] = pickle.load(open(L.SC + 'fires.pkl', 'rb'))
    return _F['f']


def static():
    s = pd.read_parquet(L.P + 'ratapani/mp_grid/static_gis_v1.parquet')
    assert (s.cell.values == Fe.base()['U']).all()
    return {k: s[k].values.astype(np.float32) for k in s.columns if k not in ('cell', 'row', 'col')}


def scar_hist(y):
    B = Fe.base(); ur, uc = B['ur'], B['uc']
    prior = [p for p in range(max(2017, y - 5), y)]
    A = np.zeros((C.H, C.W), np.float32); BG = np.zeros_like(A); B5 = np.zeros_like(A); BS = np.zeros_like(A)
    for f in fires():
        if f['year'] not in prior: continue
        r, c = f['cells'] // C.W, f['cells'] % C.W; ok = (r < C.H) & (c < C.W)
        np.add.at(A, (r[ok], c[ok]), f['frac'][ok])
        if f['forest_ha'] >= 200:
            np.add.at(BG, (r[ok], c[ok]), f['frac'][ok])
            s = f['start_cells']; BS[s[0] // C.W, s[0] % C.W] += 1
        if f['forest_ha'] >= 500: np.add.at(B5, (r[ok], c[ok]), f['frac'][ok])
    n = max(len(prior), 1); A /= n; BG /= n; B5 /= n; BS /= n
    m = lambda a, r: uniform_filter(a, 2 * r + 1, mode='constant')[ur, uc]
    o = dict(bf_all_r0=A[ur, uc], bf_all_r3=m(A, 3), bf_big_r0=BG[ur, uc], bf_big_r3=m(BG, 3), bf_big_r7=m(BG, 7), bf_b500_r3=m(B5, 3),
             bst_r7=m(BS, 7) * 225, n_scar_yrs=np.full(len(ur), len(prior), np.float32))
    if not prior:
        o = {k: np.full(len(ur), np.nan, np.float32) for k in o}; o['n_scar_yrs'][:] = 0
    return {k: v.astype(np.float32) for k, v in o.items()}


def start_labels(y):
    """dict day -> (ui array, forest_ha array) of scar-fire first-look squares by IST start day."""
    U = Fe.base()['U']; out = {}
    for f in fires():
        if f['year'] != y: continue
        s = f['start_cells']; ii = np.searchsorted(U, s); ok = (ii < len(U)) & (U[np.minimum(ii, len(U) - 1)] == s)
        if ok.any(): out.setdefault(f['start_day'], []).append((ii[ok], np.full(ok.sum(), f['forest_ha'], np.float32)))
    return {d: (np.concatenate([a for a, _ in v]), np.concatenate([b for _, b in v])) for d, v in out.items()}


def iter_season(y, V=None):
    V = C.load_det() if V is None else V
    st = static(); sh = scar_hist(y); lab = start_labels(y); nU = len(Fe.base()['U'])
    for it in Fe.season_iter(y, {}, V, static=st):
        X = np.hstack([it['X'], np.stack([sh[k] for k in sh], 1)]); names = it['names'] + list(sh)
        lsz = np.zeros(nU, np.float32)
        for dd in (1, 2):
            d = it['t'] + pd.Timedelta(days=dd)
            if d in lab:
                ui, ha = lab[d]; np.maximum.at(lsz, ui, ha)
        yield dict(t=it['t'], X=X, names=names, y_any=it['y'], lsz=lsz)


def main(y):
    rng = np.random.default_rng(y); parts = []
    for it in iter_season(y):
        pos = it['y_any'] | (it['lsz'] > 0); keep = pos | (rng.random(len(pos)) < QNEG)
        df = pd.DataFrame(it['X'][keep], columns=it['names'])
        df['y_any'] = it['y_any'][keep]; df['lsz'] = it['lsz'][keep]; df['w'] = np.where(pos[keep], 1.0, 1 / QNEG).astype(np.float32)
        df['ui'] = np.nonzero(keep)[0].astype(np.int32); df['season'] = y; df['doy'] = it['t'].dayofyear
        parts.append(df)
    D = pd.concat(parts, ignore_index=True); D.to_parquet(L.SC + f'samp_{y}.parquet')
    print(y, len(D), 'any', int(D.y_any.sum()), 'starts', int((D.lsz > 0).sum()), '200+', int((D.lsz >= 200).sum()), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))
