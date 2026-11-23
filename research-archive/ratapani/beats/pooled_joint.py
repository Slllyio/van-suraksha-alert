"""Joint variant (coordinator scouting note: literature favours pooling reserves with a region flag over pretrain-then-fine-tune).
One network per held-out Ratapani season, trained on mixed batches: half VIIRS fire points from the 8 other MP reserves
(Ratapani extra channels zero, flag 0), half Ratapani burn scars from the training seasons (extra channels on, flag 1).
Scored with the shared rule on real beats too.  Usage: python3 scr/pooled_joint.py [--smoke] [--steps N] [--seasons 2018,2020]"""
import sys, json, time, pickle, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, '/home/user/vanagni')
from src.analysis import fire_occurrence as FO
from src.analysis.fwi_observed import roll_fwi
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform as shp_transform
import torch, torch.nn as nn, torch.nn.functional as F
torch.set_num_threads(2); torch.manual_seed(0)
SMOKE = '--smoke' in sys.argv
RS = '/mnt/project-files/research/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
S = 500; TR = pickle.load(open('tr.pkl', 'rb')); fwd = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
YEARS = list(range(2013, 2025)); D0 = {Y: pd.Timestamp(f'{Y}-01-01') for Y in YEARS}; ND = 174   # Jan 1 .. Jun 23
SEAS_OFF = (pd.Timestamp('2001-02-01') - pd.Timestamp('2001-01-01')).days                      # Feb 1 offset (31)
def sdays(Y): return pd.date_range(f'{Y}-02-01', f'{Y}-06-20')
WX = ['ffmc', 'rh_pct', 'temp_c', 'dmc', 'dc', 'wind_kmh', 'precip_mm', 'rh_min_7d', 'days_since_rain', 'doy_sin', 'doy_cos']
Wall = pd.read_parquet('weather_power.parquet')
def reserve(K):
    poly = shp_transform(fwd, TR[K]); x0, y0, x1, y1 = poly.bounds
    xs = np.arange(np.floor(x0 / S) * S, x1 + S, S); ys = np.arange(np.floor(y0 / S) * S, y1 + S, S); ij = []
    for i, cx in enumerate(xs[:-1]):
        for j, cy in enumerate(ys[:-1]):
            b = box(cx, cy, cx + S, cy + S)
            if b.intersects(poly) and b.intersection(poly).area / b.area >= 0.05: ij.append((i, j))
    ij = np.array(ij); H, W = len(ys) - 1, len(xs) - 1
    mask = np.zeros((H, W), np.float32); mask[ij[:, 1], ij[:, 0]] = 1
    det = pd.read_parquet(f"det_{K.replace(' ', '_')}.parquet"); dx, dy = fwd(det.longitude.values, det.latitude.values)
    di = np.floor((dx - xs[0]) / S).astype(int); dj = np.floor((dy - ys[0]) / S).astype(int); dd = pd.to_datetime(det.acq_date)
    Fz = np.zeros((len(YEARS), ND, H, W), np.uint8)
    for k, Y in enumerate(YEARS):
        o = (dd - D0[Y]).dt.days.values; s = (o >= 0) & (o < ND) & (di >= 0) & (di < W) & (dj >= 0) & (dj < H)
        np.add.at(Fz[k], (o[s], dj[s], di[s]), 1)
    Fz *= mask.astype(np.uint8)[None, None]
    w = Wall[Wall.reserve == K].copy(); w['date'] = w.date.dt.date; w = roll_fwi(w, unit_col='reserve'); w = FO.build_features(w)
    w = w.set_index(pd.to_datetime(w.date))[WX]
    return dict(K=K, ij=ij, H=H, W=W, mask=mask, F=Fz, wx=w, xs=xs, ys=ys)
t0 = time.time()
R = {K: reserve(K) for K in TR}; print('reserves', {K: (r['H'], r['W'], int(r['F'].sum())) for K, r in R.items()}, f'{time.time()-t0:.0f}s', flush=True)
allwx = pd.concat([r['wx'] for r in R.values()]); WMU, WSD = allwx.mean().values, allwx.std().values + 1e-6
def dyn(r, k, o):
    """VIIRS-history channels for reserve r, year index k, day offset o (issue day): fires known through day o."""
    Fk = r['F'][k]
    def win(a): return Fk[max(o - a + 1, 0):o + 1].sum(0, dtype=np.float32)
    f1 = Fk[o].astype(np.float32); tot1 = f1.sum(); w7 = win(7); tot7 = w7.sum()
    ch = [f1, win(3), w7, win(30), win(o + 1)]
    ch = [np.log1p(x) for x in ch] + [np.full_like(Fk[o], np.log1p(tot1)), np.full_like(Fk[o], np.log1p(tot7))]
    return np.stack(ch)
def wxch(r, day):
    v = (r['wx'].loc[day].values - WMU) / WSD if day in r['wx'].index else np.zeros(len(WX))
    return np.nan_to_num(v).astype(np.float32)
def target_viirs(r, k, o): return (r['F'][k][o + 1:o + 3].sum(0) > 0).astype(np.float32)
NDYN = 7; NWX = len(WX); CBASE = NDYN + NWX + 1
# ── Ratapani-only extra channels (fine-tuning): static, burn prior, per-cell dryness, scars already seen ──
rp = R['Ratapani']; HH, WW = rp['H'], rp['W']
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
gpos = {(f['properties']['x0'], f['properties']['y0']): f['properties']['cell_id'] for f in G}
cid = np.array([gpos[(float(rp['xs'][i]), float(rp['ys'][j]))] for i, j in rp['ij']]); rr, cc_ = rp['ij'][:, 1], rp['ij'][:, 0]
inv = np.full(3614, -1); inv[cid] = np.arange(len(cid))
def to_map(v):   # v indexed by cell_id (..., 3614) -> (..., H, W)
    out = np.zeros(v.shape[:-1] + (HH, WW), np.float32); out[..., rr, cc_] = v[..., cid]; return out
st = pd.read_parquet('static_features.parquet').merge(pd.read_parquet('roads_features.parquet'), on='cell_id').set_index('cell_id').sort_index()
stv = st.to_numpy(np.float32); stv = np.nan_to_num((stv - np.nanmean(stv, 0)) / (np.nanstd(stv, 0) + 1e-6)); STAT = to_map(stv.T)
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw1 = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
SC_YEARS = list(range(2017, 2025)); Bm = np.zeros((len(SC_YEARS), 3614))
for r_ in bw1[bw1.season.isin(SC_YEARS)].itertuples(): Bm[SC_YEARS.index(r_.season), r_.cell_id] = 1
sc = pd.read_parquet(RS + 'ratapani-ignition/s2_cells.parquet'); cl = pd.read_parquet(RS + 'ratapani-burn-labels/clear_calendar.parquet')
cl['date'] = pd.to_datetime(cl['date']); cl = cl[cl.clear_frac >= 0.5][['cell_id', 'date']].drop_duplicates(); sc = sc.merge(cl, on=['cell_id', 'date'])
_m = bw[bw.burned == 1][['cell_id', 'window_start', 'window_end']].merge(sc[['cell_id', 'date']], on='cell_id')
_in = _m[(_m.date > _m.window_start) & (_m.date < _m.window_end)][['cell_id', 'date']].drop_duplicates()
sc = sc.merge(_in.assign(_x=1), on=['cell_id', 'date'], how='left'); sc = sc[sc._x.isna()]
cal = pd.date_range('2016-12-01', '2024-06-30'); DRY = {}
for col in ('ndvi', 'ndmi', 'nbr'):
    d = sc.pivot_table(index='date', columns='cell_id', values=col).reindex(index=cal, columns=range(3614)).shift(1)
    last = d.ffill(limit=60); DRY[col] = last.to_numpy(np.float32); DRY[col + '_chg'] = (last - last.shift(30)).to_numpy(np.float32)
for k_ in list(DRY): a = DRY[k_]; DRY[k_] = np.nan_to_num((a - np.nanmean(a)) / (np.nanstd(a) + 1e-6))
def extra(Y, day, prior_v):
    """Ratapani extra channels on issue day: 9 static-ish (subset), prior, 6 dryness, 2 seen-scar maps."""
    g = bw1[bw1.season == Y]; seen = np.zeros(3614, np.float32); seen7 = np.zeros(3614, np.float32)
    ok = g.window_end <= day - pd.Timedelta(days=1); seen[g.cell_id[ok].values] = 1
    ok7 = ok & (g.window_end > day - pd.Timedelta(days=8)); seen7[g.cell_id[ok7].values] = 1
    k = cal.get_loc(day)
    dry = np.stack([DRY[c][k] for c in ('ndvi', 'ndmi', 'nbr', 'ndvi_chg', 'ndmi_chg', 'nbr_chg')])
    return np.concatenate([STAT, to_map(prior_v[None]), to_map(dry), to_map(np.stack([seen, seen7]))], 0)
NEXTRA = STAT.shape[0] + 1 + 6 + 2
lab = ps.labels(SC_YEARS); lab['k'] = lab.groupby(['season', 'date']).ngroup()
class Net(nn.Module):
    def __init__(s, cin, cx=0, w=48):
        super().__init__(); s.inp = nn.Conv2d(cin, w, 1); s.cx = cx
        s.inx = nn.Conv2d(cx, w, 1) if cx else None
        if cx: nn.init.zeros_(s.inx.weight); nn.init.zeros_(s.inx.bias)
        s.blocks = nn.ModuleList([nn.Sequential(nn.Conv2d(w, w, 3, padding=d, dilation=d), nn.GroupNorm(8, w), nn.GELU(),
                                                nn.Conv2d(w, w, 3, padding=d, dilation=d), nn.GroupNorm(8, w)) for d in (1, 2, 4, 8)])
        s.out = nn.Conv2d(w, 1, 1)
    def forward(s, x, xe=None):
        h = s.inp(x)
        if s.inx is not None and xe is not None: h = h + s.inx(xe)
        for b in s.blocks: h = F.gelu(h + b(h))
        return s.out(h)[:, 0]
def base_input(r, k, o):
    Y = YEARS[k]; day = D0[Y] + pd.Timedelta(days=o)
    m = r['mask'][None]; w = wxch(r, day)[:, None, None] * m
    return np.concatenate([dyn(r, k, o) * m, np.broadcast_to(w, (NWX, r['H'], r['W'])), m], 0).astype(np.float32)
def crop(a, y0, x0, c=96): return a[..., y0:y0 + c, x0:x0 + c]
def pretrain(exclude_year, epochs=2, steps_cap=None):
    net = Net(CBASE); opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    items = [(K, k, o) for K in R if K != 'Ratapani' for k, Y in enumerate(YEARS) if Y != exclude_year for o in range(SEAS_OFF, ND - 3)]
    rs = np.random.RandomState(0); BS = 8; steps = epochs * len(items) // BS
    if steps_cap: steps = min(steps, steps_cap)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=steps); net.train()
    for st_ in range(steps):
        xb, yb, mb = [], [], []
        for q in rs.randint(len(items), size=BS):
            K, k, o = items[q]; r = R[K]; c = 96
            y0 = rs.randint(max(1, r['H'] - c + 1)); x0 = rs.randint(max(1, r['W'] - c + 1))
            x = crop(base_input(r, k, o), y0, x0); t = crop(target_viirs(r, k, o), y0, x0); m = crop(r['mask'], y0, x0)
            pad = lambda a: np.pad(a, [(0, 0)] * (a.ndim - 2) + [(0, c - a.shape[-2]), (0, c - a.shape[-1])])
            xb.append(pad(x)); yb.append(pad(t)); mb.append(pad(m))
        x = torch.from_numpy(np.stack(xb)); y = torch.from_numpy(np.stack(yb)); m = torch.from_numpy(np.stack(mb))
        lo = net(x); loss = (F.binary_cross_entropy_with_logits(lo, y, pos_weight=torch.tensor(20.0), reduction='none') * m).sum() / m.sum()
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        if st_ % 500 == 0: print(f'    pretrain step {st_}/{steps} loss {loss.item():.4f}', flush=True)
    return net
def rp_inputs(Y, prior_v):
    k = YEARS.index(Y); days = sdays(Y); xs_, xe_ = [], []
    for day in days:
        o = (day - D0[Y]).days; xs_.append(base_input(rp, k, o).astype(np.float16)); xe_.append(extra(Y, day, prior_v).astype(np.float16))
    return np.stack(xs_), np.stack(xe_), days
def rp_labels(Y, days):
    L = np.zeros((len(days), HH, WW), np.float32); V = np.zeros_like(L); g = lab[lab.season == Y]
    t = (g.date - days[0]).dt.days.values; c = inv[g.cell_id.values]
    V[t, rr[c], cc_[c]] = 1; L[t, rr[c], cc_[c]] = g.pos.values.astype(np.float32); return L, V
def finetune(net, Xs, Xe, Ls, Vs, epochs=6, lr=1e-3):
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4); n_ = len(Xs); BS = 8
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * ((n_ + BS - 1) // BS)); net.train()
    for ep in range(epochs):
        perm = np.random.RandomState(ep).permutation(n_)
        for q in range(0, n_, BS):
            i = perm[q:q + BS]; x = torch.from_numpy(Xs[i].astype(np.float32)); xe = torch.from_numpy(Xe[i].astype(np.float32)); y = torch.from_numpy(Ls[i]); v = torch.from_numpy(Vs[i])
            lo = net(x, xe); loss = (F.binary_cross_entropy_with_logits(lo, y, pos_weight=torch.tensor(4.0), reduction='none') * v).sum() / v.sum().clamp(min=1)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
    return net
def predict(net, Xs, Xe):
    net.eval(); out = []
    with torch.no_grad():
        for q in range(0, len(Xs), 16): out.append(torch.sigmoid(net(torch.from_numpy(Xs[q:q + 16].astype(np.float32)), torch.from_numpy(Xe[q:q + 16].astype(np.float32)) if Xe is not None else None)).numpy())
    return np.concatenate(out)[:, rr, cc_]   # days x cells (our order)
STEPS = int(sys.argv[sys.argv.index('--steps') + 1]) if '--steps' in sys.argv else 1500
test_years = [int(s) for s in sys.argv[sys.argv.index('--seasons') + 1].split(',')] if '--seasons' in sys.argv else SC_YEARS
if SMOKE: test_years, STEPS = test_years[:1], 40
PIDX = STAT.shape[0]; DATA = {s_: rp_inputs(s_, np.zeros(3614, np.float32)) for s_ in SC_YEARS}; print('ratapani inputs built', flush=True)
others = [(K, k, o) for K in R if K != 'Ratapani' for k, Y in enumerate(YEARS) for o in range(SEAS_OFF, ND - 3)]
def pad(a, c=96): return np.pad(a, [(0, 0)] * (a.ndim - 2) + [(0, c - a.shape[-2]), (0, c - a.shape[-1])])
def flag(v, H, W): return np.full((1, H, W), v, np.float32)
def joint(Xs, Xe, Ls, Vs):
    torch.manual_seed(0); net = Net(CBASE + 1, NEXTRA); nn.init.normal_(net.inx.weight, std=0.05)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4); sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=STEPS)
    rs = np.random.RandomState(0); net.train(); c = 96
    for st_ in range(STEPS):
        xb, eb, yb, mb, pw = [], [], [], [], []
        for _ in range(4):   # 4 crops from the other reserves (VIIRS targets)
            K, k, o = others[rs.randint(len(others))]; r = R[K]; y0 = rs.randint(max(1, r['H'] - c + 1)); x0 = rs.randint(max(1, r['W'] - c + 1))
            x = np.concatenate([base_input(r, k, o), flag(0, r['H'], r['W'])]); xb.append(pad(crop(x, y0, x0))); eb.append(np.zeros((NEXTRA, c, c), np.float32))
            yb.append(pad(crop(target_viirs(r, k, o), y0, x0))); mb.append(pad(crop(r['mask'], y0, x0))); pw.append(20.0)
        for i in rs.randint(len(Xs), size=4):   # 4 Ratapani scar days (whole sanctuary, padded/cropped to 96 rows)
            y0 = rs.randint(max(1, HH - c + 1)); x0 = rs.randint(max(1, WW - c + 1))
            x = np.concatenate([Xs[i].astype(np.float32), flag(1, HH, WW)]); xb.append(pad(crop(x, y0, x0))); eb.append(pad(crop(Xe[i].astype(np.float32), y0, x0)))
            yb.append(pad(crop(Ls[i], y0, x0))); mb.append(pad(crop(Vs[i], y0, x0))); pw.append(4.0)
        x, xe, y, m = (torch.from_numpy(np.stack(a)) for a in (xb, eb, yb, mb)); p = torch.tensor(pw)[:, None, None]
        lo = net(x, xe); l = F.binary_cross_entropy_with_logits(lo, y, reduction='none') * (1 + (p - 1) * y) * m
        loss = l[:4].sum() / m[:4].sum().clamp(min=1) + l[4:].sum() / m[4:].sum().clamp(min=1)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        if st_ % 500 == 0: print(f'    joint step {st_}/{STEPS} loss {loss.item():.4f}', flush=True)
    return net
def predict_j(net, Xs, Xe):
    net.eval(); out = []; f = np.ones((1, 1, HH, WW), np.float32)
    with torch.no_grad():
        for q in range(0, len(Xs), 16):
            x = Xs[q:q + 16].astype(np.float32); x = np.concatenate([x, np.repeat(f, len(x), 0)], 1)
            out.append(torch.sigmoid(net(torch.from_numpy(x), torch.from_numpy(Xe[q:q + 16].astype(np.float32)))).numpy())
    return np.concatenate(out)[:, rr, cc_]
rows = []
for Y in test_years:
    t1 = time.time(); trY = [s for s in SC_YEARS if s != Y]
    prior_v = np.log((Bm[[SC_YEARS.index(s) for s in trY]].sum(0) + 0.5) / (len(trY) + 1)).astype(np.float32); prior_v = (prior_v - prior_v.mean()) / prior_v.std()
    for s_ in SC_YEARS: DATA[s_][1][:, PIDX] = to_map(prior_v[None])[0].astype(np.float16)
    Xs = np.concatenate([DATA[s][0] for s in trY]); Xe = np.concatenate([DATA[s][1] for s in trY])
    LV = [rp_labels(s, DATA[s][2]) for s in trY]; Ls = np.concatenate([a for a, _ in LV]); Vs = np.concatenate([b for _, b in LV])
    P = predict_j(joint(Xs, Xe, Ls, Vs), DATA[Y][0], DATA[Y][1]); days = DATA[Y][2]; del Xs, Xe, Ls, Vs
    rows.append(pd.DataFrame(dict(season=Y, date=np.repeat(days, len(cid)), cell_id=np.tile(cid, len(days)), joint=P.reshape(-1))))
    print(f'season {Y} done {time.time()-t1:.0f}s', flush=True)
pr = pd.concat(rows); pr.to_parquet('pred_pooled_joint' + ('_smoke' if SMOKE else '_' + '-'.join(map(str, test_years))) + '.parquet'); labY = lab[lab.season.isin(test_years)]
lean = pd.read_parquet('pred_lean_loso.parquet'); m = pr.merge(lean, on=['season', 'date', 'cell_id'])
m['blend'] = m.groupby(['season', 'date']).joint.rank() + m.groupby(['season', 'date']).pipeline_lean.rank()
res = ps.score(m, labY, ['joint', 'blend', 'pipeline_lean']); out = {k: v for k, v in res.items() if k.endswith('recall@5')}; out['seasons'] = test_years
cb = pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv')   # real beats, 5 picks per beat per day among valid cells
v = labY[['season', 'date', 'cell_id', 'pos']].merge(m, on=['season', 'date', 'cell_id']).merge(cb[['cell_id', 'beat_uid']], on='cell_id')
for col in ('joint', 'blend', 'pipeline_lean'):
    v['_r'] = v.groupby(['season', 'date', 'beat_uid'])[col].rank(ascending=False, method='first'); out['real94_' + col] = float(v.pos[v._r <= 5].sum() / v.pos.sum())
print(json.dumps(out), flush=True); json.dump(out, open('results_pooled_joint' + ('_smoke' if SMOKE else '_' + '-'.join(map(str, test_years))) + '.json', 'w'), indent=1); print('JOINT_DONE')
