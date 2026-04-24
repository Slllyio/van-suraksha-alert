import { motion, staggerContainer, fadeUp, useAccessibleVariants, transitions } from '../lib/motion';
import { colors, layout as layoutTokens } from '../designTokens';
import StatusBadge from '../components/StatusBadge';
import ConfidenceTier from '../components/ConfidenceTier';

// Placeholder — 12 demo divisions. Real data from /api/division-overview.
const DEMO_DIVISIONS = [
  { name: 'Betul',      crit: 8,  alert: 22, watch: 51, tier: 'HIGH' as const },
  { name: 'Guna',       crit: 6,  alert: 18, watch: 42, tier: 'HIGH' as const },
  { name: 'Hoshangabad',crit: 5,  alert: 14, watch: 38, tier: 'MEDIUM' as const },
  { name: 'Chhindwara', crit: 4,  alert: 12, watch: 34, tier: 'MEDIUM' as const },
  { name: 'Seoni',      crit: 3,  alert: 9,  watch: 28, tier: 'MEDIUM' as const },
  { name: 'Mandla',     crit: 2,  alert: 7,  watch: 22, tier: 'LOW'    as const },
  { name: 'Dindori',    crit: 2,  alert: 6,  watch: 20, tier: 'LOW'    as const },
  { name: 'Balaghat',   crit: 1,  alert: 5,  watch: 17, tier: 'MEDIUM' as const },
  { name: 'Sidhi',      crit: 1,  alert: 4,  watch: 14, tier: 'LOW'    as const },
  { name: 'Shahdol',    crit: 0,  alert: 3,  watch: 11, tier: 'MEDIUM' as const },
  { name: 'Umaria',     crit: 0,  alert: 2,  watch: 9,  tier: 'LOW'    as const },
  { name: 'Katni',      crit: 0,  alert: 1,  watch: 6,  tier: 'LOW'    as const },
];

export default function DivisionsTab() {
  const container = useAccessibleVariants(staggerContainer(0.04));
  const item = useAccessibleVariants(fadeUp);

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: 16,
        padding: 24,
        overflowY: 'auto',
        height: '100%',
      }}
    >
      {DEMO_DIVISIONS.map((d) => (
        <motion.article
          key={d.name}
          variants={item}
          whileHover={{
            y: -2,
            backgroundColor: colors.bg.raised,
            borderColor: colors.border.base,
          }}
          transition={transitions.fast}
          style={{
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: layoutTokens.cardPadding,
            padding: 18,
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ fontSize: 15, fontWeight: 500, color: colors.text.primary }}>
              {d.name}
            </h3>
            <ConfidenceTier tier={d.tier} size="sm" />
          </div>

          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {d.crit > 0 && <StatusBadge band="critical" count={d.crit} size="sm" />}
            {d.alert > 0 && <StatusBadge band="alert" count={d.alert} size="sm" />}
            {d.watch > 0 && <StatusBadge band="watch" count={d.watch} size="sm" />}
          </div>

          <div
            className="mono"
            style={{
              fontSize: 11,
              color: colors.text.tertiary,
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: 6,
              paddingTop: 10,
              borderTop: `1px solid ${colors.border.subtle}`,
            }}
          >
            <span>Beats: 103</span>
            <span>Hawkes λ: 0.42</span>
          </div>
        </motion.article>
      ))}
    </motion.div>
  );
}
