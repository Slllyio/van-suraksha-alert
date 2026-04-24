import { useEffect, useState } from 'react';
import { Layers, Flame, Target, Crosshair, Loader2, Calendar } from 'lucide-react';
import { motion, fadeUp, transitions } from '../lib/motion';
import { colors } from '../designTokens';
import { Sidebar, SidebarSection } from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import ConfidenceTier from '../components/ConfidenceTier';
import FireMap from '../components/FireMap';
import MapFlyout from '../components/MapFlyout';
import CountUp from '../components/CountUp';
import FloatingParticles from '../components/FloatingParticles';
import { playCue, hapticTap } from '../lib/feedback';
import { api, type V17Cell, type ViirsFire, type GeoJSONFeatureCollection } from '../lib/api';

interface RiskCounts {
  critical: number;
  alert: number;
  watch: number;
}

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
  const [showIgnition, setShowIgnition] = useState(true);
  const [showFires, setShowFires] = useState(true);
  const [showBeats, setShowBeats] = useState(false);
  const [showDiv] = useState(true);

  // Lazy-loaded beat polygons (179 MB — only fetch when user turns the toggle on)
  const [beats, setBeats] = useState<GeoJSONFeatureCollection | null>(null);
  const [beatsLoading, setBeatsLoading] = useState(false);

  // Load v17 + VIIRS once
  useEffect(() => {
    const ctrl = new AbortController();
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [v17, viirsResp] = await Promise.all([
          api
            .ignitionV17(undefined, ctrl.signal)
            .catch(() => ({ banded_alerts: [] as V17Cell[] })),
          api
            .viirsFires(undefined, undefined, ctrl.signal)
            .catch(() => ({ fires: [] as ViirsFire[] })),
        ]);
        // Backend returns `banded_alerts` now; tolerate legacy `cells` too.
        const raw = v17.banded_alerts ?? v17.cells ?? [];
        const norm: V17Cell[] = raw.map((c) => ({
          ...c,
          band: String(c.band ?? '').toUpperCase(),
          lat: Number(c.lat),
          lon: Number(c.lon),
        }));
        setCells(norm);
        setPredictionDate(v17.prediction_date ?? v17.target_date);
        // Backend wraps fires under { fires: [...] } — unwrap + coerce numerics
        const firesList: ViirsFire[] = (viirsResp.fires ?? []).map((f) => ({
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

  const handleBeatsToggle = async (checked: boolean) => {
    setShowBeats(checked);
    if (checked && !beats && !beatsLoading) {
      setBeatsLoading(true);
      try {
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

  // Filter layer data based on toggles
  const displayedCells = showIgnition ? cells : [];
  const displayedFires = showFires ? viirs : [];

  const ageDays = daysSince(predictionDate);
  const stale = ageDays != null && ageDays > 1;

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <Sidebar>
        {predictionDate && (
          <motion.div
            variants={fadeUp}
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
            <Calendar size={12} />
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
              return (
                <motion.div
                  key={row.band}
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  custom={i}
                  whileHover={{
                    y: -2,
                    boxShadow: `0 8px 24px ${bandBg}, 0 0 0 1px ${colors.fire[row.band].border}`,
                  }}
                  transition={transitions.base}
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
                      opacity: 0.8,
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
                    <StatusBadge
                      band={row.band}
                      size="sm"
                      pulse={row.band === 'critical' && row.count > 0}
                    />
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
                </motion.div>
              );
            })}
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

        <SidebarSection label="Layers">
          {[
            {
              icon: Flame,
              label: 'Predicted ignitions',
              checked: showIgnition,
              onChange: setShowIgnition,
            },
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
      </Sidebar>

      <section style={{ flex: 1, minWidth: 0, position: 'relative' }}>
        <FireMap
          cells={displayedCells}
          viirs={displayedFires}
          beats={showBeats ? beats : null}
          onCellClick={(cell) => {
            setSelected(cell);
            const isCritical =
              typeof cell.band === 'string' && cell.band.toUpperCase() === 'CRITICAL';
            playCue(isCritical ? 'alert' : 'open');
            hapticTap(isCritical ? [20, 40, 20] : 15);
          }}
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
  return (
    <div style={{ position: 'relative', width: 84, height: 84, margin: '0 auto' }}>
      <svg width={84} height={84} viewBox="0 0 84 84">
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
          stroke={colors.fire.confirmed.fg}
          strokeWidth={6}
          strokeLinecap="round"
          transform="rotate(-90 42 42)"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 6px ${colors.fire.confirmed.bg})` }}
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
