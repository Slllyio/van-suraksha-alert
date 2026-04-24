// StatusBadge — icon + text + color triple for fire band / alert state.
// This component enforces the WCAG `color-not-only` accessibility rule: callers
// cannot render a color-only pill because the icon and label are not optional.

import type { ComponentType, SVGProps } from 'react';
import { AlertTriangle, Flame, Eye, CheckCircle2, Info } from 'lucide-react';
import { motion, useReducedMotion } from '../lib/motion';
import { colors } from '../designTokens';

export type FireBand = 'critical' | 'alert' | 'watch' | 'confirmed' | 'info';

type LucideIcon = ComponentType<SVGProps<SVGSVGElement> & { size?: number | string }>;

const BAND_META: Record<FireBand, {
  icon: LucideIcon;
  label: string;
  palette: typeof colors.fire.critical;
}> = {
  critical:  { icon: AlertTriangle, label: 'CRITICAL',  palette: colors.fire.critical  },
  alert:     { icon: Flame,         label: 'ALERT',     palette: colors.fire.alert     },
  watch:     { icon: Eye,           label: 'WATCH',     palette: colors.fire.watch     },
  confirmed: { icon: CheckCircle2,  label: 'CONFIRMED', palette: colors.fire.confirmed },
  info:      { icon: Info,          label: 'INFO',      palette: colors.fire.info      },
};

export interface StatusBadgeProps {
  band: FireBand;
  /** Optional override label (default is the band name capitalized). */
  label?: string;
  /** Optional numeric count shown after the label, e.g. `CRITICAL · 12`. */
  count?: number;
  /** Size variant. */
  size?: 'sm' | 'md';
  /** Toggles a subtle pulsing animation for CRITICAL only (respected by
   *  prefers-reduced-motion via CSS). */
  pulse?: boolean;
}

export function StatusBadge({
  band,
  label,
  count,
  size = 'md',
  pulse = false,
}: StatusBadgeProps) {
  const { icon: Icon, label: defaultLabel, palette } = BAND_META[band];
  const isSmall = size === 'sm';
  const reduce = useReducedMotion();

  // Pulse animation for CRITICAL — uses framer-motion so prefers-reduced-motion
  // is honored and the animation interrupts cleanly on unmount.
  const animate =
    pulse && !reduce
      ? {
          boxShadow: [
            `0 0 0 0px ${palette.border}`,
            `0 0 0 6px rgba(239, 68, 68, 0)`,
            `0 0 0 0px ${palette.border}`,
          ],
        }
      : undefined;

  return (
    <motion.span
      className={`sb sb--${band}`}
      animate={animate}
      transition={
        pulse
          ? { duration: 1.6, repeat: Infinity, ease: 'easeOut' }
          : undefined
      }
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: isSmall ? 4 : 6,
        padding: isSmall ? '2px 8px' : '4px 10px',
        borderRadius: 999,
        background: palette.bg,
        color: palette.fg,
        border: `1px solid ${palette.border}`,
        fontSize: isSmall ? 11 : 12,
        fontWeight: 500,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        lineHeight: 1,
        whiteSpace: 'nowrap',
      }}
      role="status"
      aria-label={`${label ?? defaultLabel}${count != null ? `: ${count}` : ''}`}
    >
      <Icon size={isSmall ? 12 : 14} aria-hidden="true" />
      <span>{label ?? defaultLabel}</span>
      {count != null && (
        <span style={{ fontFamily: "'Fira Code', monospace", fontVariantNumeric: 'tabular-nums' }}>
          {`· ${count.toLocaleString()}`}
        </span>
      )}
    </motion.span>
  );
}

export default StatusBadge;
