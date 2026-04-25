# Multi-Frontend UX Polish Plan — Mitigations 1/2/3

**Created:** 2026-04-25
**Workflow:** `/everything-claude-code:multi-frontend` (Gemini unavailable; substituted with parallel `ux-designer` + `ui-designer` subagents per user election)
**Scope:** Package C — full polish (color collisions + a11y + layout + legend)

## Findings (synthesized from 2 parallel audits, 26 total items)

Convergent BLOCKERs (independent agreement = high confidence):
- Blind-spot orange rings = ALERT orange dots — colorblind ambiguity
- Prior-watch amber rings = WATCH amber dots — model vs climatology indistinguishable

Distinct BLOCKERs:
- ux: MapFlyout has no focus management on open
- ux: Trust-strip `aria-label` swallows children → screen readers miss the dispatch guidance
- ui: Heatmap warm-end (red) collides with CRITICAL red

MAJORs incorporated:
- Trust-tier palette collides with fire-band palette (MEDIUM=WATCH amber, LOW=CRITICAL red)
- ConfidenceRing green clashes with VIIRS-confirmed-fire green
- No map legend
- Flyout 380px overflows tablet viewport
- Solo-band has no keyboard equivalent
- ConfidenceRing missing aria-label
- Mitigation 3 callout amber tint operationally misleading
- Layer ordering puts priorWatch above ignitionCells

## Files touched

| Path | Change |
|---|---|
| `dashboard/v4/src/designTokens.ts` | Decouple `trustTier` from fire palette. Add `colors.coverage.{blindSpot,priorWatch}` tokens. |
| `dashboard/v4/src/components/FireMap.tsx` | Recolor heatmap warm-end (magenta), blindSpotLayer (purple), priorWatchLayer (darker amber, hollow). Swap layer order so priorWatch sits BELOW ignitionCells. Tighten radii. |
| `dashboard/v4/src/components/MapFlyout.tsx` | Focus mgmt on open (focus close button via ref). Add `aria-modal="true"`. Remove aria-label from trust-strip wrapper, add visually-hidden heading. Add `id`/`aria-controls` for "Why this band". Trust-strip text hierarchy fix (recallContext 12px/secondary/non-italic, bold pct). Responsive width: `min(380px, calc(100vw - 256px))`. |
| `dashboard/v4/src/components/Sidebar.tsx` | Add `aria-label="Map controls and alert summary"`. |
| `dashboard/v4/src/tabs/LiveMapTab.tsx` | Mitigation 3 callout active-state → blue (accent.muted/base). ConfidenceRing → arc color blue, add aria-label. Solo-band keyboard handler (Shift+Enter). Add aria-live region for layer load completion. Stale prediction warning → role=status + aria-live. |
| `dashboard/v4/src/components/MapLegend.tsx` | NEW — bottom-left legend showing color swatches + labels for every active map layer. Conditionally renders rows based on which layers are on. |

## Verification

- `npx tsc --noEmit` — clean
- vite HMR + manual click-through on each toggle
- Re-audit via `ux-designer` (focused on diff)

## Out of scope (NITs deferred)

- Augment toggle pre-checked-disabled (issue 15 from ux-designer)
- Comment inaccuracy in FireMap (issue 11 from ui-designer)
- aria-controls on "Why this band?" (issue 11 from ux-designer)
