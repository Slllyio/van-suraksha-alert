// Client-side derivation of v17.5 cell trust tier.
//
// Why this lives client-side: the backend payload doesn't currently set
// `trust_tier`, but every cell carries the underlying Hawkes signal
// (`hawkes_lambda` + `hawkes_n_recent_10km_7d`). Deriving here lets us
// tune thresholds without a backend redeploy and keeps the brutal
// honesty surface (see `docs/edge_bias_brutal_analysis.md`) visible to
// every officer who clicks an alert.
//
// Tier thresholds match the analysis doc's Mitigation 1 table:
//
//   HIGH   — hawkes_lambda > 0.01 AND n_recent_10km_7d > 0
//            (model is in its 25.5% R@5% sweet spot — Hawkes contagion regime)
//   MEDIUM — Hawkes nonzero, no recent fires
//            (mid-confidence — cross-check with patrol before dispatch)
//   LOW    — hawkes_lambda < 0.001
//            (cold-start zone — model recall ≈ 5.9%, near-random)
//
// Distribution on 2026-04-24 daily prediction (1,570 banded alerts):
//   HIGH ~19%, MEDIUM ~71%, LOW ~9.3%

import type { V17Cell } from './api';

export type TrustTier = 'HIGH' | 'MEDIUM' | 'LOW';

export interface TrustGuidance {
  tier: TrustTier;
  /** One-line officer-facing label. */
  label: string;
  /** Action guidance for the dispatch decision. */
  guidance: string;
  /** Honest model-recall context for this regime. */
  recallContext: string;
}

const HIGH_LAMBDA = 0.01;
const LOW_LAMBDA = 0.001;

export function deriveTrustTier(cell: V17Cell): TrustTier {
  // Honor backend-provided tier if the API ever starts emitting one.
  if (cell.trust_tier === 'HIGH' || cell.trust_tier === 'MEDIUM' || cell.trust_tier === 'LOW') {
    return cell.trust_tier;
  }

  const lambda = typeof cell.hawkes_lambda === 'number' ? cell.hawkes_lambda : 0;
  const nRecent =
    typeof cell.hawkes_n_recent_10km_7d === 'number' ? cell.hawkes_n_recent_10km_7d : 0;

  if (lambda > HIGH_LAMBDA && nRecent > 0) return 'HIGH';
  if (lambda < LOW_LAMBDA) return 'LOW';
  return 'MEDIUM';
}

export function getTrustGuidance(cell: V17Cell): TrustGuidance {
  const tier = deriveTrustTier(cell);
  switch (tier) {
    case 'HIGH':
      return {
        tier,
        label: 'High-trust contagion zone',
        guidance: 'Act on this. Recent fire activity within 10 km — model is in its sweet spot.',
        recallContext: 'v17.5 catches ~25.5% of fires in this regime.',
      };
    case 'MEDIUM':
      return {
        tier,
        label: 'Mixed signal',
        guidance: 'Cross-check with the latest patrol log before dispatching.',
        recallContext: 'Some Hawkes signal, but no fires within 10 km in last 7 days.',
      };
    case 'LOW':
    default:
      return {
        tier,
        label: 'Cold-start blind zone',
        guidance:
          'Use only as awareness — do NOT dispatch on this cell alone. Pair with a coverage / patrol prior.',
        recallContext: 'v17.5 recall in this regime is ~5.9% (near-random).',
      };
  }
}
