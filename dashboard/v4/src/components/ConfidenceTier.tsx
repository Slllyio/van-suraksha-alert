// ConfidenceTier — HIGH/MEDIUM/LOW pill shown alongside a fire band.
// Officers learn to weigh "WATCH-HIGH" more than "CRITICAL-LOW" — so this is
// surfaced as a separate primitive, always visible next to a StatusBadge.

import type { ComponentType, SVGProps } from 'react';
import { ShieldCheck, ShieldAlert, ShieldX } from 'lucide-react';
import { colors } from '../designTokens';

export type Tier = 'HIGH' | 'MEDIUM' | 'LOW';

type LucideIcon = ComponentType<SVGProps<SVGSVGElement> & { size?: number | string }>;

const TIER_META: Record<Tier, { icon: LucideIcon; fg: string; description: string }> = {
  HIGH:   { icon: ShieldCheck, fg: colors.trustTier.high.fg,   description: 'High model confidence' },
  MEDIUM: { icon: ShieldAlert, fg: colors.trustTier.medium.fg, description: 'Medium model confidence' },
  LOW:    { icon: ShieldX,     fg: colors.trustTier.low.fg,    description: 'Low model confidence — verify before dispatch' },
};

export interface ConfidenceTierProps {
  tier: Tier;
  /** Optional numeric probability to display (0-1 or 0-100). */
  probability?: number;
  size?: 'sm' | 'md';
}

export function ConfidenceTier({ tier, probability, size = 'sm' }: ConfidenceTierProps) {
  const { icon: Icon, fg, description } = TIER_META[tier];
  const isSmall = size === 'sm';

  const probText =
    probability == null
      ? null
      : probability <= 1
        ? `${Math.round(probability * 100)}%`
        : `${Math.round(probability)}%`;

  return (
    <span
      className={`tier tier--${tier.toLowerCase()}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: isSmall ? '2px 8px' : '3px 10px',
        borderRadius: 999,
        background: 'rgba(148, 163, 184, 0.08)',
        color: fg,
        border: '1px solid rgba(148, 163, 184, 0.22)',
        fontSize: isSmall ? 10 : 11,
        fontWeight: 500,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        lineHeight: 1,
        whiteSpace: 'nowrap',
      }}
      title={description}
      aria-label={`${description}${probText ? `, ${probText} probability` : ''}`}
    >
      <Icon size={isSmall ? 11 : 12} aria-hidden="true" />
      <span>{tier}</span>
      {probText && (
        <span style={{ fontFamily: "'Fira Code', monospace", fontVariantNumeric: 'tabular-nums' }}>
          {probText}
        </span>
      )}
    </span>
  );
}

export default ConfidenceTier;
