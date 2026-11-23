"""Step 8. The PC's real daily-rule models on 2025 (the one season they were not trained on), rebuilt in the cloud with
field-system/pc_models (exact PC feature builder + the 87 live models) and the live-alerts thread's cloud inputs
(pc_models/cloud_series: GFS, ERA5 soil moisture (PC used ERA5-Land), MODIS from Planetary Computer; HLS mp_dry_2025.npz;
fire_celldays). Raw model score per square and issue day 13 Feb-30 May 2025 -> scratch cube_PC_2025.npy on this study's
square list U, so l5_score.py scores it exactly like the other models (top q% per division).
Usage: python l8_pc2025.py run [workers]; python l8_pc2025.py cube"""
import sys, os, json, lzma, time
import numpy as np, pandas as pd
import lf_common as L
PM = L.P + 'field-system/pc_models/'
sys.path.insert(0, PM); sys.path.insert(0, L.P + 'field-system')
OUTD = L.SC + 'pc2025/'; os.makedirs(OUTD, exist_ok=True)
DAYS = pd.date_range('2025-02-13', '2025-05-30')


def run_div(dv):
    fn = OUTD + f'{dv}.npz'
    if os.path.exists(fn): return
    import lightgbm as lgb, build_day_features as B, gfs_features as G
    from app.cloud_inputs import modis_frames
    meta = json.load(open(PM + 'meta.json')); static = pd.read_parquet(PM + 'static_inputs.parquet')
    clim = pd.read_parquet(PM + 'modis_clim.parquet'); gis = pd.read_parquet(L.P + 'ratapani/mp_grid/static_gis_v1.parquet')
    fires = pd.read_parquet(PM + 'fire_celldays.parquet'); fires['date'] = pd.to_datetime(fires.date)
    npz = dict(np.load(L.P + 'ratapani/mp_grid/dryness/mp_dry_2025.npz'))
    gfs = pd.read_csv(PM + 'cloud_series/gfs_daily_2025.csv', parse_dates=['date']); sw = pd.read_csv(PM + 'cloud_series/swvl1_2025.csv', parse_dates=['date'])
    cells = static.loc[static.division == dv, 'cell'].to_numpy(); div = B.Division(dv, cells)
    w = G.weather_table(gfs[gfs.division == dv].set_index('date'), sw[sw.division == dv].set_index('date').swvl1)
    sr, lst = modis_frames(PM + 'cloud_series/modis_2025.npz', cells, 2025)
    f = meta['divisions'][dv]['features']; cl = clim[clim.division == dv]
    m = lgb.Booster(model_str=lzma.decompress(open(PM + f'models/{dv}.txt.xz', 'rb').read()).decode())
    S = np.zeros((len(DAYS), div.n), np.float32); t0 = time.time()
    for i, t in enumerate(DAYS):
        df = B.build(div, t, static, gis, fires, sr, lst, cl, npz, w.loc[t], f)
        S[i] = m.predict(df[f].values.astype(np.float64), num_threads=1)
        if i == 0: dc = df.cell.to_numpy()
    np.savez(fn, cells=dc, S=S)
    print('done', dv, div.n, round(time.time() - t0), 's', flush=True)


def cube():
    import lf_sr
    B = lf_sr.Fe.base(); U = B['U']; home = B['home']; names = B['divnames']
    C = np.full((len(DAYS), len(U)), np.nan, np.float32); own = np.zeros(len(U), bool)
    norm = lambda s: s.replace(' ', '_')
    for fn in sorted(os.listdir(OUTD)):
        dv = fn[:-4]; z = np.load(OUTD + fn); c = z['cells']; ii = np.searchsorted(U, c); ok = (ii < len(U)) & (U[np.minimum(ii, len(U) - 1)] == c)
        k = names.index(norm(dv)) if norm(dv) in names else -1
        mine = ok & (home[np.minimum(ii, len(U) - 1)] == k)
        fill = ok & ~own[np.minimum(ii, len(U) - 1)] & ~mine          # other-division copy only where no own score
        for sel in (fill, mine):
            C[:, ii[sel]] = z['S'][:, sel]
        own[ii[mine]] = True
    print('squares with own-division score', own.mean(), 'any score', np.isfinite(C[0]).mean(), flush=True)
    np.save(L.SC + 'cube_PC_2025.npy', np.nan_to_num(C, nan=-1).astype(np.float16) if False else C)


if __name__ == '__main__':
    if sys.argv[1] == 'run':
        from multiprocessing import Pool
        meta = json.load(open(PM + 'meta.json')); st = pd.read_parquet(PM + 'static_inputs.parquet', columns=['division'])
        dvs = st.division.value_counts().index.tolist()   # largest first
        with Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 4) as p: p.map(run_div, dvs, chunksize=1)
    else:
        cube()
