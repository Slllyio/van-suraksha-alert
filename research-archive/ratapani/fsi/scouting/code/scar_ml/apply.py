"""Run every method on every test chip and date the burned pixels.
Methods: rule (current rule re-implemented on the chip, all FIRMS alerts in the image gap as seeds; on decoys a pretend
VIIRS alert at the chip centre), v2 (the frozen v2 event outline, Wayback real chips only), b_abs (NBR drop >= 0.10),
b_nc (rule pass-1 test with no alert tie), ml_pu / ml_pn / ml_af (learned models, P >= 0.5, patches >= 0.5 ha).
For fire-pixel and photo chips the truth scene's date is removed from the image stack first.
Out: scratch/res/<chip>.npz and res_index.jsonl (pair dates, compute seconds)."""
import os, sys, json, time, warnings, numpy as np, pandas as pd, lightgbm as lgb, geopandas as gpd
from rasterio.features import rasterize
from concurrent.futures import ProcessPoolExecutor
from lib import CODE, SCR, prepare, features, static_layers, patches, burn_dates
warnings.filterwarnings('ignore')
os.makedirs(SCR + 'res', exist_ok=True)
META = json.load(open(CODE + 'train_meta.json')); FE = META['features']; CPU = META['pu_c']
FAF = json.load(open(CODE + 'train_af_meta.json'))['features']; IAF = [FE.index(f) for f in FAF]
V2 = None


def v2_mask(key, st):
    global V2
    if V2 is None:
        V2 = gpd.read_file('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson').to_crs(32643).set_index('event_id')
    if key not in V2.index: return np.zeros((st['n'], st['n']), bool)
    import rasterio
    return rasterize([V2.loc[key].geometry], out_shape=(st['n'], st['n']), transform=rasterio.Affine(*st['tr']), all_touched=False).astype(bool)


def one(r):
    out = f"{SCR}res/{r['chip']}.npz"
    if os.path.exists(out) or not os.path.exists(f"{SCR}stacks/{r['chip']}.npz"): return None
    t = time.time()
    ex = [r['scene_date']] if isinstance(r.get('scene_date'), str) else []
    p = prepare(r, ex, pretend_centre=r['kind'] == 'wb_decoy')
    if p is None:
        return dict(chip=r['chip'], status='no_pair')
    t1 = time.time()
    st = p['st']; n = st['n']
    f = features(st, p['pair'], p['parts'], static_layers(st['tr'], n))
    Xf = np.stack([f[k].ravel() for k in FE], 1).astype(np.float32)
    bpu = lgb.Booster(model_file=CODE + 'model_pu.txt'); bpn = lgb.Booster(model_file=CODE + 'model_pn.txt'); baf = lgb.Booster(model_file=CODE + 'model_af.txt')
    ok = p['parts']['ok']
    ppu = np.minimum(bpu.predict(Xf, num_threads=1).reshape(n, n) / CPU, 1.0); ppn = bpn.predict(Xf, num_threads=1).reshape(n, n)
    paf = baf.predict(Xf[:, IAF], num_threads=1).reshape(n, n)
    ppu[~ok] = 0; ppn[~ok] = 0; paf[~ok] = 0
    ml_pu = patches(ppu >= 0.5)[0]; ml_pn = patches(ppn >= 0.5)[0]; ml_af = patches(paf >= 0.5)[0]
    t2 = time.time()
    v2 = v2_mask(r['key'], st) if r['kind'] == 'wb_real' else np.zeros((n, n), bool)
    anyb = ml_pu | ml_pn | ml_af | p['rule'] | p['b_nc'] | p['b_abs'] | v2
    extra = {}
    if r['kind'] == 'photo':  # the fuel thread's final scar S, put on this chip's grid, so every S pixel gets a date
        z = np.load(f"/mnt/project-files/fuel-map/ratapani/timing/chips/{r['key']}.npz")
        Sg = np.zeros((n, n), bool); bym = np.zeros((n, n), bool); okp = np.zeros((n, n), bool)
        ii, jj = np.where(z['S'])
        import rasterio
        with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as s_: TRB = s_.transform
        X = TRB.c + (jj + int(z['j0']) + 0.5) * 20; Y = TRB.f - (ii + int(z['i0']) + 0.5) * 20
        cc = ((X - st['tr'][2]) / 20).astype(int); rr = ((st['tr'][5] - Y) / 20).astype(int); k = (cc >= 0) & (cc < n) & (rr >= 0) & (rr < n)
        Sg[rr[k], cc[k]] = True; bym[rr[k], cc[k]] = z['bym'][ii[k], jj[k]]; okp[rr[k], cc[k]] = z['ok'][ii[k], jj[k]]
        anyb = anyb | Sg
        extra = dict(S=Sg, bym=bym, okp=okp)
    U, L = burn_dates(st, anyb, ex)
    t3 = time.time()
    np.savez_compressed(out, rule=p['rule'], core=p['core'], v2=v2, b_abs=p['b_abs'], b_nc=p['b_nc'], ml_pu=ml_pu, ml_pn=ml_pn, ml_af=ml_af, p_af=paf.astype(np.float16),
                        p_pu=ppu.astype(np.float16), p_pn=ppn.astype(np.float16), ok=ok, disk=p['disk'], U=U.astype(np.float32), L=L.astype(np.float32),
                        rdn=p['parts']['rdn'].astype(np.float16), **extra)
    return dict(chip=r['chip'], status='ok', rule_status=p['rule_status'], n_alerts=p['n_alerts'], **{k: p['pair'][k] for k in ('pre', 'post', 'check')},
                n_looks=len(st['dates']), sec_rule=round(t1 - t, 2), sec_ml=round(t2 - t1, 2), sec_date=round(t3 - t2, 2), n=n)


if __name__ == '__main__':
    C = pd.read_csv(CODE + 'chips.csv')
    kinds = sys.argv[1].split(',') if len(sys.argv) > 1 else ['wb_real', 'wb_decoy', 'af_nofirms', 'af_firms', 'photo']
    C = C[C.kind.isin(kinds)]
    log = SCR + 'res_index.jsonl'
    with ProcessPoolExecutor(3) as exe:
        for res in exe.map(one, C.to_dict('records'), chunksize=4):
            if res: open(log, 'a').write(json.dumps(res) + '\n')
