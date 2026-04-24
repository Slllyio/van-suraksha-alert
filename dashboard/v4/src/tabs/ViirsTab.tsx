import { useEffect, useState } from 'react';
import { Calendar, Download, Loader2 } from 'lucide-react';
import { motion, fadeUp, transitions, useAccessibleVariants } from '../lib/motion';
import { colors } from '../designTokens';
import StatusBadge from '../components/StatusBadge';
import CountUp from '../components/CountUp';

import { api } from '../lib/api';

export default function ViirsTab() {
  const [from, setFrom] = useState('2026-04-17');
  const [to, setTo] = useState('2026-04-24');
  const [firesCount, setFiresCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const item = useAccessibleVariants(fadeUp);

  const loadFires = async () => {
    setLoading(true);
    try {
      const env = await api.viirsFires(from, to);
      setFiresCount(env.meta?.total ?? env.data?.length ?? 0);
    } catch {
      setFiresCount(null);
    } finally {
      setLoading(false);
    }
  };

  // Auto-load on first mount
  useEffect(() => { loadFires(); /* eslint-disable-next-line */ }, []);

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
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.06 } },
        }}
      >
        <motion.header variants={item} style={{ marginBottom: 24 }}>
          <div className="micro" style={{ color: colors.text.tertiary, marginBottom: 6 }}>
            Historical detections
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 500 }}>VIIRS Fire Viewer</h1>
          <p style={{ marginTop: 8, color: colors.text.secondary, fontSize: 13 }}>
            Forest-clipped NASA FIRMS VIIRS active fire detections. 1.35M historical rows
            covering 2014–2026. Spatial join to MP beat polygons removes ~75% of non-forest pixels.
          </p>
        </motion.header>

        <motion.section
          variants={item}
          style={{
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: 12,
            padding: 20,
            marginBottom: 20,
            display: 'flex',
            alignItems: 'flex-end',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <DateField label="From" value={from} onChange={setFrom} />
          <DateField label="To" value={to} onChange={setTo} />
          <motion.button
            onClick={loadFires}
            disabled={loading}
            whileHover={{ backgroundColor: colors.accent.hover }}
            whileTap={{ scale: 0.97 }}
            transition={transitions.fast}
            style={{
              padding: '10px 20px',
              borderRadius: 999,
              background: colors.accent.base,
              color: colors.text.onAccent,
              fontSize: 13,
              fontWeight: 500,
              letterSpacing: '0.01em',
              cursor: loading ? 'wait' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? (
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                style={{ display: 'inline-flex' }}
              >
                <Loader2 size={14} />
              </motion.span>
            ) : (
              <Calendar size={14} />
            )}
            Load detections
          </motion.button>
          <motion.button
            whileHover={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
            whileTap={{ scale: 0.97 }}
            transition={transitions.fast}
            style={{
              padding: '10px 16px',
              borderRadius: 999,
              background: 'transparent',
              border: `1px solid ${colors.border.base}`,
              color: colors.text.secondary,
              fontSize: 13,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Download size={14} />
            CSV export
          </motion.button>
        </motion.section>

        <motion.section
          variants={item}
          style={{
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: 12,
            padding: 32,
            textAlign: 'center',
          }}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={transitions.slow}
          >
            <div
              className="mono"
              style={{
                fontSize: 56,
                fontWeight: 600,
                color: colors.fire.confirmed.fg,
                textShadow: `0 0 24px ${colors.fire.confirmed.bg}`,
                lineHeight: 1,
                letterSpacing: '-0.02em',
              }}
            >
              {firesCount === null ? '—' : <CountUp value={firesCount} duration={1.6} />}
            </div>
            <div className="micro" style={{ marginTop: 10 }}>forest-clipped fire pixels</div>
            <div style={{ marginTop: 14, color: colors.text.tertiary, fontSize: 12 }}>
              FIRMS VIIRS NRT · spatial-joined to MP beat polygons (~75% of raw pixels removed)
            </div>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
              <StatusBadge
                band="confirmed"
                label="CONFIRMED"
                count={firesCount ?? undefined}
                size="sm"
              />
              <StatusBadge band="info" label="FOREST-CLIPPED" size="sm" />
            </div>
          </motion.div>
        </motion.section>
      </motion.div>
    </div>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span className="micro">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '10px 12px',
          borderRadius: 8,
          background: colors.bg.raised,
          border: `1px solid ${colors.border.base}`,
          color: colors.text.primary,
          fontFamily: "'Fira Code', monospace",
          fontSize: 13,
          minWidth: 160,
        }}
      />
    </label>
  );
}
