"""Score this thread's cell-day rates with the pipeline thread's rule (/mnt/project-files/ratapani/scoring/SCORING.md):
positive cell-days (first burn per cell-season, H=2), valid = t+2 <= last clear look, 68 pipeline pseudo-beats,
recall = hits / valid positive cell-days at 5 (and 10) listed per beat per issue day (Feb 1 - Jun 20).
Usage: pipeline_score.py <daily_pred.parquet> <out.json> [score_cols comma-separated]
"""
import sys, json
import numpy as np, pandas as pd

LAB = '/mnt/project-files/research/ratapani-burn-labels/'
SC = '/mnt/project-files/ratapani/scoring/'
H = 2


def labels(seasons):
    """Return DataFrame (season, date, cell_id, pos) of VALID cell-days for the given seasons, pipeline rule, MODE=first."""
    bw = pd.read_csv(LAB + 'burn_windows.csv', parse_dates=['window_start', 'window_end'])
    cc = pd.read_parquet(LAB + 'clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc['date'])
    out = []
    for Y in seasons:
        days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20')
        last = cc[(cc.season == Y) & (cc.clear_frac >= 0.5)].groupby('cell_id').date.max()
        cells = np.arange(3614)
        lastd = last.reindex(cells)
        # valid where t + H <= last clear look
        T = len(days); valid = np.zeros((T, 3614), bool); pos = np.zeros((T, 3614), bool)
        dnum = (days - days[0]).days.values
        lim = ((lastd - days[0]).dt.days - H).values  # last valid day index
        for c in cells:
            if np.isfinite(lim[c]) and lim[c] >= 0:
                valid[:int(min(lim[c], T - 1)) + 1, c] = True
        w = bw[(bw.season == Y) & (bw.burned == 1)].sort_values(['cell_id', 'window_end'])
        for c, g in w.groupby('cell_id'):
            s, e = g.window_start.iloc[0], g.window_end.iloc[0]       # first burn only
            a = (s - days[0]).days - H + 1; b = (e - days[0]).days - 1
            a0, b0 = max(a, 0), min(b, T - 1)
            if b0 >= a0:
                pos[a0:b0 + 1, c] = True; valid[a0:b0 + 1, c] = True
            ei = (e - days[0]).days
            if ei <= T - 1:
                valid[max(ei, 0):, c] = False; pos[max(ei, 0):, c] = False
        ti, ci = np.nonzero(valid)
        out.append(pd.DataFrame(dict(season=Y, date=days[ti], cell_id=ci, pos=pos[ti, ci])))
    return pd.concat(out, ignore_index=True)


def score(pred, lab, cols, budgets=(5, 10)):
    pb = pd.read_csv(SC + 'pseudo_beats_pipeline.csv').set_index('cell_id').pseudo_beat
    lab = lab.copy(); lab['pb'] = lab.cell_id.map(pb).values
    m = lab.merge(pred[['season', 'date', 'cell_id'] + cols], on=['season', 'date', 'cell_id'], how='left')
    res = {'valid_cell_days': int(len(m)), 'positives': int(m.pos.sum()), 'base_rate': round(float(m.pos.mean()), 4)}
    rng = np.random.default_rng(0); m['random'] = rng.random(len(m))
    for col in cols + ['random']:
        s = m[col].fillna(-np.inf)
        r = s.groupby([m.season, m.date, m.pb]).rank('first', ascending=False)
        for B in budgets:
            hit = m.pos[r <= B].sum(); ndays = m.groupby(['season', 'date']).ngroups
            res[f'{col}_recall@{B}'] = round(float(hit / m.pos.sum()), 4)
            res[f'{col}_precision@{B}'] = round(float(hit / (B * 68 * ndays)), 4)
        # per-season recall@5
        for y, g in m.groupby('season'):
            rr = g[col].fillna(-np.inf).groupby([g.date, g.pb]).rank('first', ascending=False)
            res[f'{col}_recall@5_{y}'] = round(float(g.pos[rr <= 5].sum() / g.pos.sum()), 4)
    return res


if __name__ == '__main__':
    pred = pd.read_parquet(sys.argv[1]); pred['date'] = pd.to_datetime(pred['date'])
    cols = sys.argv[3].split(',') if len(sys.argv) > 3 else ['combined', 'two_model', 'ignition_feats']
    lab = labels(sorted(pred.season.unique()))
    res = score(pred, lab, cols)
    json.dump(res, open(sys.argv[2], 'w'), indent=1); print(json.dumps(res, indent=1))
