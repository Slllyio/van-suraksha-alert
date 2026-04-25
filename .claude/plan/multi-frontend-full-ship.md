# Multi-Frontend Full-Ship Plan — 4 Surfaces, 17 Findings

**Created:** 2026-04-25
**Workflow:** `/everything-claude-code:multi-frontend` (round 2)
**Audit basis:** parallel ux-designer (mobile) + ui-designer (4 tabs) + ux-designer (AIBriefDrawer) + api-documenter (OpenAPI)
**Scope:** 5 BLOCKERs + 12 MAJORs + OpenAPI insertion. ~600 LoC across 9 files.

## Pass A — Token-collision back-ports (mirror 51fdab25 pattern)

| File | Change |
|---|---|
| `DivisionsTab.tsx:352-356` | Floor-promoted card → `colors.coverage.priorWatch.{bg,border,fg}` (was raw amber hex) |
| `ViirsTab.tsx:568` | Clip-ratio StatCard → `colors.text.secondary` (was `fire.watch.fg`) |
| `ViirsTab.tsx:738-739` | Leaderboard ranks 4-10 → `colors.accent.base` (was `fire.info.fg`) |
| `ValidationTab.tsx:253` | LOW-trust badge → ConfidenceTier with `trustTier.low.fg` (was StatusBadge band='critical' = red) |
| `ModelCardTab.tsx:53` | TRUST_TIERS LOW → use `trustTier.low.fg` directly (was band='critical') |

## Pass B — AIBriefDrawer polish (mirror MapFlyout pattern from 51fdab25)

| Change | Why |
|---|---|
| Remove `aria-modal="true"` | No focus trap implemented; same MapFlyout fix |
| Replace aria-label with visually-hidden h2 + aria-labelledby | Same child-swallowing fix |
| Focus → close button (not textarea, which is disabled during stream) | Honors always-enabled escape hatch |
| `aria-live="off"` during stream, role=status announce on completion | SSE token-by-token would otherwise spam AT |
| Responsive width: `min(420px, calc(100vw - 48px))` minWidth 280 | Same width-clamp pattern |
| `<label htmlFor=textarea>` + `aria-describedby` for PII disclaimer | Placeholder isn't an a11y label |
| Send button: dynamic aria-label + aria-busy during stream | Distinguish "empty input" vs "streaming" |
| Cursor span `aria-hidden="true"` | Stop AT reading the blinking block char |
| Stub-fallback notice → separate role=status banner | Currently buried in stream text |
| Conversation scroll `tabIndex={0}` + aria-label | Keyboard users can't scroll history |
| Stable keys on message list (id, not array index) | Avoids re-render churn during stream |

## Pass C — Mobile responsive (CSS + layout breakpoints)

| File | Change |
|---|---|
| `theme.css` add `@media (max-width: 900px)` | Header flex-wrap + tab nav full-width + height auto |
| `MapFlyout.tsx` | Width formula: 32px gutter when ≤900px, 256px when wider |
| `DivisionsTab.tsx:156-157,888` | DetailPanel `min(400px, calc(100vw - 24px))`; paddingRight conditional |
| `ValidationTab.tsx:169-268` | Wrap `<table>` in `overflowX:auto`, padding clamp |
| All tabs | Outer padding `clamp(16px, 5vw, 48px)` |
| `ViirsTab.tsx:702` | Leaderboard `flex: 1 1 100px, minWidth: 80, maxWidth: 180` |
| Touch targets | Close buttons 44×44, sidebar rows padding 10px |

## Pass D — OpenAPI insertion + apiSchema regen

| File | Change |
|---|---|
| `dashboard/v3/openapi.yaml` | Insert 2 paths + 4 schemas (api-documenter agent produced YAML) |
| `dashboard/v4/src/lib/apiSchema.ts` | Regen via `npm run codegen` |
| `dashboard/v4/src/lib/api.ts` | Optional: switch hand-written interfaces to schema-derived (low priority for this pass) |

## Pass E — Polish (DivisionsTab nice-to-haves)

| File | Change |
|---|---|
| `DivisionsTab.tsx:714-740` | Skeleton shimmer animation (motion opacity keyframes) |
| `DivisionsTab.tsx:DetailPanel` | scroll-to-top on division change |
| `DivisionsTab.tsx` | Add visually-hidden h1 |

## Verification

- `npx tsc --noEmit` clean
- 22-case test suite passes
- Vite HMR pickup
- Re-audit via ux-designer on the diff (Phase 5)

## Out of scope

- ModelCardTab `buildForecastTraces` shared mock data (NIT)
- KPI font-size token drift (32 vs 36 vs 40) — needs token-system decision separately
