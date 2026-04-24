# JwalaNetra v4 — Fire-Domain Design Overrides

> **This file overrides MASTER.md** for the entire v4 portal. MASTER was generated
> with light "Financial Dashboard" defaults which don't fit a crisis-response tool
> checked at 3 AM. Overrides below are synthesized from `ui-ux-pro-max-skill`
> domain searches (product, style, color, chart, ux, typography) + fire-EWS
> operational constraints.

## Style Decision

**Primary: Dark Mode (OLED) + Data-Dense hybrid**
- `Dark Mode (OLED)` — WCAG AAA, low emission, eye-friendly for night operations
- `Data-Dense` — 12-col grid, 8-12 px padding, 36 px table rows, sortable tables,
  KPI cards row, filter sidebar (240 px), header (56 px)
- **Rejected:** Cyberpunk (gov context, too playful), Glassmorphism (GIS map
  readability loses to heavy blur), Brutalist mono (data isn't primary content,
  map is — mono font for chrome, sans for map overlays)

## Color Palette (finalized)

Based on `product="Financial Dashboard"` result + `color="cybersecurity/autonomous systems"` alert-red patterns + our fire-band semantics.

### Surfaces (dark — always)
| Role | Hex | Usage |
|---|---|---|
| `bg-canvas` | `#0F172A` | Page background (slate-900) |
| `bg-surface` | `#1E293B` | Primary panels, sidebar (slate-800) |
| `bg-raised` | `#334155` | Cards on hover, modals (slate-700) |
| `bg-overlay` | `#475569` | Popovers, dropdowns (slate-600) |
| `border` | `rgba(148,163,184,.14)` | Subtle dividers (slate-400 @ 14%) |
| `border-strong` | `rgba(148,163,184,.28)` | Focused elements |

### Text (WCAG AAA on `bg-canvas`)
| Role | Hex | Contrast | Usage |
|---|---|---|---|
| `text-primary` | `#F8FAFC` | 17.4:1 | Headings, values |
| `text-secondary` | `#CBD5E1` | 11.3:1 | Labels, secondary info |
| `text-tertiary` | `#94A3B8` | 6.8:1 | Captions, metadata |
| `text-disabled` | `#64748B` | 3.6:1 | Disabled (still ≥3:1) |

### Semantic (fire bands — **icon + color + text**, never color alone)
| Band | Hex | Lucide Icon | Dark-bg contrast |
|---|---|---|---|
| `critical` | `#EF4444` | `AlertTriangle` | 4.8:1 (AA) |
| `alert` | `#F97316` | `Flame` | 5.9:1 (AA) |
| `watch` | `#FBBF24` | `Eye` | 10.2:1 (AAA) |
| `confirmed` | `#22C55E` | `CheckCircle2` | 6.4:1 (AA) |
| `info` | `#3B82F6` | `Info` | 5.8:1 (AA) |

> Anti-pattern enforcement: Every status badge MUST render `<Icon /> + text + color`.
> Ref: ux rule `color-not-only` — "Red/green only for error/success" is a BAD.
> Ref: ux rule `color-not-decorative-only`.

## Typography

**Pairing:** `Fira Sans` (UI) + `Fira Code` (all numbers, coordinates, timestamps, IDs)

Reason: `product=Analytics/Financial Dashboard` → both returned `Fira Code / Fira Sans`
as "dashboard, data, analytics, code, technical, precise". Fira family cohesion means
mono and sans share metrics — no alignment shifts when switching inside a table cell.

```css
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

--font-ui:   'Fira Sans', system-ui, sans-serif;
--font-mono: 'Fira Code', ui-monospace, monospace;  /* tabular numbers on */
```

**Scale (12/14/16/20/24/32):**
- `micro` 11 px — uppercase captions (tracking +0.08em, weight 500)
- `caption` 12 px — metadata, timestamps
- `body` 14 px — default (line-height 1.5, weight 400)
- `label` 13 px — form labels (weight 500)
- `h3` 16 px (weight 600)
- `h2` 20 px (weight 500, tracking -0.01em)
- `h1` 24 px (weight 500, tracking -0.01em)
- `display` 32 px — KPI numerics (mono, weight 600, tabular-nums)

## Spacing (8-pt grid)
`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64`

Data-Dense specifics: card padding `12 px`, grid gap `8 px`, table row `36 px`,
sidebar `240 px`, header `56 px`.

## Radii
`xs=4 / sm=6 / md=8 / lg=12 / pill=999`

No huge rounding — serious/operational tone. `lg=12` is the max for panels; `pill`
only for status badges and tab chips.

## Elevation (black shadows for dark bg)
- `shadow-1`: `0 1px 2px rgba(0,0,0,.4)`
- `shadow-2`: `0 2px 6px rgba(0,0,0,.45), 0 1px 2px rgba(0,0,0,.4)`
- `shadow-3`: `0 6px 16px rgba(0,0,0,.55), 0 2px 4px rgba(0,0,0,.4)`
- `shadow-4`: `0 12px 32px rgba(0,0,0,.6), 0 4px 8px rgba(0,0,0,.45)` (modals only)

## Motion (framer-motion)

**Tokens:**
```ts
const ease = {
  standard:   [0.2, 0, 0, 1] as const,   // enter/most UI
  emphasized: [0.3, 0, 0, 1] as const,   // panel slides, page changes
  exit:       [0.4, 0, 1, 1] as const,   // faster exit
};
const duration = { fast: 0.12, base: 0.2, slow: 0.32 };   // seconds
```

**Patterns:**
- Page/tab fade: `opacity 0→1 + y 8→0`, `duration.base`, `ease.standard`
- Card stagger (division grid): 40 ms delay per card, max 12 cards
- Alert flyout: right-edge slide, `duration.slow`, `ease.emphasized`
- Map pin drop: `spring({ stiffness: 200, damping: 20 })` on confirmed fires only
- CRITICAL band pulse: opacity `0.6→1` loop, 1.6 s, respects `prefers-reduced-motion`
- Data refresh: shimmer placeholder (>300 ms wait) — never spinner

**Anti-patterns (ux rule refs):**
- ❌ Bouncy springs on non-map elements (`spring-physics` says subtle, not consumer)
- ❌ Animations >500 ms (`duration-timing`)
- ❌ Scale-on-press for panels (consumer app feel; only for buttons, 0.98→1)
- ❌ Decorative-only animation (`excessive-motion` — max 1-2 animated elements per view)
- ❌ Ignoring reduced-motion (`reduced-motion` CRITICAL rule)

All framer-motion components wrap with:
```tsx
import { useReducedMotion } from 'framer-motion';
const reduce = useReducedMotion();
<motion.div animate={reduce ? {} : { opacity: 1, y: 0 }} />
```

## Charts (per-screen guidance from `--domain chart`)

| Screen | Chart | Rationale (ref chart.csv) |
|---|---|---|
| Validation log (pred vs actual) | **Line Chart with Highlights** | `anomaly-detection` — normal days blue, missed-fire days red marker + annotation |
| V17 division forecast trend | **Line with Confidence Band** | `time-series-forecast` — actual solid blue, forecast dashed orange, 95% CI band |
| Alert breakdown by division | **Horizontal Bar Chart** | `no-pie-overuse` — >5 categories kills pies; horizontal handles long division names |
| Feature importance (model card) | **Vertical Bar Chart** | Direct labeling (`direct-labeling` rule), top-20 ranked |
| VIIRS historical heatmap | **Choropleth map (not chart)** | Handled by MapLibre, not chart lib |

**Library recommendation:** Recharts 9/10 (matches React idioms + Fira Code via `tabular-nums` CSS).

## Fire/Emergency-Specific Patterns (my domain additions)

These aren't in the skill CSVs but are essential for public-safety tools:

1. **Trust tier badge** — every predictive cell shows `HIGH/MEDIUM/LOW` confidence alongside the band. Officers learn to weigh WATCH-HIGH more than CRITICAL-LOW. Render as a small pill next to band (`bg-overlay`, `border-strong`, icon from Lucide).

2. **Honest metrics on model card** — display recall 45.5% and precision 3.2% (CRITICAL tier) PROMINENTLY, not buried. Per ux rule `error-clarity`: "state cause + how to fix." We show cause (5.9% low-Hawkes recall) + fix path (climatology floor + hurdle blend details).

3. **Time-since freshness** — every tile shows "updated X min ago" in mono. After 6h age, show amber WATCH border on the tile. After 24h, show CRITICAL red border + "stale data" warning.

4. **Color + icon + text triple for every band** — per WCAG, never rely on color. Use `<AlertTriangle /> CRITICAL · 12`, not bare `12` on red.

5. **Keyboard shortcuts** — officers using tablets in the field also get bluetooth keyboards. Wire up:
   - `1-5` → switch tabs
   - `/` → focus search
   - `ESC` → close flyout/modal
   - `Enter` on focused cell → open detail

6. **No hover-only info** — tap/click for everything. Per ux rule `hover-vs-tap`.

## Anti-Patterns (explicit DO-NOT list)

From the skill's output + our domain:
- ❌ Bright neon (cybersec style recommended #00FF41 — rejected: gov serious tone)
- ❌ Emoji as icons (🔥 🚨) — use Lucide SVG only
- ❌ Gradients as decoration on cards (obscure data per `trend-emphasis`)
- ❌ Glassmorphism blur over the map (reduces GIS readability)
- ❌ Pie charts for >5 divisions (pattern `no-pie-overuse`)
- ❌ Color-only alert states (pattern `color-not-only`)
- ❌ Red/green pair without icon (pattern `color-guidance` chart rule)
- ❌ Scale-on-press for cards (consumer-app, mismatch with operational tone)
- ❌ Bounces / springs with low damping (< 15)
- ❌ Animations > 500 ms
- ❌ Light mode default (night operations)

## Implementation (next steps)

1. `src/designTokens.ts` — TypeScript tokens, import everywhere
2. `src/theme.css` — CSS variables mirror of tokens for non-JS (Tailwind-like)
3. `src/components/StatusBadge.tsx` — the icon+text+color primitive (blocks color-only misuse)
4. `src/components/ConfidenceTier.tsx` — HIGH/MEDIUM/LOW pill
5. `src/lib/motion.ts` — reduced-motion-aware wrapper + token re-exports
6. Page-specific overrides in `design-system/jwalanetra-fire-ews-v4/pages/{live-map,divisions,model-card,validation,viirs}.md`

## Sources

Every rule above traces to either:
- `.claude/skills/ui-ux-pro-max/data/products.csv` (Financial Dashboard row)
- `.claude/skills/ui-ux-pro-max/data/styles.csv` (Dark Mode OLED, Data-Dense)
- `.claude/skills/ui-ux-pro-max/data/colors.csv` (Cybersecurity + IoT rows, semantic alerts)
- `.claude/skills/ui-ux-pro-max/data/typography.csv` (Fira Code/Sans pairing)
- `.claude/skills/ui-ux-pro-max/data/ux.csv` (color-not-only, reduced-motion, tap-vs-hover, anomaly-detection chart rule)
- `.claude/skills/ui-ux-pro-max/data/charts.csv` (anomaly-detection, time-series-forecast, no-pie-overuse)
