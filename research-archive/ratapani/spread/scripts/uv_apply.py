"""Unseen-fire validation of the per-look front forecast (Oct 17, Akkshay: "use this model on unseen fires and validate").
Frozen models (multi_front/models/*_all.txt, trained on the 146 big fires only) and the forecast tool itself (forecast_fronts.forecast)
are applied, with no refitting, to fires NOT among the 146. Truth as before: fire-continuity blend map inside the fire's outline v2.
Stage 1 (mf_tracker.py with FIRE_LIST) gives the true new burning per front; this script issues the tool's forecast at every look
and scores it.
  FC_SCRATCH=/tmp/claude-0/fronts python3 uv_apply.py prefix            (fires with 2+ looks)
  FC_SCRATCH=/tmp/claude-0/fronts python3 uv_apply.py prefix one.csv    (fires seen at one look only: eventual growth check)
"""
import os, sys, pickle, json, warnings, numpy as np, pandas as pd
warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree
from rasterio import features
from rasterio.transform import Affine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forecast_fronts as FF
C = FF.C
LOSO = os.environ.get('FF_LOSO')            # dir of per-season models (uv_retrain.py): use the one that never saw this season
TAG = '_loso' if LOSO else ''
PRE = sys.argv[1]; X0, Y0 = 737300.0, 2560500.0
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']


def soren(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


if len(sys.argv) > 2:                         # one-look fires: forecast at the only look vs the final outline
    SC = pickle.load(open(f"{os.environ['FC_SCRATCH']}/fire_scars.pkl", 'rb'))
    from shapely.geometry import Point
    from shapely.ops import unary_union
    rows = []
    for fire in pd.read_csv(sys.argv[2]).fire:
        g = A[A.fire == fire]
        d, k, feats, foot, fc, band = FF.forecast(g.copy())
        f0 = feats[0] if len(feats) == 1 else max(feats, key=lambda x: len(x[3]))
        near = unary_union([Point(p).buffer(1000) for p in d[['x', 'y']].values])
        poly = SC[fire]
        rows.append(dict(fire=fire, dots=len(d), n_fronts=len(feats), pred_ha=sum(x[4] for x in feats), p_stop=min(x[5] for x in feats),
                         outline_ha=poly.area / 1e4, beyond_ha=poly.difference(foot).intersection(near).area / 1e4,
                         foot_ha=foot.area / 1e4, fc_ha=fc.area / 1e4,
                         sor_fc=2 * fc.intersection(poly).area / (fc.area + poly.area), sor_foot=2 * foot.intersection(poly).area / (foot.area + poly.area)))
    pd.DataFrame(rows).to_csv(f'{PRE}_one.csv', index=False); print('done', len(rows)); sys.exit()

R = pd.read_parquet(f'{PRE}_fronts.parquet'); I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
TRAIN = pd.read_parquet('/tmp/claude-0/fronts/mf_fronts.parquet'); TRAIN = TRAIN[TRAIN.active]
MED = float(np.median(TRAIN.new24_ha))                      # 'same growth for every front' baseline, from the training fires
fr_rows, is_rows = [], []
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg']; dom = mp['dom']
    tr = Affine(20, 0, X0 + c0 * 20, 0, -20, Y0 - r0 * 20)
    rr, cc = np.mgrid[r0:r1, c0:c1]; Pxy = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    allg = A[A.fire == fire]; dl = C.viirs_looks(allg)
    for it in g.itertuples():
        tiss = dl[dl.lk == it.k].t.max()
        mdl = (FF.lgb.Booster(model_file=f'{LOSO}/growth24_{it.season}.txt'), FF.lgb.Booster(model_file=f'{LOSO}/stop24_{it.season}.txt')) if LOSO else None
        d, k, feats, foot, fc, band = FF.forecast(allg.copy(), tiss, mdl)
        assert k == it.k
        truth = (dom & (Tg <= it.th + 24)).ravel()
        ras = lambda geom: features.rasterize([geom], out_shape=dom.shape, transform=tr).astype(bool).ravel() if not geom.is_empty else np.zeros(dom.size, bool)
        m_fc, m_foot = ras(fc), ras(foot)
        xy = d[['x', 'y']].values; dall = cKDTree(xy).query(Pxy)[0]
        n_fc = int(m_fc.sum()); order = np.argsort(dall, kind='stable')
        blob = np.zeros(len(dall), bool); blob[order[:n_fc]] = True                          # same area, one blob around all dots
        n_med = int(m_foot.sum() + MED * sum(1 for x in feats if x[2]) / .04)
        blob_med = np.zeros(len(dall), bool); blob_med[order[:n_med]] = True                 # baseline: median growth per active front
        new = (dom & (Tg > it.th) & (Tg <= it.th + 24)).ravel(); far = new & (dall > 1000)
        inband = far & (dall <= 3000); band_px = (dall > 1000) & (dall <= 3000)
        is_rows.append(dict(fire=fire, season=it.season, k=it.k, th=it.th, truth_ha=truth.sum() * .04, new24_ha=new.sum() * .04,
                            fc_ha=n_fc * .04, foot_ha=m_foot.sum() * .04, sor_tool=soren(m_fc, truth), sor_foot=soren(m_foot, truth),
                            sor_blob_same_area=soren(blob, truth), sor_blob_median=soren(blob_med, truth),
                            far1k_ha=far.sum() * .04, far_in_band_ha=inband.sum() * .04, band_ha=band_px.sum() * .04,
                            band_hit_rate=inband.sum() / max(band_px.sum(), 1)))
        dd_, near_ = cKDTree(xy).query(Pxy); own_of = d.front.values[near_]            # true new burning per front, as in mf_tracker.py
        for f, kind, act, gx, grow, pstop in feats:
            if act:
                g_ = d[d.front == f]
                fr_rows.append(dict(fire=fire, season=it.season, k=it.k, front=int(f), kind=kind, n_dots=len(g_), n_dots_last=int((g_.lk == k).sum()),
                                    n_dots_last2=int((g_.lk >= k - 1).sum()), pred_ha=grow, p_stop=pstop,
                                    true_ha=float((new & (own_of == f) & (dd_ <= 1000)).sum() * .04)))
    if len(is_rows) % 200 < len(g):
        print(fire, len(is_rows), flush=True)
pd.DataFrame(fr_rows).to_csv(f'{PRE}_apply{TAG}_fronts.csv', index=False); pd.DataFrame(is_rows).to_csv(f'{PRE}_apply{TAG}_issues.csv', index=False)
print('done', len(is_rows), 'issues', len(fr_rows), 'active front rows')
