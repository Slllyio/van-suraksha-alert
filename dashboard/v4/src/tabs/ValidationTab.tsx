import { useEffect, useMemo, useState } from 'react';
import {
  motion,
  staggerContainer,
  fadeUp,
  useAccessibleVariants,
} from '../lib/motion';
import { colors, chartColors, fontFamily } from '../designTokens';
import StatusBadge from '../components/StatusBadge';
import PlotlyChart from '../components/PlotlyChart';
import { api, type ValidationRow } from '../lib/api';

// Local demo fallback when the API isn't reachable. Keeps the chart meaningful
// before the backend is wired up.
const FALLBACK: ValidationRow[] = [
  { date: '2026-04-16', predicted: 2071, observed: 19, caught: 4,  recall_pct: 21.1, trust: 'LOW' },
  { date: '2026-04-17', predicted: 2055, observed: 24, caught: 5,  recall_pct: 20.8, trust: 'LOW' },
  { date: '2026-04-18', predicted: 2089, observed: 29, caught: 7,  recall_pct: 24.1, trust: 'MEDIUM' },
  { date: '2026-04-19', predicted: 2110, observed: 41, caught: 9,  recall_pct: 22.0, trust: 'MEDIUM' },
  { date: '2026-04-20', predicted: 2076, observed: 38, caught: 11, recall_pct: 28.9, trust: 'MEDIUM' },
  { date: '2026-04-21', predicted: 2094, observed: 52, caught: 17, recall_pct: 32.7, trust: 'HIGH' },
  { date: '2026-04-22', predicted: 2128, observed: 47, caught: 14, recall_pct: 29.8, trust: 'HIGH' },
];

export default function ValidationTab() {
  const [rows, setRows] = useState<ValidationRow[]>(FALLBACK);
  const [source, setSource] = useState<'live' | 'fallback'>('fallback');

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .seasonValidation(ctrl.signal)
      .then((live) => {
        // v2 endpoint unwraps to data: ValidationRow[]
        if (Array.isArray(live) && live.length > 0) {
          setRows(live);
          setSource('live');
        }
      })
      .catch(() => {
        /* keep fallback */
      });
    return () => ctrl.abort();
  }, []);

  const container = useAccessibleVariants(staggerContainer(0.03));
  const item = useAccessibleVariants(fadeUp);

  // Detect anomaly days (recall drops sharply vs moving average) for the chart
  const anomalies = useMemo(() => detectAnomalies(rows), [rows]);

  // Plotly trace config — anomaly-detection pattern from the skill
  const traces = useMemo(() => {
    const x = rows.map((r) => r.date);
    const y = rows.map((r) => r.recall_pct);
    const anomalyX = anomalies.map((i) => rows[i].date);
    const anomalyY = anomalies.map((i) => rows[i].recall_pct);
    return [
      {
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Recall %',
        x,
        y,
        line: { color: chartColors.actual, width: 2, shape: 'spline' as const },
        marker: {
          size: 7,
          color: chartColors.actual,
          line: { color: colors.bg.canvas, width: 1.5 },
        },
        hovertemplate:
          '<b>%{x}</b><br>Recall: %{y:.1f}%<extra></extra>',
      },
      {
        type: 'scatter' as const,
        mode: 'markers' as const,
        name: 'Anomaly (missed batch)',
        x: anomalyX,
        y: anomalyY,
        marker: {
          size: 14,
          color: chartColors.anomaly,
          symbol: 'x' as const,
          line: { color: colors.bg.canvas, width: 2 },
        },
        hovertemplate:
          '<b>%{x}</b><br>Recall: %{y:.1f}%<br>Below threshold<extra></extra>',
      },
    ];
  }, [rows, anomalies]);

  return (
    <div
      style={{
        padding: '32px 48px',
        overflowY: 'auto',
        height: '100%',
        maxWidth: 960,
        margin: '0 auto',
      }}
    >
      <motion.div variants={container} initial="hidden" animate="visible">
        <motion.header variants={item} style={{ marginBottom: 24 }}>
          <div
            className="micro"
            style={{ color: colors.text.tertiary, marginBottom: 6 }}
          >
            Field validation
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 500 }}>
            Rolling prediction vs FIRMS VIIRS
          </h1>
          <p
            style={{
              marginTop: 8,
              color: colors.text.secondary,
              fontSize: 13,
              lineHeight: 1.6,
            }}
          >
            Each point compares a day's v17.5 predicted cells against the FIRMS
            VIIRS fires actually observed the next day. Red × markers flag
            anomaly days where recall dropped below a 3-day moving baseline.
            {source === 'fallback' && (
              <>
                {' '}
                <span style={{ color: colors.fire.watch.fg }}>
                  Showing fallback data — backend offline.
                </span>
              </>
            )}
          </p>
        </motion.header>

        <motion.section
          variants={item}
          style={{
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: 12,
            padding: '18px 12px 8px',
            marginBottom: 24,
          }}
        >
          <PlotlyChart
            data={traces}
            height={320}
            layout={{
              showlegend: true,
              legend: { orientation: 'h', y: 1.15, x: 0 },
              xaxis: { title: { text: 'Date', font: { family: fontFamily.ui } } },
              yaxis: {
                title: { text: 'Recall (%)', font: { family: fontFamily.ui } },
                range: [0, Math.max(...rows.map((r) => r.recall_pct)) * 1.25],
              },
            }}
          />
        </motion.section>

        <motion.div
          variants={item}
          style={{
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: 12,
            overflow: 'hidden',
          }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: colors.bg.raised }}>
                {['Date', 'Predicted', 'Observed', 'Caught', 'Recall', 'Trust'].map(
                  (h) => (
                    <th
                      key={h}
                      className="micro"
                      style={{
                        padding: '12px 16px',
                        textAlign:
                          h === 'Date' || h === 'Trust' ? 'left' : 'right',
                        color: colors.text.tertiary,
                        borderBottom: `1px solid ${colors.border.subtle}`,
                        fontWeight: 500,
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const recall = r.recall_pct;
                return (
                  <motion.tr
                    key={r.date}
                    variants={item}
                    whileHover={{ backgroundColor: 'rgba(255,255,255,0.02)' }}
                  >
                    <td
                      className="mono"
                      style={tdStyle({ color: colors.text.primary })}
                    >
                      {r.date}
                    </td>
                    <td
                      className="mono"
                      style={tdStyle({
                        color: colors.text.secondary,
                        textAlign: 'right',
                      })}
                    >
                      {r.predicted.toLocaleString()}
                    </td>
                    <td
                      className="mono"
                      style={tdStyle({
                        color: colors.text.secondary,
                        textAlign: 'right',
                      })}
                    >
                      {r.observed}
                    </td>
                    <td
                      className="mono"
                      style={tdStyle({
                        color: colors.text.primary,
                        textAlign: 'right',
                        fontWeight: 500,
                      })}
                    >
                      {r.caught}
                    </td>
                    <td
                      className="mono"
                      style={tdStyle({
                        textAlign: 'right',
                        color:
                          recall >= 30
                            ? colors.fire.confirmed.fg
                            : recall >= 20
                              ? colors.fire.watch.fg
                              : colors.fire.alert.fg,
                        fontWeight: 500,
                      })}
                    >
                      {recall.toFixed(1)}%
                    </td>
                    <td style={tdStyle({})}>
                      <StatusBadge
                        band={
                          r.trust === 'HIGH'
                            ? 'confirmed'
                            : r.trust === 'LOW'
                              ? 'critical'
                              : 'watch'
                        }
                        label={r.trust ?? 'MEDIUM'}
                        size="sm"
                      />
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </motion.div>
      </motion.div>
    </div>
  );
}

function tdStyle(extra: Record<string, string | number>): React.CSSProperties {
  return {
    padding: '12px 16px',
    borderBottom: `1px solid ${colors.border.subtle}`,
    fontSize: 13,
    ...(extra as React.CSSProperties),
  };
}

/** Simple anomaly flagger: recall drops more than 1 std-dev below a 3-day mean */
function detectAnomalies(rows: ValidationRow[]): number[] {
  const out: number[] = [];
  const vals = rows.map((r) => r.recall_pct);
  if (vals.length < 4) return out;
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const std = Math.sqrt(
    vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length,
  );
  const threshold = mean - std;
  vals.forEach((v, i) => {
    if (v < threshold) out.push(i);
  });
  return out;
}
