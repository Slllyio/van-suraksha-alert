import { useEffect, useState } from 'react';
import { Layers, Flame, Target, Crosshair, Loader2 } from 'lucide-react';
import { motion, fadeUp, transitions } from '../lib/motion';
import { colors } from '../designTokens';
import { Sidebar, SidebarSection } from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import ConfidenceTier from '../components/ConfidenceTier';
import FireMap from '../components/FireMap';
import MapFlyout from '../components/MapFlyout';
import { api, type V17Cell, type ViirsFire } from '../lib/api';

interface RiskCounts {
  critical: number;
  alert: number;
  watch: number;
}

export default function LiveMapTab() {
  const [cells, setCells] = useState<V17Cell[]>([]);
  const [viirs, setViirs] = useState<ViirsFire[]>([]);
  const [selected, setSelected] = useState<V17Cell | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Layer toggles
  const [showIgnition, setShowIgnition] = useState(true);
  const [showFires, setShowFires] = useState(true);
  const [showBeats] = useState(false);
  const [showDiv] = useState(true);

  // Load v17 + VIIRS once
  useEffect(() => {
    const ctrl = new AbortController();
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [v17, fires] = await Promise.all([
          api.ignitionV17(undefined, ctrl.signal).catch(() => ({ cells: [] as V17Cell[] })),
          api
            .viirsFires(undefined, undefined, ctrl.signal)
            .catch(() => [] as ViirsFire[]),
        ]);
        // Normalize band to uppercase + coerce lat/lon numeric
        const norm = (v17.cells ?? []).map((c) => ({
          ...c,
          band: String(c.band ?? '').toUpperCase(),
          lat: Number(c.lat),
          lon: Number(c.lon),
        }));
        setCells(norm);
        setViirs(fires ?? []);
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

  const divisionCount = new Set(cells.map((c) => c.division).filter(Boolean)).size;

  const rows: { band: 'critical' | 'alert' | 'watch'; count: number; divisions: number }[] = [
    { band: 'critical', count: counts.critical, divisions: divisionCount },
    { band: 'alert',    count: counts.alert,    divisions: divisionCount },
    { band: 'watch',    count: counts.watch,    divisions: divisionCount },
  ];

  // Filter layer data based on toggles
  const displayedCells = showIgnition ? cells : [];
  const displayedFires = showFires ? viirs : [];

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <Sidebar>
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
            rows.map((row, i) => (
              <motion.div
                key={row.band}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                custom={i}
                whileHover={{ y: -1, backgroundColor: colors.bg.overlay }}
                transition={transitions.fast}
                style={{
                  background: colors.bg.raised,
                  border: `1px solid ${colors.border.subtle}`,
                  borderLeft: `3px solid ${colors.fire[row.band].fg}`,
                  borderRadius: 8,
                  padding: '12px 14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  cursor: 'pointer',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <StatusBadge
                    band={row.band}
                    size="sm"
                    pulse={row.band === 'critical' && row.count > 0}
                  />
                  <motion.span
                    className="mono"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.1 + i * 0.05 }}
                    style={{ fontSize: 20, fontWeight: 500, color: colors.text.primary }}
                  >
                    {row.count.toLocaleString()}
                  </motion.span>
                </div>
                <div style={{ fontSize: 11, color: colors.text.tertiary }}>
                  {row.divisions > 0
                    ? `across ${row.divisions} / 87 divisions`
                    : '— no data —'}
                </div>
              </motion.div>
            ))}
        </SidebarSection>

        <SidebarSection label="Model confidence">
          <div
            style={{
              background: colors.bg.raised,
              border: `1px solid ${colors.border.subtle}`,
              borderRadius: 8,
              padding: 14,
              textAlign: 'center',
            }}
          >
            <div
              className="mono"
              style={{ fontSize: 28, fontWeight: 500, color: colors.text.primary }}
            >
              22.8<span style={{ fontSize: 14, color: colors.text.tertiary }}>%</span>
            </div>
            <div className="micro" style={{ marginTop: 4 }}>
              pixel-level recall
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                gap: 4,
                marginTop: 10,
              }}
            >
              <ConfidenceTier tier="HIGH" size="sm" />
            </div>
          </div>
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
              onChange: undefined, // not wired yet
            },
            {
              icon: Layers,
              label: 'Division boundaries',
              checked: showDiv,
              onChange: undefined,
            },
          ].map(({ icon: Icon, label, checked, onChange }) => (
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
                disabled={!onChange}
                style={{ accentColor: colors.accent.base }}
              />
              <Icon size={14} color={colors.text.tertiary} />
              <span>{label}</span>
            </motion.label>
          ))}
        </SidebarSection>
      </Sidebar>

      <section style={{ flex: 1, minWidth: 0, position: 'relative' }}>
        <FireMap cells={displayedCells} viirs={displayedFires} onCellClick={setSelected} />
        <MapFlyout cell={selected} onClose={() => setSelected(null)} />
      </section>
    </div>
  );
}
