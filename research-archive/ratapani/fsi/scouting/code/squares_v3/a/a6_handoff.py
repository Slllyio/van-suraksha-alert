"""A6: drop-in correction files for the per-fire thread (r20_b): class speed factors and the per-pair edge term."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
import pandas as pd
T = pd.read_csv(f'{OUT}/a1_corrected_speeds.csv').set_index(['dn', 'set'])
d, n = T.loc[('D', 'fires, all')], T.loc[('N', 'fires, all')]
out = dict(day_factor=round(d.corr_m_h / d.raw_m_h, 3), night_factor=round(n.corr_m_h / n.raw_m_h, 3),
           day_m_h=float(d.corr_m_h), night_m_h=float(n.corr_m_h),
           ci=dict(day=[float(d.corr_lo), float(d.corr_hi)], night=[float(n.corr_lo), float(n.corr_hi)]),
           v2_day_m_h=float(d.raw_m_h), v2_night_m_h=float(n.raw_m_h),
           note=('Pooled outward centre speed of all MP VIIRS small-gap fire pairs after removing the edge-reach (pixel size), '
                 'noise-coupling, view-angle and sensor-order terms (coefficients fitted on the other season half). '
                 'Per-pair term: edge_term_by_pair.parquet (pair_row = pairs.parquet row; subtract edge_m from the clipped p_out). '
                 'The night factor is large because v2 night was small; absolute night CI is ~8-12 m/h. Centre speed, not front speed.'))
json.dump(out, open(f'{OUT}/class_speed_correction.json', 'w'), indent=1); print(out)
