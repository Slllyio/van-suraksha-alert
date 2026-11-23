"""Layer 1a (cont.): per-detection geometry checks and the "looks" denominator for every square and day.
For every pass in passes.parquet (observed + orbit-predicted), every union square gets its cross-track distance from the
fitted nadir track -> scan angle -> view zenith angle (VZA) and pixel size; a square farther than the swath edge
(scan angle 56.06 deg) is not viewed by that pass.
Per square and IST day (seasons 2014-26, 1 Jan-2 Jun) we store: number of VIIRS views, day views, views at VZA>50,
best (lowest) VZA, and "effective looks" = sum of (375 m x 375 m) / pixel area (a small fire's share of the pixel, the
first-order driver of detection probability).
Checks: along-scan size vs scan angle (aggregation zones), duplicates in one pass (bow-tie / scan overlap), coverage.
Outputs: scratch looks_{season}.npz; out/s2_*.csv; fig1_viirs_geometry.png."""
import numpy as np, pandas as pd, json
from scipy.spatial import cKDTree
import common as C, features as Fe
from s1_passes import ground_dist, th_from_ground, xtrack, HEAD, THMAX, slant, HSAT
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt

if __name__ == '__main__':
    v = pd.read_parquet(C.SC + 'det_geom.parquet')
    v['th_deg'] = np.degrees(v.th)
    # along-scan size by scan angle: empirical median curve (from detections), with aggregation-zone jumps
    bins = np.arange(0, 57, 1.0); v['thb'] = pd.cut(v.th_deg, bins, labels=bins[:-1] + .5)
    sc = v.groupby('thb', observed=True).agg(scan_med=('scan', 'median'), track_med=('track', 'median'), n=('scan', 'size'),
                                              vza=('vza', 'median'))
    sc.to_csv(C.OUT + 's2_pixel_size_by_scan_angle.csv')
    # position-based scan angle (from the pass fit) vs track-based
    th_pos = th_from_ground(v.xt.values); v['th_pos'] = np.degrees(th_pos)
    res = (v.th_pos - v.th_deg).abs()
    print('scan angle from position vs from track size: median |diff| %.2f deg, p90 %.2f' % (res.median(), res.quantile(.9)))
    # duplicates within one pass: two detections of one pass closer than half a pixel along track and along scan
    dup = []
    for pid, g in v[v.type == 0].groupby('pass_id'):
        if len(g) < 2: continue
        h = np.radians(HEAD[g.daynight.iat[0]]); xy = np.c_[g.x.values, g.y.values] / 1000
        al = xy @ np.array([np.sin(h), np.cos(h)]); ac = xy @ np.array([np.cos(h), -np.sin(h)])
        t = cKDTree(np.c_[al, ac]); pr = t.query_pairs(1.0, output_type='ndarray')
        if len(pr) == 0: continue
        i, j = pr[:, 0], pr[:, 1]; tr = g.track.values; scn = g.scan.values
        dal = np.abs(al[i] - al[j]); dac = np.abs(ac[i] - ac[j])
        near = (dal < 0.5 * tr[i]) & (dac < 0.5 * scn[i])
        for k in np.where(near)[0]: dup.append((pid, g.index[i[k]], g.index[j[k]], g.vza.values[i[k]], dal[k], dac[k]))
    D = pd.DataFrame(dup, columns=['pass_id', 'a', 'b', 'vza', 'dal', 'dac'])
    vb = np.arange(0, 75, 5); v0 = v[v.type == 0]
    nd = pd.cut(D.vza, vb).value_counts().sort_index(); nt = pd.cut(v0.vza, vb).value_counts().sort_index()
    dtab = pd.DataFrame(dict(dup_pairs=nd, detections=nt)); dtab['dup_per_1000'] = 1000 * dtab.dup_pairs / dtab.detections
    dtab.to_csv(C.OUT + 's2_duplicates_by_vza.csv'); print(dtab)
    pd.Series(np.unique(D.b.values)).to_frame('det').to_parquet(C.SC + 'dup_det.parquet')
    # looks per square-day
    Pz = pd.read_parquet(C.SC + 'passes.parquet')
    B = Fe.base(); U = B['U']; ur, uc = B['ur'], B['uc']
    x = C.X0 + (uc + .5) * C.S; y = C.Y1 - (ur + .5) * C.S
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(x, y)
    gmax, _ = ground_dist(THMAX)
    sc_curve = sc.scan_med.values; sc_th = sc.index.astype(float).values
    summ = []
    for yr in range(2014, 2027):
        days = pd.date_range(f'{yr}-01-01', f'{yr}-06-02'); di = pd.Series(np.arange(len(days)), index=days)
        Py = Pz[Pz.ld.isin(days)]
        NV = np.zeros((len(days), len(U)), np.uint8); ND = np.zeros_like(NV); NS = np.zeros_like(NV)
        MV = np.full((len(days), len(U)), 99, np.uint8); EF = np.zeros((len(days), len(U)), np.float32)
        for _, p in Py.iterrows():
            d = di[p.ld]; xt = xtrack(lon, lat, p.lon_fit, 23.5, HEAD[p.dn]); th = th_from_ground(xt)
            ok = np.isfinite(th) & (np.abs(xt) <= gmax)
            th = th[ok]; vz = np.degrees(np.arcsin((6371 + HSAT) / 6371 * np.sin(th)))
            trk = 0.375 * slant(th) / HSAT; scn = np.interp(np.degrees(th), sc_th, sc_curve)
            NV[d, ok] += 1; ND[d, ok] += (p.dn == 'D'); NS[d, ok] += (vz > 50)
            MV[d, ok] = np.minimum(MV[d, ok], vz.astype(np.uint8)); EF[d, ok] += 0.375 ** 2 / (trk * scn)
        np.savez_compressed(C.SC + f'looks_{yr}.npz', nv=NV, nd=ND, ns=NS, mv=MV, ef=EF.astype(np.float16))
        m = (days.month * 100 + days.day >= 215) & (days.month <= 5)
        summ.append(dict(season=yr, sats=Py.sat.nunique(), views_per_day=float(NV[m].mean()), day_views=float(ND[m].mean()),
                         slant_share=float(NS[m].sum() / max(1, NV[m].sum())), zero_view_share=float((NV[m] == 0).mean()),
                         eff_per_day=float(EF[m].mean()), best_vza_med=float(np.median(MV[m]))))
        print(summ[-1], flush=True)
    pd.DataFrame(summ).to_csv(C.OUT + 's2_looks_by_season.csv', index=False)
    # figure
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    ax[0].plot(sc.index.astype(float), sc.scan_med, 'o-', ms=3, label='along-scan (FIRMS scan)')
    ax[0].plot(sc.index.astype(float), sc.track_med, 's-', ms=3, label='along-track (FIRMS track)')
    for z in (31.59, 44.68): ax[0].axvline(z, color='grey', ls=':')
    ax[0].set_xlabel('scan angle (deg), from track size'); ax[0].set_ylabel('pixel size (km)'); ax[0].legend(); ax[0].set_title('A. VIIRS pixel grows and jumps at aggregation zones')
    L = np.load(C.SC + 'looks_2024.npz'); days = pd.date_range('2024-01-01', '2024-06-02'); m = (days.month * 100 + days.day >= 215) & (days.month <= 5)
    img = np.full((C.H, C.W), np.nan); img[ur, uc] = (L['ns'][m].sum(0) / np.maximum(1, L['nv'][m].sum(0)))
    im = ax[1].imshow(img, cmap='viridis', vmin=0, vmax=.6); plt.colorbar(im, ax=ax[1], fraction=.04); ax[1].set_title('B. share of 2024 views at VZA > 50 deg'); ax[1].axis('off')
    ax[2].bar(np.arange(len(dtab)), dtab.dup_per_1000.values); ax[2].set_xticks(np.arange(len(dtab))); ax[2].set_xticklabels([str(i.left) for i in dtab.index], rotation=90)
    ax[2].set_xlabel('view zenith angle bin (deg)'); ax[2].set_ylabel('same-pass duplicate pairs per 1000 detections'); ax[2].set_title('C. duplicates in one pass (scan overlap)')
    plt.tight_layout(); plt.savefig(C.OUT + 'fig1_viirs_geometry.png', dpi=110)
    print('DONE')
