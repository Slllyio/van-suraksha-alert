// MapLegend — bottom-left floating legend that explains the active
// map layers. Only renders rows for layers currently toggled on so the
// legend stays minimal.
//
// Why this exists: ux-designer audit flagged that without an inline
// legend, officers — especially returning users or first-time visitors
// — have to mentally cross-reference the sidebar toggle labels against
// the map symbology. Under field stress (2 a.m., 7-inch tablet) this
// causes mis-identification (orange ring = ALERT band? blind-spot?
// climatology?). Embedding the swatch+label removes that lookup.

import { motion, AnimatePresence } from '../lib/motion';
import { colors } from '../designTokens';

interface MapLegendProps {
  showFires: boolean;
  showBeats: boolean;
  showBurnDensity: boolean;
  showBlindSpots: boolean;
  augmentWithPriors: boolean;
  /** When fuel-load layer is active, render a categorical sub-legend
   *  for the SB40 fuel classes so officers can identify forest litter
   *  vs cropland vs grassland by colour, not by guess. */
  showFuelLoad?: boolean;
}

interface LegendRow {
  key: string;
  swatch: React.ReactNode;
  label: string;
}

function Swatch({ children }: { children: React.ReactNode }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 18,
        height: 18,
        flexShrink: 0,
      }}
    >
      {children}
    </span>
  );
}

function Dot({ fill }: { fill: string }) {
  return (
    <Swatch>
      <span
        style={{
          width: 12, height: 12, borderRadius: '50%', background: fill,
          boxShadow: `0 0 6px ${fill}55`,
        }}
      />
    </Swatch>
  );
}

function Ring({ stroke, dashed }: { stroke: string; dashed?: boolean }) {
  return (
    <Swatch>
      <span
        style={{
          width: 14, height: 14, borderRadius: '50%',
          border: `1.5px ${dashed ? 'dashed' : 'solid'} ${stroke}`,
        }}
      />
    </Swatch>
  );
}

function HeatRamp() {
  return (
    <Swatch>
      <span
        style={{
          width: 18, height: 8, borderRadius: 4,
          background: 'linear-gradient(90deg, rgba(40,60,90,0.4), #3E6D98, #599F7C, #DAAF46, #B43C8C, #D250B4)',
        }}
      />
    </Swatch>
  );
}

export default function MapLegend({
  showFires,
  showBeats,
  showBurnDensity,
  showBlindSpots,
  augmentWithPriors,
  showFuelLoad,
}: MapLegendProps) {
  // Always-on alert bands first; dynamic layers below. Only render the
  // dynamic-layer rows when their toggle is on so the legend stays
  // tight (state-fire seasons can have 3-5 layers active simultaneously).
  const rows: LegendRow[] = [
    { key: 'critical', swatch: <Dot fill={colors.fire.critical.fg} />, label: 'CRITICAL alert (model)' },
    { key: 'alert',    swatch: <Dot fill={colors.fire.alert.fg} />,    label: 'ALERT (model)' },
    { key: 'watch',    swatch: <Dot fill={colors.fire.watch.fg} />,    label: 'WATCH (model)' },
  ];

  if (showFires) {
    rows.push({
      key: 'viirs',
      swatch: <Dot fill={colors.fire.confirmed.fg} />,
      label: 'Confirmed fire (VIIRS)',
    });
  }
  if (showBurnDensity) {
    rows.push({
      key: 'density',
      swatch: <HeatRamp />,
      label: 'Past 5y burn density',
    });
  }
  if (showBlindSpots) {
    rows.push({
      key: 'blind',
      swatch: <Ring stroke={colors.coverage.blindSpot.fg} />,
      label: 'Blind-spot (silent in v17, burned 3+ seasons)',
    });
  }
  if (augmentWithPriors) {
    rows.push({
      key: 'prior',
      swatch: <Ring stroke={colors.coverage.priorWatch.fg} />,
      label: 'Climatology-promoted WATCH (override)',
    });
  }
  if (showBeats) {
    rows.push({
      key: 'beats',
      swatch: <Ring stroke="rgba(129, 201, 149, 0.6)" />,
      label: 'Forest beat boundary',
    });
  }
  if (showFuelLoad) {
    // Categorical SB40 fuel classes — distinct hue per type so
    // officers can ID forest leaf-litter vs cropland vs grassland
    // at a glance. Order: heaviest fuel first (forest litter).
    rows.push(
      { key: 'fuel-tl2', swatch: <Dot fill={colors.fuelClass.TL2.fg} />, label: colors.fuelClass.TL2.label },
      { key: 'fuel-sh2', swatch: <Dot fill={colors.fuelClass.SH2.fg} />, label: colors.fuelClass.SH2.label },
      { key: 'fuel-gr1', swatch: <Dot fill={colors.fuelClass.GR1.fg} />, label: colors.fuelClass.GR1.label },
      { key: 'fuel-gr2', swatch: <Dot fill={colors.fuelClass.GR2.fg} />, label: colors.fuelClass.GR2.label },
    );
  }

  return (
    <AnimatePresence>
      <motion.div
        key="map-legend"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 8 }}
        transition={{ duration: 0.18 }}
        role="region"
        aria-label="Map layer legend"
        style={{
          position: 'absolute',
          left: 16,
          bottom: 16,
          maxWidth: 280,
          padding: '10px 12px',
          background: 'rgba(15, 23, 42, 0.78)',
          backdropFilter: 'blur(14px) saturate(140%)',
          WebkitBackdropFilter: 'blur(14px) saturate(140%)',
          border: `1px solid ${colors.border.base}`,
          borderRadius: 10,
          fontSize: 11,
          color: colors.text.secondary,
          lineHeight: 1.4,
          boxShadow: '0 6px 20px rgba(0, 0, 0, 0.35)',
          zIndex: 4,
          pointerEvents: 'none',  // never blocks map clicks
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: colors.text.tertiary,
            marginBottom: 6,
          }}
        >
          Legend
        </div>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {rows.map((row) => (
            <li
              key={row.key}
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              {row.swatch}
              <span>{row.label}</span>
            </li>
          ))}
        </ul>
      </motion.div>
    </AnimatePresence>
  );
}
