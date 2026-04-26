// JwalaNetra v4 — Design Tokens
// Single source of truth for colors, type, spacing, motion.
// Derived from design-system/jwalanetra-fire-ews-v4/FIRE_OVERRIDES.md

export const colors = {
  bg: {
    canvas:  '#0F172A',  // page background (slate-900)
    surface: '#1E293B',  // panels, sidebar (slate-800)
    raised:  '#334155',  // cards on hover, modals (slate-700)
    overlay: '#475569',  // popovers, dropdowns (slate-600)
  },
  border: {
    subtle: 'rgba(148, 163, 184, 0.14)',
    base:   'rgba(148, 163, 184, 0.22)',
    strong: 'rgba(148, 163, 184, 0.28)',
    divider: 'rgba(148, 163, 184, 0.08)',
  },
  text: {
    primary:   '#F8FAFC',  // 17.4:1 AAA
    secondary: '#CBD5E1',  // 11.3:1 AAA
    tertiary:  '#94A3B8',  //  6.8:1 AA
    disabled:  '#64748B',  //  3.6:1 (>=3:1 required)
    onAccent:  '#0F172A',  // dark text on bright CTA fills
  },
  fire: {
    critical:  { fg: '#EF4444', bg: 'rgba(239, 68, 68, 0.14)',  border: 'rgba(239, 68, 68, 0.42)' },
    alert:     { fg: '#F97316', bg: 'rgba(249, 115, 22, 0.14)', border: 'rgba(249, 115, 22, 0.42)' },
    watch:     { fg: '#FBBF24', bg: 'rgba(251, 191, 36, 0.14)', border: 'rgba(251, 191, 36, 0.42)' },
    confirmed: { fg: '#22C55E', bg: 'rgba(34, 197, 94, 0.14)',  border: 'rgba(34, 197, 94, 0.42)' },
    info:      { fg: '#3B82F6', bg: 'rgba(59, 130, 246, 0.14)', border: 'rgba(59, 130, 246, 0.42)' },
  },
  accent: {
    base:    '#3B82F6',  // trust blue for primary actions/links
    hover:   '#60A5FA',
    pressed: '#2563EB',
    muted:   'rgba(59, 130, 246, 0.16)',
  },
  // Trust tier — DECOUPLED from fire-band palette so MEDIUM cells with
  // LOW model confidence don't read as "amber+amber" or "red+red" in
  // MapFlyout. Fire-band keeps its semantic meaning (severity), trust
  // tier carries the orthogonal axis (model confidence in this prediction).
  // HIGH stays green (matches confirmed-fire semantically: trustworthy).
  // MEDIUM moves to violet — distinct from amber WATCH.
  // LOW moves to amber-500 — distinct from CRITICAL red, still warning-coded.
  trustTier: {
    high:   { fg: '#22C55E', label: 'HIGH' },
    medium: { fg: '#A78BFA', label: 'MEDIUM' },  // violet-400
    low:    { fg: '#F59E0B', label: 'LOW' },     // amber-500 (warning, not alarm)
  },
  // Coverage-diagnostic layers (Mitigation 2 + 3). Tokens deliberately
  // OFF the red/orange/amber alert axis so officers can distinguish
  // "model said this" from "climatology said this" at a glance.
  coverage: {
    blindSpot:  { fg: '#7C3AED', bg: 'rgba(124, 58, 237, 0.14)',  border: 'rgba(124, 58, 237, 0.42)' },  // violet-600
    priorWatch: { fg: '#D97706', bg: 'rgba(217, 119, 6, 0.10)',   border: 'rgba(217, 119, 6, 0.36)' },   // amber-600 (darker than WATCH)
  },
  // Fuel-load categorical palette — Scott & Burgan 40 fuel-model
  // classes. Discrete hues so officers can tell forest leaf-litter
  // from cropland from grassland AT A GLANCE, not via a continuous
  // gradient. All chosen OFF the red/orange/amber alert palette and
  // OFF the magenta burn-density terminus.
  fuelClass: {
    TL2: { fg: '#1F6B3A', label: 'Forest litter (TL2, ~15 t/ha)' },     // deep forest green
    SH2: { fg: '#2A8C8C', label: 'Shrub (SH2, ~8 t/ha)' },              // teal
    GR2: { fg: '#A88E2C', label: 'Grassland (GR2, ~3.5 t/ha)' },        // olive
    GR1: { fg: '#D4A55C', label: 'Cropland (GR1, ~12 t/ha)' },          // wheat
    NB1: { fg: '#64748B', label: 'Urban/non-burnable' },                 // slate
    NB8: { fg: '#3B82F6', label: 'Water (NB8)' },                        // blue
    NB9: { fg: '#94A3B8', label: 'Bare ground (NB9)' },                  // light slate
  },
} as const;

export const fontFamily = {
  ui:   "'Fira Sans', system-ui, sans-serif",
  mono: "'Fira Code', ui-monospace, 'SFMono-Regular', Menlo, monospace",
} as const;

export const fontSize = {
  micro:   '11px',  // uppercase captions
  caption: '12px',
  label:   '13px',
  body:    '14px',
  h3:      '16px',
  h2:      '20px',
  h1:      '24px',
  display: '32px',  // KPI numerics (mono, tabular-nums)
} as const;

export const fontWeight = {
  regular: 400,
  medium:  500,
  semi:    600,
  bold:    700,
} as const;

export const lineHeight = {
  tight:  1.15,
  snug:   1.3,
  normal: 1.5,
  loose:  1.75,
} as const;

// Letter-spacing
export const tracking = {
  tight:  '-0.01em',
  normal: '0',
  wide:   '0.02em',
  widest: '0.08em',  // uppercase micro labels
} as const;

// 8-pt grid
export const space = {
  1:  '4px',
  2:  '8px',
  3:  '12px',
  4:  '16px',
  5:  '20px',
  6:  '24px',
  7:  '32px',
  8:  '40px',
  9:  '48px',
  10: '64px',
} as const;

// Data-Dense specifics
export const layout = {
  sidebarWidth: '240px',
  headerHeight: '56px',
  cardPadding:  '12px',
  gridGap:       '8px',
  tableRowHeight: '36px',
  focusRing: '2px',
} as const;

export const radius = {
  xs:   '4px',
  sm:   '6px',
  md:   '8px',
  lg:   '12px',
  pill: '999px',
} as const;

export const shadow = {
  1: '0 1px 2px rgba(0,0,0,0.4)',
  2: '0 2px 6px rgba(0,0,0,0.45), 0 1px 2px rgba(0,0,0,0.4)',
  3: '0 6px 16px rgba(0,0,0,0.55), 0 2px 4px rgba(0,0,0,0.4)',
  4: '0 12px 32px rgba(0,0,0,0.6), 0 4px 8px rgba(0,0,0,0.45)',
  ring: `0 0 0 2px ${colors.accent.base}80`,
} as const;

// ---- Motion (framer-motion compatible) ----

// cubic-bezier values as readonly tuples (framer-motion accepts these)
export const ease = {
  standard:   [0.2, 0, 0, 1] as const,
  emphasized: [0.3, 0, 0, 1] as const,
  exit:       [0.4, 0, 1, 1] as const,
} as const;

export const duration = {
  fast: 0.12,  // micro-interactions (hover)
  base: 0.2,   // page/tab transitions
  slow: 0.32,  // panel slides, flyouts
} as const;

export const spring = {
  // Subtle — operational, not consumer-bouncy
  gentle:   { type: 'spring', stiffness: 220, damping: 28 } as const,
  default:  { type: 'spring', stiffness: 280, damping: 24 } as const,
  // ONLY for map pin drops on confirmed fires
  mapPin:   { type: 'spring', stiffness: 320, damping: 20 } as const,
} as const;

export const stagger = {
  card:   0.04,  // division grid cards
  list:   0.03,  // table rows
  alert:  0.06,  // critical alerts — slightly slower to read
} as const;

// ---- Chart colors (colorblind-safe, paired with pattern/shape) ----

export const chartColors = {
  actual:     '#3B82F6',   // solid line
  forecast:   '#F97316',   // dashed line
  anomaly:    '#EF4444',   // red marker + icon
  confidence: 'rgba(59, 130, 246, 0.16)',  // 95% CI band fill
  grid:       'rgba(148, 163, 184, 0.12)',
  axis:       '#94A3B8',
  baseline:   '#64748B',
  series: [
    '#3B82F6', '#F97316', '#22C55E', '#A78BFA',
    '#FBBF24', '#EC4899', '#14B8A6', '#F43F5E',
  ],
} as const;

// ---- Export union type ----

export type DesignTokens = {
  colors: typeof colors;
  fontFamily: typeof fontFamily;
  fontSize: typeof fontSize;
  fontWeight: typeof fontWeight;
  lineHeight: typeof lineHeight;
  tracking: typeof tracking;
  space: typeof space;
  layout: typeof layout;
  radius: typeof radius;
  shadow: typeof shadow;
  ease: typeof ease;
  duration: typeof duration;
  spring: typeof spring;
  stagger: typeof stagger;
  chartColors: typeof chartColors;
};

export const tokens: DesignTokens = {
  colors, fontFamily, fontSize, fontWeight, lineHeight, tracking,
  space, layout, radius, shadow, ease, duration, spring, stagger, chartColors,
};

export default tokens;
