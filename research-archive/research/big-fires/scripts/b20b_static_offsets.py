"""Stage 3 of the static-source test (see b20_static_truth.py). For every VIIRS static-source detection: offset from the
Sentinel-2 truth in metres east/north, then
 - fixed bias per satellite x day/night (mean over sites, 95% CI by resampling sites),
 - the same in the satellite frame: along track (direction of flight) and across track (away from nadir, using which side
   of the ground track the site lay on, from local solar time vs the satellite's nadir local time),
 - by pixel width (view angle),
 - random part: per-detection scatter minus the in-pixel placement (pixel size^2/12 uniform, or /24 if detection favours the
   pixel centre) minus the size of the hot area,
 - what a single VIIRS point means on the ground: distance to the true source (median, 90th percentile).
Out: results/static_offsets.json, results/static_detections.csv.gz, figures/10_static_offsets.png"""
import json, numpy as np, pandas as pd
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'
SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/static'
# TRUTH: 'wt' (default) = heat-weighted centre of the hottest group, 'peak' = single hottest 20 m pixel, 'freq' = first-pass
# centroid of often-hot pixels (b20, pulled toward the warm halo). Quality filter uses nothing about the VIIRS offset:
# one dominant hot group (<30% of heat elsewhere within 1 km), clear heat (excess >= 0.05), VIIRS cluster not smeared (sd < 300 m).
import os as _os; TRUTH = _os.environ.get('TRUTH', 'wt'); QUAL = _os.environ.get('QUAL', '1') == '1'
T = pd.read_csv(f'{R}/static_sites.csv').merge(pd.read_csv(f'{R}/static_sites_peak.csv').drop(columns=['status']), on='site')
T = T[(T.status == 'ok') & T.wt_lon.notna()].copy()
if QUAL: T = T[(T.other_excess_share < 0.3) & (T.peak_excess >= 0.05) & (T.sx < 300) & (T.sy < 300)].copy()
if TRUTH != 'freq': T['truth_lon'], T['truth_lat'] = T[f'{TRUTH}_lon'], T[f'{TRUTH}_lat']
T['extent_e'] = T['extent_n'] = T.wt_sd_m if TRUTH != 'freq' else None
if TRUTH == 'freq': T['extent_e'], T['extent_n'] = pd.read_csv(f'{R}/static_sites.csv').set_index('site').loc[T.site, ['extent_e', 'extent_n']].values.T
SUF = '' if (TRUTH == 'wt' and QUAL) else f'_{TRUTH}{"" if QUAL else "_allsites"}'
P = pd.read_parquet(f'{SC}/static_points.parquet')
NAME = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}; P['satn'] = P.sat.map(NAME)
# ---- nadir local solar time per satellite x year x day/night, from ALL VIIRS points (pixel width is smallest at nadir)
import glob, os
AM = '/mnt/project-files/fire-alert-scars/alerts_mp'
A = pd.concat([pd.read_csv(f, usecols=['longitude', 'scan', 'acq_date', 'acq_time', 'daynight']).assign(sat=os.path.basename(f).split('_')[0]) for f in sorted(glob.glob(f'{AM}/viirs-*.csv'))], ignore_index=True)
def lst(df): return ((df.acq_time // 100 + (df.acq_time % 100) / 60 + df.longitude / 15) % 24)
A['lst'] = lst(A); A['year'] = A.acq_date.str[:4].astype(int)
nadir = {}
for (s, y, dn), g in A.groupby(['sat', 'year', 'daynight']):
    x = g.lst.values; x = np.where((dn == 'N') & (x > 12), x - 24, x)          # night around 01:30 -> keep continuous
    bins = np.arange(np.floor(x.min() * 12) / 12, x.max() + 1 / 12, 1 / 12)   # 5-minute bins
    if len(bins) < 5: continue
    idx = np.digitize(x, bins); med = pd.Series(g.scan.values).groupby(idx).median(); cnt = pd.Series(idx).value_counts()
    med = med[cnt.reindex(med.index).fillna(0) >= 50]
    if len(med) < 3: continue
    k = med.idxmin(); nadir[(s, y, dn)] = float(bins[k - 1] + 1 / 24) if k >= 1 else float(bins[0])
P['lst'] = lst(P); P['lst'] = np.where((P.daynight == 'N') & (P.lst > 12), P.lst - 24, P.lst)
P['nadir_lst'] = [nadir.get((s, y, dn), np.nan) for s, y, dn in zip(P.sat, P.year, P.daynight)]
P['side'] = np.sign(P.lst - P.nadir_lst)                      # +1 site east of the ground track, -1 west
P['dist_from_track_km'] = (P.lst - P.nadir_lst) * 15 * 111.32 * np.cos(np.radians(P.latitude))
# ---- offsets from truth
P = P.merge(T[['site', 'truth_lon', 'truth_lat', 'extent_e', 'extent_n', 'n_hot_group']], on='site', how='inner')
P['dE'] = (P.longitude - P.truth_lon) * np.cos(np.radians(P.truth_lat)) * 111320; P['dN'] = (P.latitude - P.truth_lat) * 110574
P = P[np.hypot(P.dE, P.dN) <= 1500].copy()
h = np.where(P.daynight == 'D', np.radians(-12), np.radians(192))             # ground-track heading: ascending NNW by day, descending SSW at night
P['along'] = P.dE * np.sin(h) + P.dN * np.cos(h)                             # + = ahead, in the direction of flight
pE, pN = np.cos(np.radians(12)), np.where(P.daynight == 'D', np.sin(np.radians(12)), -np.sin(np.radians(12)))   # east-pointing scan axis
P['across_east'] = P.dE * pE + P.dN * pN
P['away'] = P.across_east * P.side                                           # + = away from nadir
P['scan_m'] = P.scan * 1000; P['track_m'] = P.track * 1000; P['dist'] = np.hypot(P.dE, P.dN)
P['grp'] = P.satn + ' ' + np.where(P.daynight == 'D', 'day', 'night')
P.to_csv(f'{R}/static_detections{SUF}.csv.gz', index=False)
rng = np.random.default_rng(0)
def site_ci(g, col, B=1000):
    m = g.groupby('site')[col].mean(); v = m.values
    if len(v) < 3: return [round(float(v.mean()), 1) if len(v) else None, None, None]
    bs = [rng.choice(v, len(v)).mean() for _ in range(B)]
    return [round(float(v.mean()), 1), round(float(np.percentile(bs, 2.5)), 1), round(float(np.percentile(bs, 97.5)), 1)]
def block(g):
    o = dict(detections=int(len(g)), sites=int(g.site.nunique()), east_m=site_ci(g, 'dE'), north_m=site_ci(g, 'dN'),
             along_track_m=site_ci(g, 'along'), away_from_nadir_m=site_ci(g[g.side != 0], 'away'),
             dist_to_truth_median_m=round(float(g.dist.median())), dist_to_truth_p90_m=round(float(g.dist.quantile(.9))),
             pixel_width_median_m=round(float(g.scan_m.median())), pixel_length_median_m=round(float(g.track_m.median())))
    # random part per axis: residual about the group's fixed bias, in the satellite frame
    ra = g.along - g.along.mean(); rx = g.away - g.away.mean()
    var_a, var_x = float(np.var(ra)), float(np.var(rx))
    q_a_u, q_x_u = float((g.track_m ** 2).mean() / 12), float((g.scan_m ** 2).mean() / 12)
    ext = float(((g.extent_e ** 2 + g.extent_n ** 2) / 2).mean())
    def s(v): return round(float(np.sqrt(max(v, 0))))
    o['scatter_sd_along_m'] = s(var_a); o['scatter_sd_across_m'] = s(var_x)
    o['in_pixel_sd_along_m_uniform'] = s(q_a_u); o['in_pixel_sd_across_m_uniform'] = s(q_x_u); o['hot_area_sd_m'] = s(ext)
    o['pointing_error_sd_along_m'] = [s(var_a - q_a_u - ext), s(var_a - q_a_u / 2 - ext)]      # [uniform in-pixel, centre-favoured]
    o['pointing_error_sd_across_m'] = [s(var_x - q_x_u - ext), s(var_x - q_x_u / 2 - ext)]
    return o
out = dict(sites_used=int(P.site.nunique()), detections=int(len(P)), note='offset = VIIRS point minus Sentinel-2 truth; [mean, 95% CI by site]; '
           'pointing_error_sd = [if the source is equally likely anywhere in the pixel, if detection favours the pixel centre]',
           all=block(P), by_group={k: block(g) for k, g in P.groupby('grp')})
P['wbin'] = pd.cut(P.scan_m, [0, 420, 520, 650, 900], labels=['<=420 m (near nadir)', '420-520 m', '520-650 m', '>650 m (swath edge)'])
out['by_pixel_width'] = {str(k): block(g) for k, g in P.groupby('wbin', observed=True)}
out['by_side_of_track'] = {('east of track' if k > 0 else 'west of track'): block(g) for k, g in P[P.side != 0].groupby('side')}
P['far'] = np.abs(P.dist_from_track_km) > 300
out['by_side_far_from_nadir'] = {('east' if k > 0 else 'west'): dict(east_m=site_ci(g, 'dE'), north_m=site_ci(g, 'dN'), away_m=site_ci(g, 'away'), n=int(len(g)))
                                  for k, g in P[(P.side != 0) & P.far].groupby('side')}
# compact sites only (hot area small) as a robustness check
C = P[np.sqrt((P.extent_e ** 2 + P.extent_n ** 2) / 2) < 60]
out['compact_sites_only'] = dict(sites=int(C.site.nunique()), by_group={k: dict(east_m=site_ci(g, 'dE'), north_m=site_ci(g, 'dN'), n=int(len(g))) for k, g in C.groupby('grp')})
# year halves stability
P['half'] = np.where(P.year % 2 == 0, 'even years', 'odd years')
out['even_vs_odd_years'] = {f'{k[0]} | {k[1]}': dict(east_m=site_ci(g, 'dE', 300), north_m=site_ci(g, 'dN', 300), n=int(len(g))) for k, g in P.groupby(['grp', 'half'])}
out['truth'] = TRUTH; out['site_ids'] = sorted(map(int, T.site)); json.dump(out, open(f'{R}/static_offsets{SUF}.json', 'w'), indent=1); print(json.dumps({k: out[k] for k in ['sites_used', 'detections', 'all']}, indent=1))
# ---- figure
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 3, figsize=(14, 4.6))
cols = {'S-NPP': 'tab:blue', 'NOAA-20': 'tab:orange', 'NOAA-21': 'tab:green'}
for k, g in P.groupby('grp'):
    sat, dn = k.split(' '); m = g.groupby('site')[['dE', 'dN']].mean()
    ax[0].scatter(m.dE, m.dN, s=8, alpha=.35, c=cols[sat], marker='o' if dn == 'night' else '^')
    ax[0].errorbar(g.groupby('site').dE.mean().mean(), g.groupby('site').dN.mean().mean(), fmt='o' if dn == 'night' else '^', ms=10, mec='k', c=cols[sat], label=k)
ax[0].axhline(0, c='k', lw=.5); ax[0].axvline(0, c='k', lw=.5); ax[0].set_xlim(-300, 300); ax[0].set_ylim(-300, 300); ax[0].set_aspect('equal')
ax[0].set_xlabel('east (m)'); ax[0].set_ylabel('north (m)'); ax[0].set_title('mean VIIRS position minus true source\n(small = one site, large = all sites)'); ax[0].legend(fontsize=7)
ax[1].hist(P.dist, bins=np.arange(0, 1001, 25), color='grey'); ax[1].axvline(P.dist.median(), c='r'); ax[1].set_xlabel('one VIIRS point to the true source (m)'); ax[1].set_title(f'median {P.dist.median():.0f} m, 90% within {P.dist.quantile(.9):.0f} m')
wb = P.groupby('wbin', observed=True).agg(d=('dist', 'median'), w=('scan_m', 'median'))
ax[2].plot(wb.w, wb.d, 'o-', label='observed median distance'); ax[2].plot(wb.w, 0.38 * wb.w, 's--', label='if only in-pixel placement (0.38 x width)')
ax[2].set_xlabel('pixel width along scan (m)'); ax[2].set_ylabel('m'); ax[2].legend(fontsize=8); ax[2].set_title('distance grows with pixel size')
fig.tight_layout(); fig.savefig(f'{FG}/10_static_offsets{SUF}.png', dpi=130)
