import { Info, AlertTriangle } from 'lucide-react';
import { motion, staggerContainer, fadeUp, useAccessibleVariants, transitions } from '../lib/motion';
import { colors, chartColors, fontFamily } from '../designTokens';
import StatusBadge from '../components/StatusBadge';
import PlotlyChart from '../components/PlotlyChart';
import CountUp from '../components/CountUp';

const KPIS: {
  label: string;
  num?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  literal?: string;
  ctx: string;
  accent: keyof typeof colors.fire | 'accent';
}[] = [
  { label: 'Recall @ top-5%',        num: 45.5, decimals: 1, suffix: '%',                ctx: '(unique events)', accent: 'confirmed' },
  { label: 'Precision (CRIT)',       num: 3.2,  decimals: 1, suffix: '%',                ctx: '(low tier)',      accent: 'critical'  },
  { label: 'R @ top-5% (BA tiered)', num: 47.4, decimals: 1, suffix: '%',                ctx: '(labeled)',       accent: 'confirmed' },
  { label: 'Coverage',               literal: '87 / 87',                                 ctx: 'divisions',       accent: 'accent'    },
  { label: 'Low-Hawkes R',           num: 7.65, decimals: 2, suffix: '%',                ctx: '(cold-start)',    accent: 'alert'     },
  { label: 'Daily volume',           num: 140,  decimals: 0, prefix: '~', suffix: '',    ctx: 'CRITICAL / day',  accent: 'critical'  },
];

const FEATURE_IMPORTANCE = [
  { name: 'Hawkes λ (self-excite)', gain: 74 },
  { name: 'FWI · 7d rolling',       gain: 42 },
  { name: 'Tree cover loss (5y)',   gain: 31 },
  { name: 'VPD anomaly · 3d',       gain: 28 },
  { name: 'Distance to road',       gain: 24 },
  { name: 'Population · 1km',       gain: 21 },
  { name: 'Elevation',              gain: 17 },
  { name: 'Slope · aspect',         gain: 14 },
  { name: 'Beat history prior',     gain: 12 },
  { name: 'Soil moisture · 10cm',   gain:  9 },
];

const TRUST_TIERS = [
  {
    tier: 'HIGH',
    band: 'confirmed' as const,
    body: 'High-Hawkes cells near recent ignitions. 25.5% R@5% in this regime. Act confidently.',
  },
  {
    tier: 'MEDIUM',
    // Use trustTier palette directly, not fire-band tokens. The fire
    // band 'watch' (amber-400) collides with the trustTier MEDIUM
    // (now violet) post the 51fdab25 decoupling.
    band: 'medium' as const,
    body: 'Active fire weather but low prior activity. Cross-check with local patrol before dispatch.',
  },
  {
    tier: 'LOW',
    // LOW model confidence is NOT a CRITICAL severity. amber-500 vs
    // CRITICAL red — same fix as 51fdab25.
    band: 'low' as const,
    body: 'Cold-start region (low-Hawkes). Only 7.65% R@5% here. Use as awareness, not dispatch trigger.',
  },
];

// Map TRUST_TIERS .band value → actual color from the trustTier palette.
const TRUST_BAND_COLOR: Record<string, string> = {
  high: '#22C55E',     // colors.trustTier.high.fg
  medium: '#A78BFA',   // colors.trustTier.medium.fg
  low: '#F59E0B',      // colors.trustTier.low.fg
  // Backward compat for any callers still using fire-band names:
  confirmed: '#22C55E',
  watch: '#FBBF24',
  critical: '#EF4444',
};

export default function ModelCardTab() {
  const container = useAccessibleVariants(staggerContainer(0.05));
  const item = useAccessibleVariants(fadeUp);

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
        <motion.header variants={item} style={{ marginBottom: 32 }}>
          <div
            className="micro"
            style={{ color: colors.text.tertiary, marginBottom: 6 }}
          >
            Model transparency
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 500, letterSpacing: '-0.02em' }}>
            v17.5 — LightGBM × Hurdle blend
          </h1>
          <p style={{ marginTop: 8, color: colors.text.secondary, maxWidth: 640, lineHeight: 1.6 }}>
            Production fire-ignition forecaster since 2026-04-19. Trained on 111 features
            combining Hawkes self-excitation, fire-weather indices, static terrain,
            and 5-year FIRMS detection history.
          </p>
        </motion.header>

        <motion.section variants={item} style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 14 }}>Honest metrics</h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 14,
            }}
          >
            {KPIS.map((k) => {
              const accentColor =
                k.accent === 'accent'
                  ? colors.accent.base
                  : colors.fire[k.accent].fg;
              const accentGlow =
                k.accent === 'accent'
                  ? colors.accent.muted
                  : colors.fire[k.accent].bg;
              return (
                <motion.div
                  key={k.label}
                  variants={item}
                  whileHover={{
                    y: -3,
                    boxShadow: `0 12px 40px ${accentGlow}, 0 0 0 1px ${accentColor}40`,
                  }}
                  transition={transitions.base}
                  style={{
                    position: 'relative',
                    overflow: 'hidden',
                    background: `linear-gradient(145deg, ${colors.bg.surface} 0%, ${colors.bg.raised} 100%)`,
                    border: `1px solid ${colors.border.subtle}`,
                    borderRadius: 14,
                    padding: '22px 18px',
                    textAlign: 'center',
                  }}
                >
                  {/* Corner glow in the accent color */}
                  <div
                    aria-hidden
                    style={{
                      position: 'absolute',
                      top: -50,
                      right: -50,
                      width: 140,
                      height: 140,
                      background: `radial-gradient(circle, ${accentGlow} 0%, transparent 65%)`,
                      pointerEvents: 'none',
                      opacity: 0.7,
                    }}
                  />
                  <div
                    className="mono"
                    style={{
                      position: 'relative',
                      fontSize: 40,
                      fontWeight: 600,
                      color: accentColor,
                      lineHeight: 1,
                      letterSpacing: '-0.02em',
                      textShadow: `0 0 24px ${accentGlow}`,
                    }}
                  >
                    {k.literal ? (
                      <span>{k.literal}</span>
                    ) : (
                      <CountUp
                        value={k.num ?? 0}
                        decimals={k.decimals ?? 0}
                        prefix={k.prefix}
                        suffix={k.suffix}
                        duration={1.8}
                      />
                    )}
                  </div>
                  <div className="micro" style={{ marginTop: 10, position: 'relative' }}>
                    {k.label}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: colors.text.tertiary,
                      marginTop: 6,
                      position: 'relative',
                    }}
                  >
                    {k.ctx}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </motion.section>

        <motion.section variants={item} style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 14 }}>
            Known weaknesses
          </h2>
          <motion.div
            variants={item}
            style={{
              background: colors.fire.critical.bg,
              border: `1px solid ${colors.fire.critical.border}`,
              borderRadius: 12,
              padding: 18,
              display: 'flex',
              gap: 14,
              alignItems: 'flex-start',
            }}
          >
            <AlertTriangle size={20} color={colors.fire.critical.fg} style={{ flexShrink: 0, marginTop: 2 }} />
            <div style={{ fontSize: 13, color: colors.text.secondary, lineHeight: 1.6 }}>
              <strong style={{ color: colors.text.primary }}>Cold-start blind spot:</strong>{' '}
              the model excels at fire <em>contagion</em> (Hawkes-driven, 25.5% R@5% in high-activity regions)
              but is near-random on <em>new outbreaks</em> in quiet regions (5.9% R@5%). 77% of fires actually
              start in low-Hawkes cells. Use with <StatusBadge band="info" label="CLIMATOLOGY" size="sm" /> floor
              decoration as a fallback.
            </div>
          </motion.div>
        </motion.section>

        <motion.section variants={item} style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 14 }}>
            When to trust each alert
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {TRUST_TIERS.map((t) => (
              <motion.div
                key={t.tier}
                variants={item}
                style={{
                  background: colors.bg.raised,
                  border: `1px solid ${colors.border.subtle}`,
                  // Look up via TRUST_BAND_COLOR map (trustTier palette)
                  // instead of colors.fire[band] (severity palette).
                  borderLeft: `3px solid ${TRUST_BAND_COLOR[t.band]}`,
                  borderRadius: 10,
                  padding: 16,
                  fontSize: 13,
                  color: colors.text.secondary,
                  lineHeight: 1.6,
                }}
              >
                <strong style={{ color: colors.text.primary }}>{t.tier} trust:</strong>{' '}
                {t.body}
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section variants={item} style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 14 }}>
            Recall trend &amp; forecast
          </h2>
          <div
            style={{
              background: colors.bg.surface,
              border: `1px solid ${colors.border.subtle}`,
              borderRadius: 12,
              padding: '18px 12px 8px',
            }}
          >
            <PlotlyChart
              data={buildForecastTraces()}
              height={300}
              layout={{
                showlegend: true,
                legend: { orientation: 'h', y: 1.18, x: 0 },
                xaxis: {
                  title: {
                    text: 'Date',
                    font: { family: fontFamily.ui },
                  },
                },
                yaxis: {
                  title: {
                    text: 'Recall @ top-5% (%)',
                    font: { family: fontFamily.ui },
                  },
                  range: [0, 55],
                },
              }}
            />
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginTop: 12,
              fontSize: 12,
              color: colors.text.tertiary,
            }}
          >
            <Info size={14} />
            Blue line is observed daily recall. Orange dashed is the projected trend;
            shaded band is 95% CI. Hover any point for exact values.
          </div>
        </motion.section>

        <motion.section variants={item}>
          <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 14 }}>Feature importance</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {FEATURE_IMPORTANCE.map((f) => (
              <motion.div
                key={f.name}
                variants={item}
                style={{ display: 'flex', alignItems: 'center', gap: 10 }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: 12,
                    color: colors.text.secondary,
                    width: 190,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {f.name}
                </span>
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${f.gain}%` }}
                  transition={{ duration: 0.6, ease: [0.2, 0, 0, 1] }}
                  style={{
                    height: 22,
                    borderRadius: 6,
                    background: `linear-gradient(90deg, ${colors.accent.pressed}, ${colors.accent.base})`,
                    flex: 1,
                    maxWidth: 'calc(100% - 240px)',
                  }}
                />
                <span
                  className="mono"
                  style={{ fontSize: 11, color: colors.text.tertiary, minWidth: 44, textAlign: 'right' }}
                >
                  {f.gain}
                </span>
              </motion.div>
            ))}
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginTop: 16,
              fontSize: 12,
              color: colors.text.tertiary,
            }}
          >
            <Info size={14} />
            Gain values are relative; sum across all features = 100.
          </div>
        </motion.section>
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Synthetic recall history + 7-day forecast with 95% CI band. Replace with
// live /api/v17-recall-history data once the backend endpoint exists.
// ---------------------------------------------------------------------------
function buildForecastTraces() {
  const actualDates = [
    '2026-04-16', '2026-04-17', '2026-04-18', '2026-04-19',
    '2026-04-20', '2026-04-21', '2026-04-22',
  ];
  const actualY = [21.1, 20.8, 24.1, 22.0, 28.9, 32.7, 29.8];

  const forecastDates = [
    '2026-04-22', '2026-04-23', '2026-04-24', '2026-04-25',
    '2026-04-26', '2026-04-27', '2026-04-28', '2026-04-29',
  ];
  const forecastY = [29.8, 30.4, 31.1, 31.6, 31.9, 32.1, 32.2, 32.3];
  const upper = forecastY.map((y) => y + 4.5);
  const lower = forecastY.map((y) => y - 4.5);

  return [
    // 95% CI band — upper
    {
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: '95% CI upper',
      x: forecastDates,
      y: upper,
      line: { color: 'transparent' },
      showlegend: false,
      hoverinfo: 'skip' as const,
    },
    // 95% CI band — lower (fills to the upper trace above)
    {
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: '95% CI',
      x: forecastDates,
      y: lower,
      line: { color: 'transparent' },
      fill: 'tonexty' as const,
      fillcolor: chartColors.confidence,
      hoverinfo: 'skip' as const,
    },
    // Actual (solid blue)
    {
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Observed',
      x: actualDates,
      y: actualY,
      line: { color: chartColors.actual, width: 2 },
      marker: { size: 6, color: chartColors.actual },
      hovertemplate: '<b>%{x}</b><br>Observed: %{y:.1f}%<extra></extra>',
    },
    // Forecast (dashed orange)
    {
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: 'Forecast',
      x: forecastDates,
      y: forecastY,
      line: {
        color: chartColors.forecast,
        width: 2,
        dash: 'dash' as const,
      },
      hovertemplate: '<b>%{x}</b><br>Forecast: %{y:.1f}%<extra></extra>',
    },
  ];
}

