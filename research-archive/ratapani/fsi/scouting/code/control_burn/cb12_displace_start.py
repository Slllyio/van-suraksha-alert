"""Step 12. Displacement test without split fires. cb11 counts a fire's cells by the day each cell burnt, so one fire that
crosses 15 March AND a square edge is 'early' in its square and 'late' in the neighbour, which alone would give a positive
ring slope. Here every fire is assigned whole to the square-season by its START day and START square: early = fires started
15 Feb-15 Mar (forest ha, all their cells), late = fires started 16 Mar-15 Jun; the cells are credited to the square they lie in,
the period to the fire's start. Gap variant: early = started 15 Feb-1 Mar, late = started 16 Mar on (no fire runs two weeks).
Same two-way FE ring regression as cb11. Out: out/cb12_squares.parquet, out/cb12_displace.csv"""
import os, sys, glob, pickle
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
from cb11_displace import rings, fit
rng = np.random.default_rng(3)


def build():
    rows = []
    for key in B.KEYS:
        L, FOR = B.load_div(key); H, W = L['H'], L['W']
        sq = (np.arange(H)[:, None] // B.SQ) * 1000 + (np.arange(W)[None, :] // B.SQ)
        fha = np.bincount(sq[FOR].ravel()) * B.CELL_HA
        acc = {}
        for f in L['fires']:
            d0 = f['t0'].dayofyear
            if d0 < 46 or d0 > 166: continue
            per = 'e' if d0 <= 74 else 'l'; per2 = 'e2' if d0 <= 59 else ('l' if d0 >= 75 else None)
            h, w = f['shape']; Mm = np.unpackbits(f['M'])[:h * w].astype(bool).reshape(h, w)
            rr, cc = np.nonzero(Mm); rr = rr + f['r0']; cc = cc + f['c0']
            fo = FOR[rr, cc]; s = sq[rr[fo], cc[fo]]
            cnt = pd.Series(s).value_counts()
            for q, n in cnt.items():
                k = (f['year'], int(q)); a = acc.setdefault(k, [0.0, 0.0, 0.0])
                a[0 if per == 'e' else 1] += n * B.CELL_HA
                if per2 == 'e2': a[2] += n * B.CELL_HA
        for (y, q), a in acc.items():
            rows.append(dict(key=key, year=y, sq=q, ha_e=a[0], ha_l=a[1], ha_e2=a[2], forest_ha=fha[q] if q < len(fha) else 0.0))
        fh = pd.DataFrame({'sq': np.arange(len(fha)), 'forest_ha': fha}); fh = fh[fh.forest_ha > 0]
        for q, fa in zip(fh.sq, fh.forest_ha):
            for y in B.YEARS:
                if (y, int(q)) not in acc: rows.append(dict(key=key, year=y, sq=int(q), ha_e=0.0, ha_l=0.0, ha_e2=0.0, forest_ha=fa))
        print(key, flush=True)
    S = pd.DataFrame(rows); S.to_parquet(B.OUT + 'cb12_squares.parquet'); return S


def main():
    S = build() if not os.path.exists(B.OUT + 'cb12_squares.parquet') else pd.read_parquet(B.OUT + 'cb12_squares.parquet')
    S['e1'], S['e2'] = rings(S, 'ha_e'); S['g1'], S['g2'] = rings(S, 'ha_e2')
    S = S[S.forest_ha >= 200].copy(); S['sqid'] = S.groupby(['key', 'sq']).ngroup(); S['dyid'] = S.groupby(['key', 'year']).ngroup()
    print('square-seasons', len(S), 'early ha/yr', round(S.ha_e.sum() / 9), 'late', round(S.ha_l.sum() / 9), flush=True)
    rows = []
    for xcols, lab in ((['ha_e', 'e1', 'e2'], 'fires started 15 Feb-15 Mar vs fires started 16 Mar on'), (['ha_e2', 'g1', 'g2'], 'fires started 15 Feb-1 Mar vs started 16 Mar on (gap)')):
        b, lo, hi, bs = fit(S, 'ha_l', xcols); mult = np.array((1, 8, 16)); net = (bs * mult).sum(1); net0 = float((b * mult).sum())
        for bb, l, h, m, nm in zip(b, lo, hi, mult, ('own square', 'ring 1 (5-10 km), per neighbour', 'ring 2 (10-15 km), per neighbour')):
            rows.append(dict(early=lab, term=nm, slope=bb, lo=l, hi=h, squares_in_ring=m))
        rows.append(dict(early=lab, term='net per early ha (own + 8 x ring 1 + 16 x ring 2)', slope=net0, lo=float(np.percentile(net, 2.5)), hi=float(np.percentile(net, 97.5)), squares_in_ring=np.nan))
        rows.append(dict(early=lab, term='displaced to rings per early ha', slope=net0 - b[0], lo=float(np.percentile(net - bs[:, 0], 2.5)), hi=float(np.percentile(net - bs[:, 0], 97.5)), squares_in_ring=np.nan))
        print(lab, np.round(b, 4), 'net', round(net0, 4), flush=True)
    R = pd.DataFrame(rows); R.to_csv(B.OUT + 'cb12_displace.csv', index=False); print(R.round(4).to_string(index=False))


if __name__ == '__main__':
    main()
