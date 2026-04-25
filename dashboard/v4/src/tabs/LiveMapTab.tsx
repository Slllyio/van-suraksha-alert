import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Layers, Target, Crosshair, Loader2, Calendar, Eye, EyeOff, Filter,
  Mountain, Flame, ShieldQuestion,
} from 'lucide-react';
import { motion, AnimatePresence, fadeUp, transitions } from '../lib/motion';
import { colors } from '../designTokens';
import { Sidebar, SidebarSection } from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import ConfidenceTier from '../components/ConfidenceTier';
import FireMap from '../components/FireMap';
import MapFlyout from '../components/MapFlyout';
import MapLegend from '../components/MapLegend';
import CountUp from '../components/CountUp';
import FloatingParticles from '../components/FloatingParticles';
import { playCue, hapticTap } from '../lib/feedback';
import {
  api,
  type V17Cell,
  type ViirsFire,
  type GeoJSONFeatureCollection,
  type HistoricalBurnPrior,
  type HistoricalBurnPoint,
} from '../lib/api';

interface RiskCounts {
  critical: number;
  alert: number;
  watch: number;
}

type BandKey = 'critical' | 'alert' | 'watch';

function daysSince(iso: string | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const delta = Date.now() - d.getTime();
  return Math.floor(delta / (24 * 60 * 60 * 1000));
}

export default function LiveMapTab() {
  const [cells, setCells] = useState<V17Cell[]>([]);
  const [viirs, setViirs] = useState<ViirsFire[]>([]);
  const [selected, setSelected] = useState<V17Cell | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictionDate, setPredictionDate] = useState<string | undefined>();

  // Layer toggles
  const [showFires, setShowFires] = useState(true);
  const [showBeats, setShowBeats] = useState(false);
  const [showDiv] = useState(true);
  // 3D terrain — see docs/3d_terrain_analysis.md
  // Default exaggeration 4× because at state-wide zoom (~5.8) MP ridges
  // are only 100-500m tall; without exaggeration they don't pop visually.
  const [terrain3D, setTerrain3D] = useState(false);
  const [terrainExag, setTerrainExag] = useState(4.0);
  // Per-band visibility — each of CRITICAL / ALERT / WATCH independent.
  // Click a sidebar risk card (or its checkbox) to toggle that band on/off.
  const [visibleBands, setVisibleBands] = useState<Record<BandKey, boolean>>({
    critical: true,
    alert: true,
    watch: true,
  });
  const toggleBand = (k: BandKey) =>
    setVisibleBands((prev) => ({ ...prev, [k]: !prev[k] }));
  // Solo: click a band alone (meta/ctrl-click) to show only that band
  const soloBand = (k: BandKey) =>
    setVisibleBands({
      critical: k === 'critical',
      alert: k === 'alert',
      watch: k === 'watch',
    });

  // Lazy-loaded beat polygons (179 MB — only fetch when user turns the toggle on)
  const [beats, setBeats] = useState<GeoJSONFeatureCollection | null>(null);
  const [beatsLoading, setBeatsLoading] = useState(false);

  // Mitigation 2 — past-5-year burn density heatmap (lazy-loaded, ~2.4 MB).
  // Mitigation 2 — interior blind-spot diff (cells with 3+ seasons burned
  //   that have no current v17 alert).
  // Mitigation 3 — climatology-promoted WATCH cells (3+ seasons burned).
  // Both mitigations share the same /api/v2/historical-burn-priors fetch
  // because they need the per-cell season counts. Density is fetched
  // separately because it's a flat point cloud weighted by 5y total.
  const [showBurnDensity, setShowBurnDensity] = useState(false);
  const [showBlindSpots, setShowBlindSpots] = useState(false);
  const [augmentWithPriors, setAugmentWithPriors] = useState(false);
  const [burnDensity, setBurnDensity] = useState<HistoricalBurnPoint[] | null>(null);
  const [burnDensityLoading, setBurnDensityLoading] = useState(false);
  const [historicalPriors, setHistoricalPriors] = useState<HistoricalBurnPrior[] | null>(null);
  const [priorsLoading, setPriorsLoading] = useState(false);

  // Lazy fetch — burn density (Mitigation 2 base layer)
  const ensureBurnDensity = useCallback(async () => {
    if (burnDensity || burnDensityLoading) return;
    setBurnDensityLoading(true);
    try {
      const { points } = await api.historicalBurnDensity();
      setBurnDensity(points);
    } catch (e) {
      console.error('historical-burn-density fetch failed:', e);
    } finally {
      setBurnDensityLoading(false);
    }
  }, [burnDensity, burnDensityLoading]);

  // Lazy fetch — historical priors (Mitigation 2 blind-spots + Mitigation 3)
  const ensurePriors = useCallback(async () => {
    if (historicalPriors || priorsLoading) return;
    setPriorsLoading(true);
    try {
      const { records } = await api.historicalBurnPriors(3);
      setHistoricalPriors(records);
    } catch (e) {
      console.error('historical-burn-priors fetch failed:', e);
    } finally {
      setPriorsLoading(false);
    }
  }, [historicalPriors, priorsLoading]);

  const handleBurnDensityToggle = (checked: boolean) => {
    setShowBurnDensity(checked);
    if (checked) ensureBurnDensity();
  };
  const handleBlindSpotsToggle = (checked: boolean) => {
    setShowBlindSpots(checked);
    if (checked) ensurePriors();
  };
  const handleAugmentToggle = (checked: boolean) => {
    setAugmentWithPriors(checked);
    if (checked) ensurePriors();
  };

  // Load v17 + VIIRS once
  useEffect(() => {
    const ctrl = new AbortController();
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [allCells, viirsEnv] = await Promise.all([
          // Walks cursors — returns flat V17Cell[]
          api.ignitionV17All(undefined, ctrl.signal).catch(() => [] as V17Cell[]),
          api
            .viirsFires(undefined, undefined, ctrl.signal)
            .catch(() => ({ data: [] as ViirsFire[], meta: {} })),
        ]);
        const norm: V17Cell[] = allCells.map((c) => ({
          ...c,
          band: String(c.band ?? '').toUpperCase(),
          lat: Number(c.lat),
          lon: Number(c.lon),
        }));
        setCells(norm);
        // v2 envelope exposes prediction_date on the first page's meta.
        // We re-fetch one small page just to read it — cheap.
        api
          .ignitionV17(undefined, { limit: 1, signal: ctrl.signal })
          .then((env) => setPredictionDate(env.meta?.prediction_date))
          .catch(() => {});
        const firesList: ViirsFire[] = (viirsEnv.data ?? []).map((f) => ({
          ...f,
          lat: Number(f.lat),
          lon: Number(f.lon),
        }));
        setViirs(firesList);
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setError((e as Error).message);
        }
      } finally {
        setLoading(false);
      }
    })();
    return () => ctrl.abort();
  }, []);

  const handleCellClick = useCallback((cell: V17Cell) => {
    setSelected(cell);
    const isCritical =
      typeof cell.band === 'string' && cell.band.toUpperCase() === 'CRITICAL';
    playCue(isCritical ? 'alert' : 'open');
    hapticTap(isCritical ? [20, 40, 20] : 15);
  }, []);

  const handleBeatsToggle = async (checked: boolean) => {
    setShowBeats(checked);
    if (checked && !beats && !beatsLoading) {
      setBeatsLoading(true);
      try {
        // Load the original 8,973 MP beat polygons (187 MB). Officers
        // asked for the original detail back — division-dissolve looked
        // too geometric. Browser caches after first load.
        const fc = await api.beatsBoundary();
        setBeats(fc);
      } catch (e) {
        console.error('beats-boundary fetch failed:', e);
        setShowBeats(false);
      } finally {
        setBeatsLoading(false);
      }
    }
  };

  // Count bands for sidebar cards
  const counts: RiskCounts = cells.reduce<RiskCounts>(
    (acc, c) => {
      if (c.band === 'CRITICAL') acc.critical += 1;
      else if (c.band === 'ALERT') acc.alert += 1;
      else if (c.band === 'WATCH') acc.watch += 1;
      return acc;
    },
    { critical: 0, alert: 0, watch: 0 },
  );

  // Use total alert count as "divisions touched" proxy if the payload doesn't
  // include a division field per cell (the v3 backend currently doesn't).
  const divisionCount =
    new Set(cells.map((c) => c.division).filter(Boolean)).size || 87;

  const rows: { band: 'critical' | 'alert' | 'watch'; count: number; divisions: number }[] = [
    { band: 'critical', count: counts.critical, divisions: divisionCount },
    { band: 'alert',    count: counts.alert,    divisions: divisionCount },
    { band: 'watch',    count: counts.watch,    divisions: divisionCount },
  ];

  // Filter layer data based on per-band visibility + FIRMS toggle
  const displayedCells = cells.filter((c) => {
    const b = (c.band || '').toUpperCase();
    if (b === 'CRITICAL') return visibleBands.critical;
    if (b === 'ALERT')    return visibleBands.alert;
    if (b === 'WATCH')    return visibleBands.watch;
    return true;
  });
  const displayedFires = showFires ? viirs : [];
  const anyBandOff = !(visibleBands.critical && visibleBands.alert && visibleBands.watch);

  // Pre-compute the set of cell_ids the v17 model is currently flagging.
  // Drives both the blind-spot diff (priors NOT in alerts) and the
  // prior-watch promotion (priors NOT in alerts → synthetic WATCH).
  const alertCellIds = useMemo(
    () => new Set(cells.map((c) => String(c.cell_id))),
    [cells],
  );

  // Mitigation 2 — interior blind-spots: any cell that historically
  // burned in 3+ seasons but is NOT in today's alert set. These are the
  // cells where officers are flying blind.
  const blindSpotCells = useMemo<HistoricalBurnPrior[] | undefined>(() => {
    if (!showBlindSpots || !historicalPriors) return undefined;
    return historicalPriors.filter((p) => !alertCellIds.has(p.cell_id));
  }, [showBlindSpots, historicalPriors, alertCellIds]);

  // Mitigation 3 — climatology-promoted WATCH cells: same source as
  // blind spots, but rendered with double-ring amber to communicate
  // "watch this regardless of model." The override is deterministic —
  // any cell with 3+ seasons burned and no v17 alert gets surfaced.
  const priorWatchCells = useMemo<HistoricalBurnPrior[] | undefined>(() => {
    if (!augmentWithPriors || !historicalPriors) return undefined;
    return historicalPriors.filter((p) => !alertCellIds.has(p.cell_id));
  }, [augmentWithPriors, historicalPriors, alertCellIds]);

  const burnDensityLayerData = showBurnDensity && burnDensity ? burnDensity : undefined;

  const ageDays = daysSince(predictionDate);
  const stale = ageDays != null && ageDays > 1;

  // Aria-live announcement string. Updates whenever a layer finishes
  // loading so screen-reader users get completion feedback they would
  // otherwise miss (the spinner just disappears silently).
  const liveAnnouncement = (() => {
    if (burnDensityLoading) return 'Loading burn density layer';
    if (priorsLoading) return 'Loading historical priors layer';
    if (showBurnDensity && burnDensity) {
      return `Burn density layer ready, ${burnDensity.length.toLocaleString()} cells`;
    }
    if ((showBlindSpots || augmentWithPriors) && historicalPriors) {
      return `Historical priors layer ready, ${historicalPriors.length.toLocaleString()} cells`;
    }
    return '';
  })();

  return (
    <div data-layout="live-map" style={{ display: 'flex', height: '100%' }}>
      {/* Visually-hidden live region — only mounted when there is
          something to announce. Avoids empty-string echo that some AT
          (older NVDA+Firefox) read as a brief pause. */}
      {liveAnnouncement && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          style={{
            position: 'absolute', width: 1, height: 1,
            padding: 0, margin: -1, overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0,
          }}
        >
          {liveAnnouncement}
        </div>
      )}
      <Sidebar>
        {predictionDate && (
          <motion.div
            variants={fadeUp}
            // role=status + aria-live so screen readers announce
            // staleness on mount instead of leaving it in a title
            // tooltip that touch-device AT never reads.
            role={stale ? 'status' : undefined}
            aria-live={stale ? 'polite' : undefined}
            aria-label={
              stale
                ? `Warning: last prediction is ${ageDays} days old. Daily pipeline may need a re-run.`
                : `Live prediction date ${predictionDate}.`
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 10px',
              marginBottom: -8,
              background: stale ? colors.fire.watch.bg : colors.accent.muted,
              border: `1px solid ${stale ? colors.fire.watch.border : 'rgba(138,180,248,.28)'}`,
              borderRadius: 6,
              fontSize: 11,
              color: stale ? colors.fire.watch.fg : colors.accent.base,
            }}
            title={
              stale
                ? `Last prediction is ${ageDays} days old. Daily pipeline may need a re-run.`
                : 'Live prediction from the daily pipeline.'
            }
          >
            <Calendar size={12} aria-hidden="true" />
            <span className="mono">{predictionDate}</span>
            {stale && <span style={{ marginLeft: 'auto' }}>· {ageDays}d old</span>}
          </motion.div>
        )}
        <SidebarSection label="Today's risk">
          {loading && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '12px 4px',
                color: colors.text.tertiary,
                fontSize: 12,
              }}
            >
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                style={{ display: 'inline-flex' }}
              >
                <Loader2 size={14} />
              </motion.span>
              Loading predictions…
            </div>
          )}
          {!loading && error && (
            <div
              style={{
                background: colors.fire.critical.bg,
                border: `1px solid ${colors.fire.critical.border}`,
                borderRadius: 8,
                padding: 10,
                fontSize: 11,
                color: colors.fire.critical.fg,
              }}
            >
              Backend unreachable: {error}. Start{' '}
              <span className="mono">python dashboard/v3/serve.py</span>
            </div>
          )}
          {!loading &&
            !error &&
            rows.map((row, i) => {
              const bandColor = colors.fire[row.band].fg;
              const bandBg = colors.fire[row.band].bg;
              const visible = visibleBands[row.band];
              return (
                <motion.button
                  key={row.band}
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  custom={i}
                  whileHover={{
                    y: -2,
                    boxShadow: `0 8px 24px ${bandBg}, 0 0 0 1px ${colors.fire[row.band].border}`,
                  }}
                  whileTap={{ scale: 0.98 }}
                  transition={transitions.base}
                  onClick={(e) =>
                    e.shiftKey || e.metaKey || e.ctrlKey
                      ? soloBand(row.band)
                      : toggleBand(row.band)
                  }
                  // Keyboard equivalent of shift-click: Shift+Enter or
                  // Shift+Space solos this band. Plain Enter/Space
                  // toggles (handled by browser default for buttons).
                  onKeyDown={(e) => {
                    if ((e.key === 'Enter' || e.key === ' ') && (e.shiftKey || e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      soloBand(row.band);
                    }
                  }}
                  title={`Click to ${visible ? 'hide' : 'show'} ${row.band.toUpperCase()} markers. Shift-click (or Shift+Enter) to show ONLY ${row.band.toUpperCase()}.`}
                  aria-pressed={visible}
                  aria-label={`${visible ? 'Hide' : 'Show'} ${row.band.toUpperCase()} band on map. Shift+Enter to isolate this band.`}
                  style={{
                    position: 'relative',
                    overflow: 'hidden',
                    background: `linear-gradient(135deg, ${colors.bg.raised} 0%, ${colors.bg.surface} 100%)`,
                    border: `1px solid ${colors.border.subtle}`,
                    borderLeft: `3px solid ${bandColor}`,
                    borderRadius: 10,
                    padding: '14px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: 'inherit',
                    font: 'inherit',
                    opacity: visible ? 1 : 0.42,
                    filter: visible ? 'none' : 'grayscale(0.4)',
                  }}
                >
                  {/* Ambient colored glow in the corner */}
                  <div
                    aria-hidden
                    style={{
                      position: 'absolute',
                      top: -40,
                      right: -40,
                      width: 120,
                      height: 120,
                      background: `radial-gradient(circle, ${bandBg} 0%, transparent 70%)`,
                      pointerEvents: 'none',
                      opacity: visible ? 0.8 : 0.25,
                    }}
                  />
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      position: 'relative',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <StatusBadge
                        band={row.band}
                        size="sm"
                        pulse={row.band === 'critical' && row.count > 0 && visible}
                      />
                      {visible ? (
                        <Eye size={12} color={bandColor} aria-label="visible on map" />
                      ) : (
                        <EyeOff
                          size={12}
                          color={colors.text.tertiary}
                          aria-label="hidden from map"
                        />
                      )}
                    </div>
                    <motion.span
                      className="mono"
                      initial={{ opacity: 0, scale: 0.7 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{
                        delay: 0.2 + i * 0.08,
                        type: 'spring',
                        stiffness: 260,
                        damping: 20,
                      }}
                      style={{
                        fontSize: 28,
                        fontWeight: 600,
                        color: bandColor,
                        lineHeight: 1,
                        textShadow: `0 0 20px ${bandBg}`,
                      }}
                    >
                      <CountUp value={row.count} duration={1.4} />
                    </motion.span>
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: colors.text.tertiary,
                      position: 'relative',
                    }}
                  >
                    {row.divisions > 0
                      ? `across ${row.divisions} / 87 divisions`
                      : '— no data —'}
                  </div>
                </motion.button>
              );
            })}
          {anyBandOff && !loading && !error && (
            <motion.button
              variants={fadeUp}
              whileHover={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
              whileTap={{ scale: 0.97 }}
              transition={transitions.fast}
              onClick={() =>
                setVisibleBands({ critical: true, alert: true, watch: true })
              }
              style={{
                marginTop: 4,
                padding: '8px 10px',
                borderRadius: 8,
                background: 'transparent',
                border: `1px dashed ${colors.border.base}`,
                color: colors.accent.base,
                fontSize: 11,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
              }}
            >
              <Filter size={12} />
              Show all bands
            </motion.button>
          )}
        </SidebarSection>

        <SidebarSection label="Model confidence">
          <motion.div
            whileHover={{
              borderColor: 'rgba(129, 201, 149, 0.42)',
              boxShadow: '0 0 24px rgba(129, 201, 149, 0.18)',
            }}
            transition={transitions.base}
            style={{
              background: `linear-gradient(135deg, ${colors.bg.raised} 0%, ${colors.bg.surface} 100%)`,
              border: `1px solid ${colors.border.subtle}`,
              borderRadius: 12,
              padding: 18,
              textAlign: 'center',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <ConfidenceRing value={22.8} />
            <div className="micro" style={{ marginTop: 10 }}>
              pixel-level recall
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                gap: 4,
                marginTop: 12,
              }}
            >
              <ConfidenceTier tier="HIGH" size="sm" />
            </div>
          </motion.div>
        </SidebarSection>

        <SidebarSection label="Other layers">
          {[
            {
              icon: Target,
              label: 'Active fires (FIRMS)',
              checked: showFires,
              onChange: setShowFires,
            },
            {
              icon: Crosshair,
              label: 'Forest beats',
              checked: showBeats,
              onChange: handleBeatsToggle,
              loading: beatsLoading,
            },
            {
              icon: Layers,
              label: 'Division boundaries',
              checked: showDiv,
              onChange: undefined,
              loading: false,
            },
          ].map(({ icon: Icon, label, checked, onChange, loading: rowLoading }) => (
            <motion.label
              key={label}
              variants={fadeUp}
              whileHover={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
              transition={transitions.fast}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '6px 8px',
                borderRadius: 6,
                cursor: onChange ? 'pointer' : 'default',
                opacity: onChange ? 1 : 0.6,
                color: colors.text.secondary,
                fontSize: 13,
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange?.(e.target.checked)}
                disabled={!onChange || rowLoading}
                style={{ accentColor: colors.accent.base }}
              />
              <Icon size={14} color={colors.text.tertiary} />
              <span style={{ flex: 1 }}>{label}</span>
              {rowLoading && (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                  style={{
                    display: 'inline-flex',
                    color: colors.accent.base,
                  }}
                  aria-label="loading"
                >
                  <Loader2 size={12} />
                </motion.span>
              )}
            </motion.label>
          ))}
        </SidebarSection>

        {/* Mitigations 2 + 3 — coverage diagnostic + interior monitor.
            See docs/edge_bias_brutal_analysis.md. The model is structurally
            edge-biased (71% of alerts within 1 km of forest edge, 0% in
            deep interior); these toggles let officers visually verify
            the gap and override with deterministic climatology priors. */}
        <SidebarSection label="Coverage diagnostic">
          <div
            style={{
              fontSize: 10,
              color: colors.text.tertiary,
              padding: '0 4px 6px',
              lineHeight: 1.5,
            }}
          >
            v17.5 misses ~94% of fires in low-Hawkes (cold-start) cells.
            Use these to see WHERE fires actually keep happening.
          </div>
          {[
            {
              icon: Flame,
              key: 'burn-density',
              label: 'Past 5y burn density',
              checked: showBurnDensity,
              onChange: handleBurnDensityToggle,
              loading: burnDensityLoading,
              count: burnDensity?.length ?? null,
              countLabel: 'cells',
            },
            {
              icon: ShieldQuestion,
              key: 'blind-spots',
              label: 'Interior blind-spots',
              checked: showBlindSpots,
              onChange: handleBlindSpotsToggle,
              loading: priorsLoading,
              count: blindSpotCells?.length ?? null,
              countLabel: 'silent cells',
            },
          ].map(({ icon: Icon, key, label, checked, onChange, loading: rowLoading, count, countLabel }) => (
            <motion.label
              key={key}
              variants={fadeUp}
              whileHover={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
              transition={transitions.fast}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '6px 8px',
                borderRadius: 6,
                cursor: 'pointer',
                color: colors.text.secondary,
                fontSize: 13,
              }}
              title={
                key === 'burn-density'
                  ? 'Heatmap of every cell that burned ≥2× over the last 5 fire seasons.'
                  : 'Cells that historically burned in 3+ of last 5 seasons but have NO current v17 alert. Purple rings = blind spots.'
              }
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
                disabled={rowLoading}
                style={{ accentColor: colors.accent.base }}
              />
              <Icon size={14} color={colors.text.tertiary} />
              <span style={{ flex: 1 }}>{label}</span>
              {rowLoading ? (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                  style={{ display: 'inline-flex', color: colors.accent.base }}
                  aria-label="loading"
                >
                  <Loader2 size={12} />
                </motion.span>
              ) : checked && typeof count === 'number' ? (
                <span
                  className="mono"
                  style={{
                    fontSize: 10,
                    color: colors.text.tertiary,
                    background: 'rgba(148, 163, 184, 0.08)',
                    padding: '2px 6px',
                    borderRadius: 999,
                  }}
                >
                  {count.toLocaleString()} {countLabel}
                </span>
              ) : null}
            </motion.label>
          ))}

          {/* Mitigation 3 — Interior-monitor override. Visual treatment
              uses the BLUE accent (not amber) so officers don't read
              the toggle itself as alarming. The amber rings appear on
              the map; the toggle communicates "feature engaged", not
              "danger active". Pattern matches the 3D-terrain toggle's
              engaged state below. */}
          <motion.label
            variants={fadeUp}
            whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.04)' }}
            transition={transitions.fast}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              padding: '8px 10px',
              marginTop: 6,
              borderRadius: 8,
              cursor: 'pointer',
              background: augmentWithPriors
                ? colors.accent.muted
                : colors.bg.raised,
              border: `1px solid ${
                augmentWithPriors
                  ? 'rgba(138, 180, 248, 0.42)'
                  : colors.border.subtle
              }`,
              color: augmentWithPriors
                ? colors.accent.base
                : colors.text.secondary,
              fontSize: 13,
              fontWeight: 500,
            }}
            title="Interior-monitor override: deterministically promotes any cell that burned in 3+ of last 5 fire seasons to WATCH, regardless of v17 score."
          >
            <input
              type="checkbox"
              checked={augmentWithPriors}
              onChange={(e) => handleAugmentToggle(e.target.checked)}
              disabled={priorsLoading}
              style={{ marginTop: 2, accentColor: colors.fire.watch.fg }}
            />
            <span style={{ flex: 1 }}>
              <div>Augment with historical priors</div>
              <div
                style={{
                  fontSize: 10,
                  color: colors.text.tertiary,
                  marginTop: 4,
                  lineHeight: 1.45,
                  fontWeight: 400,
                }}
              >
                Promotes any cell to WATCH if it burned in 3+ of the last
                5 fire seasons, regardless of the model's score. Amber
                double-rings on the map.
              </div>
              {augmentWithPriors && priorWatchCells && (
                <div
                  className="mono"
                  style={{
                    fontSize: 10,
                    color: colors.accent.base,
                    marginTop: 6,
                  }}
                >
                  +{priorWatchCells.length.toLocaleString()} promoted cells
                </div>
              )}
            </span>
          </motion.label>
        </SidebarSection>

        <SidebarSection label="3D view">
          <motion.label
            variants={fadeUp}
            whileHover={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
            transition={transitions.fast}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 10px',
              borderRadius: 8,
              cursor: 'pointer',
              background: terrain3D ? colors.accent.muted : colors.bg.raised,
              border: `1px solid ${terrain3D ? 'rgba(138,180,248,.42)' : colors.border.subtle}`,
              color: terrain3D ? colors.accent.base : colors.text.secondary,
              fontSize: 13,
              fontWeight: 500,
              transition: 'background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast)',
            }}
          >
            <input
              type="checkbox"
              checked={terrain3D}
              onChange={(e) => setTerrain3D(e.target.checked)}
              style={{ accentColor: colors.accent.base }}
            />
            <Mountain size={14} />
            <span style={{ flex: 1 }}>3D terrain</span>
            {terrain3D && (
              <motion.span
                className="mono"
                initial={{ opacity: 0, scale: 0.7 }}
                animate={{ opacity: 1, scale: 1 }}
                style={{
                  fontSize: 10,
                  color: colors.accent.base,
                  background: 'rgba(138,180,248,.16)',
                  padding: '2px 6px',
                  borderRadius: 999,
                }}
              >
                ON
              </motion.span>
            )}
          </motion.label>
          <AnimatePresence>
            {terrain3D && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={transitions.base}
                style={{ overflow: 'hidden' }}
              >
                <div
                  style={{
                    padding: '10px 4px 4px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: 11,
                      color: colors.text.tertiary,
                    }}
                  >
                    <span>Vertical exaggeration</span>
                    <span
                      className="mono"
                      style={{ color: colors.accent.base, fontSize: 11 }}
                    >
                      {terrainExag.toFixed(1)}×
                    </span>
                  </div>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    step={0.5}
                    value={terrainExag}
                    onChange={(e) => setTerrainExag(parseFloat(e.target.value))}
                    aria-label="Terrain vertical exaggeration"
                    style={{
                      width: '100%',
                      accentColor: colors.accent.base,
                    }}
                  />
                  <div
                    style={{
                      fontSize: 10,
                      color: colors.text.tertiary,
                      lineHeight: 1.4,
                    }}
                  >
                    Drag-rotate enabled. Tiles via{' '}
                    <a
                      href="https://registry.opendata.aws/terrain-tiles/"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: colors.accent.base }}
                    >
                      AWS Terrain
                    </a>
                    .
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </SidebarSection>
      </Sidebar>

      <section style={{ flex: 1, minWidth: 0, position: 'relative' }}>
        <FireMap
          cells={displayedCells}
          viirs={displayedFires}
          beats={showBeats ? beats : null}
          terrain3D={terrain3D}
          terrainExaggeration={terrainExag}
          burnDensityPoints={burnDensityLayerData}
          blindSpotCells={blindSpotCells}
          priorWatchCells={priorWatchCells}
          onCellClick={handleCellClick}
        />
        <MapLegend
          showFires={showFires}
          showBeats={showBeats}
          showBurnDensity={showBurnDensity}
          showBlindSpots={showBlindSpots}
          augmentWithPriors={augmentWithPriors}
        />
        <FloatingParticles count={36} />
        <MapFlyout
          cell={selected}
          onClose={() => {
            setSelected(null);
            playCue('close');
          }}
        />
      </section>
    </div>
  );
}

function ConfidenceRing({ value }: { value: number }) {
  // value is 0-100
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  // Arc color: BLUE accent, NOT confirmed-fire green. Officers are
  // trained to read green = "confirmed real fire" (VIIRS dots). Reusing
  // green here for "model recall %" inverted the semantic — green at
  // 22.8% is bad news, but green is brain-coded as "good".
  return (
    <div
      role="img"
      aria-label={`Model pixel-level recall: ${value.toFixed(1)} percent`}
      style={{ position: 'relative', width: 84, height: 84, margin: '0 auto' }}
    >
      <svg width={84} height={84} viewBox="0 0 84 84" aria-hidden="true">
        {/* Track */}
        <circle
          cx={42}
          cy={42}
          r={r}
          fill="none"
          stroke={colors.border.subtle}
          strokeWidth={6}
        />
        {/* Progress arc — animated from 0 to pct */}
        <motion.circle
          cx={42}
          cy={42}
          r={r}
          fill="none"
          stroke={colors.accent.base}
          strokeWidth={6}
          strokeLinecap="round"
          transform="rotate(-90 42 42)"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 6px ${colors.accent.muted})` }}
        />
      </svg>
      <div
        className="mono"
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 22,
          fontWeight: 600,
          color: colors.text.primary,
        }}
      >
        <CountUp value={value} duration={1.4} decimals={1} suffix="%" />
      </div>
    </div>
  );
}
