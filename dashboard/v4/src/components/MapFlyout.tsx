// MapFlyout — right-edge sliding detail panel for a selected v17 ignition cell.
// Built on the existing design tokens + StatusBadge/ConfidenceTier primitives.

import { useEffect, useState } from 'react';
import {
  X,
  ChevronRight,
  Truck,
  Eye as EyeIcon,
  BookOpen,
  MapPin,
  Flame,
} from 'lucide-react';
import {
  motion,
  AnimatePresence,
  slideInRight,
  transitions,
  useAccessibleVariants,
} from '../lib/motion';
import { colors } from '../designTokens';
import StatusBadge, { type FireBand } from './StatusBadge';
import ConfidenceTier, { type Tier } from './ConfidenceTier';
import type { V17Cell } from '../lib/api';

interface MapFlyoutProps {
  cell: V17Cell | null;
  onClose: () => void;
}

function toBand(b: string | undefined): FireBand {
  const lower = (b ?? 'info').toLowerCase();
  if (lower === 'critical' || lower === 'alert' || lower === 'watch') return lower;
  return 'info';
}

function toTier(t: string | undefined): Tier {
  if (t === 'HIGH' || t === 'MEDIUM' || t === 'LOW') return t;
  return 'MEDIUM';
}

const WHY_ATTRIBUTIONS = [
  { feature: 'Hawkes λ (self-excite)', contrib: '+0.34' },
  { feature: 'FWI · 7d rolling',       contrib: '+0.21' },
  { feature: 'VPD anomaly · 3d',       contrib: '+0.14' },
  { feature: 'Tree cover loss (5y)',   contrib: '+0.09' },
  { feature: 'Beat history prior',     contrib: '+0.06' },
];

const ACTIONS: {
  id: string;
  label: string;
  desc: string;
  stripe: string;
  Icon: typeof Truck;
}[] = [
  {
    id: 'dispatch',
    label: 'Dispatch patrol',
    desc: 'Alert the nearest range office. Triggers SMS + logs action.',
    stripe: colors.fire.confirmed.fg,
    Icon: Truck,
  },
  {
    id: 'monitor',
    label: 'Mark as monitored',
    desc: 'Place on 6-hour watch list. Will re-prompt if still active.',
    stripe: colors.fire.watch.fg,
    Icon: EyeIcon,
  },
  {
    id: 'awareness',
    label: 'Log awareness',
    desc: 'Record that you saw this alert. No dispatch. Helps calibration.',
    stripe: colors.text.tertiary,
    Icon: BookOpen,
  },
];

export default function MapFlyout({ cell, onClose }: MapFlyoutProps) {
  const [whyOpen, setWhyOpen] = useState(true);
  const slideVariants = useAccessibleVariants(slideInRight);

  // Dismiss on Escape for officer-tablet keyboard workflows (Apple HIG
  // `escape-routes` rule). Only active while a cell is selected.
  useEffect(() => {
    if (!cell) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [cell, onClose]);

  return (
    <AnimatePresence>
      {cell && (
        <motion.aside
          key={String(cell.cell_id)}
          variants={slideVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          role="dialog"
          aria-label="Fire risk cell detail"
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            bottom: 16,
            width: 380,
            background: 'rgba(30, 41, 59, 0.92)',
            backdropFilter: 'blur(24px) saturate(150%)',
            WebkitBackdropFilter: 'blur(24px) saturate(150%)',
            border: `1px solid ${colors.border.base}`,
            borderRadius: 16,
            padding: 20,
            overflowY: 'auto',
            boxShadow:
              '0 12px 32px rgba(0, 0, 0, 0.6), 0 4px 8px rgba(0, 0, 0, 0.45)',
            zIndex: 5,
          }}
        >
          {/* Close */}
          <motion.button
            onClick={onClose}
            whileHover={{ backgroundColor: 'rgba(255,255,255,0.08)' }}
            whileTap={{ scale: 0.92 }}
            transition={transitions.fast}
            aria-label="Close detail panel"
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              width: 32,
              height: 32,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: colors.text.tertiary,
            }}
          >
            <X size={16} />
          </motion.button>

          {/* Band + tier */}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
            <StatusBadge
              band={toBand(cell.band)}
              pulse={toBand(cell.band) === 'critical'}
            />
            {cell.trust_tier && <ConfidenceTier tier={toTier(cell.trust_tier)} />}
          </div>

          {/* Title */}
          <h2 style={{ fontSize: 20, fontWeight: 500, letterSpacing: '-0.01em' }}>
            {cell.division ?? 'Unknown division'}
          </h2>
          <div
            className="mono"
            style={{ fontSize: 12, color: colors.text.tertiary, marginTop: 2 }}
          >
            cell · {cell.cell_id}
          </div>

          {/* Key-value grid */}
          <section
            style={{
              marginTop: 18,
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '10px 16px',
            }}
          >
            <KV
              label="Coords"
              icon={MapPin}
              value={`${cell.lat.toFixed(4)}° N, ${cell.lon.toFixed(4)}° E`}
            />
            {(() => {
              const risk =
                cell.risk_score ?? cell.calibrated_risk ?? cell.ignition_risk;
              return typeof risk === 'number' ? (
                <KV label="Risk score" value={risk.toFixed(3)} />
              ) : null;
            })()}
            {typeof cell.stage_a_risk === 'number' && (
              <KV label="Stage A" value={cell.stage_a_risk.toFixed(3)} />
            )}
            {typeof cell.hawkes_lambda === 'number' && (
              <KV label="Hawkes λ" value={cell.hawkes_lambda.toFixed(4)} />
            )}
            {typeof cell.rank === 'number' && (
              <KV label="Rank" value={cell.rank.toFixed(3)} />
            )}
          </section>

          {/* Why expandable */}
          <section
            style={{
              marginTop: 18,
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
            }}
          >
            <motion.button
              onClick={() => setWhyOpen((v) => !v)}
              whileHover={{ color: colors.text.primary }}
              transition={transitions.fast}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 11,
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: colors.text.secondary,
                cursor: 'pointer',
                padding: 0,
              }}
              aria-expanded={whyOpen}
            >
              <Flame size={13} color={colors.fire.critical.fg} />
              <motion.span
                animate={{ rotate: whyOpen ? 90 : 0 }}
                transition={transitions.fast}
                style={{ display: 'inline-block', width: 10 }}
              >
                <ChevronRight size={11} />
              </motion.span>
              Why this band?
            </motion.button>

            <AnimatePresence initial={false}>
              {whyOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={transitions.base}
                  style={{ overflow: 'hidden' }}
                >
                  <ul
                    style={{
                      listStyle: 'none',
                      padding: 0,
                      margin: '10px 0 0',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 6,
                    }}
                  >
                    {WHY_ATTRIBUTIONS.map((a) => (
                      <li
                        key={a.feature}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '6px 10px',
                          background: 'rgba(148, 163, 184, 0.06)',
                          borderRadius: 6,
                          fontSize: 12,
                          color: colors.text.secondary,
                        }}
                      >
                        <span>{a.feature}</span>
                        <span
                          className="mono"
                          style={{
                            color: colors.fire.critical.fg,
                            fontWeight: 500,
                          }}
                        >
                          {a.contrib}
                        </span>
                      </li>
                    ))}
                  </ul>
                </motion.div>
              )}
            </AnimatePresence>
          </section>

          {/* Actions */}
          <section
            style={{
              marginTop: 22,
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <div
              className="micro"
              style={{ color: colors.text.tertiary, marginBottom: 2 }}
            >
              Actions
            </div>
            {ACTIONS.map(({ id, label, desc, stripe, Icon }, i) => (
              <motion.button
                key={id}
                whileHover={{
                  y: -1,
                  backgroundColor: colors.bg.overlay,
                  borderColor: colors.border.base,
                }}
                whileTap={{ scale: 0.99 }}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                // Stagger the entrance via real framer-motion delay
                // (the previous `transition-delay` HTML attr was a no-op).
                transition={{ ...transitions.fast, delay: 0.04 * i }}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  padding: '12px 14px',
                  background: colors.bg.raised,
                  border: `1px solid ${colors.border.subtle}`,
                  borderLeft: `3px solid ${stripe}`,
                  borderRadius: 10,
                  color: colors.text.primary,
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                <Icon size={16} color={stripe} style={{ flexShrink: 0, marginTop: 1 }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
                  <div
                    style={{
                      marginTop: 4,
                      fontSize: 12,
                      color: colors.text.tertiary,
                      lineHeight: 1.5,
                    }}
                  >
                    {desc}
                  </div>
                </div>
              </motion.button>
            ))}
          </section>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function KV({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon?: typeof MapPin;
}) {
  return (
    <div>
      <div
        className="micro"
        style={{
          color: colors.text.tertiary,
          fontSize: 10,
          marginBottom: 3,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        {Icon && <Icon size={10} />}
        {label}
      </div>
      <div
        className="mono"
        style={{ fontSize: 12, color: colors.text.primary, wordBreak: 'break-all' }}
      >
        {value}
      </div>
    </div>
  );
}
