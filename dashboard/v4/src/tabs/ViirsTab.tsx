// ViirsTab — Historical FIRMS VIIRS fire detections browser (2014–today).
// Supports quick-preset date ranges, loading skeletons, CountUp stats,
// per-month bar chart (PlotlyChart), and a top-10 division leaderboard.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart2,
  Calendar,
  Flame,
  Info,
  Loader2,
  TreePine,
} from 'lucide-react';
import {
  AnimatePresence,
  fadeUp,
  motion,
  transitions,
  useAccessibleVariants,
} from '../lib/motion';
import { colors, fontFamily } from '../designTokens';
import StatusBadge from '../components/StatusBadge';
import CountUp from '../components/CountUp';
import PlotlyChart from '../components/PlotlyChart';
import { api, type ViirsFire, type ViirsMeta } from '../lib/api';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Preset {
  label: string;
  from: string;
  to: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const today = () => new Date().toISOString().slice(0, 10);

function seasonRange(year: number): { from: string; to: string } {
  return { from: `${year}-02-01`, to: `${year}-05-31` };
}

function buildPresets(): Preset[] {
  const todayStr = today();
  const year = new Date().getFullYear();

  const presets: Preset[] = [
    {
      label: 'This week',
      from: new Date(Date.now() - 6 * 86_400_000).toISOString().slice(0, 10),
      to: todayStr,
    },
    {
      label: `${year} season (Feb–May)`,
      ...seasonRange(year),
    },
  ];

  // Add last 5 seasons back to 2014
  for (let y = year - 1; y >= 2014 && presets.length < 8; y--) {
    presets.push({ label: `${y} season`, ...seasonRange(y) });
  }

  // Full-year "all fires" for 2014–(year-1)
  presets.push({ label: 'Full 2014–today', from: '2014-01-01', to: todayStr });

  return presets;
}

const PRESETS = buildPresets();

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

// ─── Derived aggregates ───────────────────────────────────────────────────────

interface MonthBucket {
  label: string; // "2024-03"
  count: number;
}

interface DivisionBucket {
  division: string;
  count: number;
}

function aggregateByMonth(fires: ViirsFire[]): MonthBucket[] {
  const map = new Map<string, number>();
  for (const f of fires) {
    const key = f.date?.slice(0, 7) ?? 'unknown';
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, count]) => ({ label, count }));
}

function aggregateByDivision(fires: ViirsFire[]): DivisionBucket[] {
  const map = new Map<string, number>();
  for (const f of fires) {
    const div = f.division ?? 'Unknown';
    map.set(div, (map.get(div) ?? 0) + 1);
  }
  return [...map.entries()]
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10)
    .map(([division, count]) => ({ division, count }));
}

function formatDate(d: string | undefined) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span
        className="micro"
        style={{ color: colors.text.tertiary, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase' }}
      >
        {label}
      </span>
      <input
        type="date"
        value={value}
        min="2014-01-01"
        max={today()}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '9px 12px',
          borderRadius: 8,
          background: colors.bg.raised,
          border: `1px solid ${colors.border.base}`,
          color: colors.text.primary,
          fontFamily: fontFamily.mono,
          fontSize: 13,
          minWidth: 152,
          outline: 'none',
        }}
      />
    </label>
  );
}

function SkeletonBlock({ height = 80, width = '100%' }: { height?: number; width?: string | number }) {
  return (
    <motion.div
      animate={{ opacity: [0.4, 0.8, 0.4] }}
      transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
      style={{
        height,
        width,
        borderRadius: 8,
        background: colors.bg.raised,
      }}
    />
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: number | null;
  sub?: string;
  color?: string;
}) {
  return (
    <div
      style={{
        flex: '1 1 180px',
        background: colors.bg.surface,
        border: `1px solid ${colors.border.subtle}`,
        borderRadius: 12,
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <span
        className="micro"
        style={{ color: colors.text.tertiary, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}
      >
        {label}
      </span>
      <span
        className="mono"
        style={{
          fontSize: 36,
          fontWeight: 600,
          lineHeight: 1,
          color: color ?? colors.text.primary,
          letterSpacing: '-0.02em',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value === null ? '—' : <CountUp value={value} duration={1.4} />}
      </span>
      {sub && (
        <span style={{ fontSize: 12, color: colors.text.tertiary }}>{sub}</span>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface FetchResult {
  fires: ViirsFire[];
  meta: ViirsMeta;
}

export default function ViirsTab() {
  const defaultPreset = PRESETS[1]; // current-year season
  const [from, setFrom] = useState(defaultPreset.from);
  const [to, setTo] = useState(defaultPreset.to);
  const [result, setResult] = useState<FetchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const item = useAccessibleVariants(fadeUp);

  const loadFires = useCallback(
    async (fromDate: string, toDate: string) => {
      // Cancel any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const env = await api.viirsFires(fromDate, toDate, controller.signal);
        setResult({ fires: env.data ?? [], meta: env.meta ?? {} });
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        const msg =
          err instanceof Error ? err.message : 'Failed to load VIIRS data';
        setError(msg);
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // Auto-load on mount
  useEffect(() => {
    loadFires(from, to);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyPreset = (p: Preset) => {
    setFrom(p.from);
    setTo(p.to);
    loadFires(p.from, p.to);
  };

  const handleLoad = () => loadFires(from, to);

  // ── Derived data ──────────────────────────────────────────────────────────
  const fires = result?.fires ?? [];
  const meta = result?.meta ?? {};

  const monthBuckets = useMemo(() => aggregateByMonth(fires), [fires]);
  const divisionBuckets = useMemo(() => aggregateByDivision(fires), [fires]);

  const clipRatio =
    meta.n_before_clip && meta.n_before_clip > 0
      ? ((meta.n_before_clip - (meta.n_clipped ?? 0)) / meta.n_before_clip) * 100
      : null;

  // ── Bar chart: color bars by intensity (max bucket = red, min = yellow) ───
  const chartData = useMemo(() => {
    if (monthBuckets.length === 0) return null;
    const maxCount = Math.max(...monthBuckets.map((b) => b.count), 1);
    const barColors = monthBuckets.map((b) => {
      const t = b.count / maxCount; // 0–1
      // Interpolate from amber (#FBBF24) → red (#EF4444)
      const r = Math.round(251 + (239 - 251) * t);
      const g = Math.round(191 + (68 - 191) * t);
      const bl = Math.round(36 + (68 - 36) * t);
      return `rgba(${r},${g},${bl},0.85)`;
    });

    // Build nice x-axis tick labels: "Mar 2024"
    const xLabels = monthBuckets.map((b) => {
      const [y, m] = b.label.split('-');
      return `${MONTH_LABELS[parseInt(m, 10) - 1]} ${y}`;
    });

    return { xLabels, counts: monthBuckets.map((b) => b.count), barColors };
  }, [monthBuckets]);

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      style={{
        padding: '32px 48px',
        overflowY: 'auto',
        height: '100%',
        maxWidth: 1040,
        margin: '0 auto',
      }}
    >
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.06 } },
        }}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <motion.header variants={item} style={{ marginBottom: 28 }}>
          <div
            className="micro"
            style={{ color: colors.text.tertiary, marginBottom: 6, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase' }}
          >
            Historical detections · NASA FIRMS VIIRS
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 500, color: colors.text.primary }}>
            VIIRS Fire Viewer
          </h1>
          <p style={{ marginTop: 8, color: colors.text.secondary, fontSize: 13, lineHeight: 1.6, maxWidth: 680 }}>
            Forest-clipped FIRMS VIIRS active fire detections from 2014 through today.
            1.35M historical rows spatially joined to 8,973 MP beat polygons —
            ~75% of raw pixels fall outside forest areas and are removed.
            Full-year queries can take 5–30 s.
          </p>
        </motion.header>

        {/* ── Quick presets + date pickers ───────────────────────────────── */}
        <motion.section
          variants={item}
          style={{
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: 12,
            padding: 20,
            marginBottom: 20,
          }}
        >
          {/* Preset pills row */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
              marginBottom: 16,
            }}
          >
            {PRESETS.map((p) => {
              const active = p.from === from && p.to === to;
              return (
                <motion.button
                  key={p.label}
                  onClick={() => applyPreset(p)}
                  whileHover={{ backgroundColor: active ? undefined : 'rgba(255,255,255,0.06)' }}
                  whileTap={{ scale: 0.97 }}
                  transition={transitions.fast}
                  style={{
                    padding: '5px 12px',
                    borderRadius: 999,
                    background: active ? colors.accent.muted : 'transparent',
                    border: `1px solid ${active ? colors.accent.base : colors.border.base}`,
                    color: active ? colors.accent.hover : colors.text.secondary,
                    fontSize: 12,
                    fontWeight: active ? 500 : 400,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    letterSpacing: '0.01em',
                  }}
                  aria-pressed={active}
                >
                  <Calendar size={12} aria-hidden="true" />
                  {p.label}
                </motion.button>
              );
            })}
          </div>

          {/* Date range pickers */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
            <DateField label="From" value={from} onChange={setFrom} />
            <DateField label="To" value={to} onChange={setTo} />

            <motion.button
              onClick={handleLoad}
              disabled={loading}
              whileHover={{ backgroundColor: loading ? undefined : colors.accent.hover }}
              whileTap={{ scale: loading ? 1 : 0.97 }}
              transition={transitions.fast}
              style={{
                padding: '10px 20px',
                borderRadius: 999,
                background: colors.accent.base,
                color: colors.text.onAccent,
                fontSize: 13,
                fontWeight: 500,
                letterSpacing: '0.01em',
                cursor: loading ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                opacity: loading ? 0.6 : 1,
              }}
              aria-busy={loading}
            >
              {loading ? (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                  style={{ display: 'inline-flex' }}
                >
                  <Loader2 size={14} />
                </motion.span>
              ) : (
                <Flame size={14} />
              )}
              {loading ? 'Loading…' : 'Load detections'}
            </motion.button>
          </div>
        </motion.section>

        {/* ── Error state ────────────────────────────────────────────────── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={transitions.base}
              style={{
                marginBottom: 20,
                padding: '14px 18px',
                borderRadius: 10,
                background: colors.fire.critical.bg,
                border: `1px solid ${colors.fire.critical.border}`,
                color: colors.fire.critical.fg,
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
              role="alert"
            >
              <Info size={14} aria-hidden="true" />
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Loading skeleton ───────────────────────────────────────────── */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={transitions.base}
              style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 16 }}
              aria-label="Loading fire detections"
              role="status"
            >
              <div style={{ display: 'flex', gap: 16 }}>
                <SkeletonBlock height={96} />
                <SkeletonBlock height={96} />
                <SkeletonBlock height={96} />
              </div>
              <SkeletonBlock height={200} />
              <SkeletonBlock height={140} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Results ────────────────────────────────────────────────────── */}
        <AnimatePresence>
          {!loading && result !== null && (
            <motion.div
              key="results"
              initial="hidden"
              animate="visible"
              exit={{ opacity: 0 }}
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.07 } } }}
            >
              {/* Zero-fires empty state */}
              {fires.length === 0 ? (
                <motion.div
                  variants={item}
                  style={{
                    background: colors.bg.surface,
                    border: `1px solid ${colors.border.subtle}`,
                    borderRadius: 12,
                    padding: '48px 32px',
                    textAlign: 'center',
                    marginBottom: 20,
                  }}
                >
                  <TreePine
                    size={40}
                    style={{ color: colors.text.disabled, marginBottom: 16 }}
                    aria-hidden="true"
                  />
                  <div style={{ fontSize: 15, fontWeight: 500, color: colors.text.secondary }}>
                    0 forest-clipped fires for this period
                  </div>
                  {meta.n_before_clip != null && meta.n_before_clip > 0 && (
                    <div style={{ marginTop: 10, fontSize: 13, color: colors.text.tertiary }}>
                      {meta.n_before_clip.toLocaleString()} raw FIRMS detections found, but all
                      fell outside forest beat boundaries (or historical beat clip wasn't backfilled
                      for this year).
                    </div>
                  )}
                  <div style={{ marginTop: 8, fontSize: 12, color: colors.text.disabled }}>
                    {formatDate(from)} – {formatDate(to)}
                  </div>
                </motion.div>
              ) : (
                <>
                  {/* ── Stat cards ───────────────────────────────────────── */}
                  <motion.div
                    variants={item}
                    style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}
                  >
                    <StatCard
                      label="Forest-clipped fire pixels"
                      value={meta.total ?? fires.length}
                      sub={`${formatDate(from)} – ${formatDate(to)}`}
                      color={colors.fire.confirmed.fg}
                    />
                    <StatCard
                      label="Raw FIRMS detections"
                      value={meta.n_before_clip ?? null}
                      sub="Before spatial join to beats"
                      color={colors.text.secondary}
                    />
                    {clipRatio !== null && (
                      <StatCard
                        label="Forest clip ratio"
                        value={Math.round(clipRatio)}
                        sub="% of raw pixels inside forest beats"
                        color={colors.fire.watch.fg}
                      />
                    )}
                  </motion.div>

                  {/* Date range pill */}
                  <motion.div
                    variants={item}
                    style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}
                  >
                    <StatusBadge band="confirmed" label="FOREST-CLIPPED" count={meta.total ?? fires.length} size="sm" />
                    <StatusBadge band="info" label={`${formatDate(meta.date_range?.from ?? from)} – ${formatDate(meta.date_range?.to ?? to)}`} size="sm" />
                    {meta.latest_date && (
                      <StatusBadge band="watch" label={`Latest: ${formatDate(meta.latest_date)}`} size="sm" />
                    )}
                  </motion.div>

                  {/* ── Monthly bar chart ────────────────────────────────── */}
                  {chartData && (
                    <motion.section
                      variants={item}
                      style={{
                        background: colors.bg.surface,
                        border: `1px solid ${colors.border.subtle}`,
                        borderRadius: 12,
                        padding: '20px 20px 8px',
                        marginBottom: 20,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          marginBottom: 16,
                        }}
                      >
                        <BarChart2 size={16} style={{ color: colors.fire.alert.fg }} aria-hidden="true" />
                        <span style={{ fontSize: 13, fontWeight: 500, color: colors.text.secondary }}>
                          Fires per month
                        </span>
                        <span style={{ fontSize: 12, color: colors.text.disabled, marginLeft: 4 }}>
                          ({monthBuckets.length} months · bar color = relative intensity)
                        </span>
                      </div>
                      <PlotlyChart
                        height={280}
                        data={[
                          {
                            type: 'bar',
                            x: chartData.xLabels,
                            y: chartData.counts,
                            marker: {
                              color: chartData.barColors,
                              line: { color: 'rgba(0,0,0,0.25)', width: 0.5 },
                            },
                            hovertemplate: '<b>%{x}</b><br>%{y} fires<extra></extra>',
                          },
                        ]}
                        layout={{
                          xaxis: {
                            tickangle: chartData.xLabels.length > 18 ? -45 : -30,
                            automargin: true,
                          },
                          yaxis: { title: { text: 'Fire pixels', font: { size: 11 } } },
                          bargap: 0.15,
                        }}
                      />
                    </motion.section>
                  )}

                  {/* ── Top-10 division leaderboard ──────────────────────── */}
                  {divisionBuckets.length > 0 && (
                    <motion.section
                      variants={item}
                      style={{
                        background: colors.bg.surface,
                        border: `1px solid ${colors.border.subtle}`,
                        borderRadius: 12,
                        padding: 20,
                        marginBottom: 20,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          marginBottom: 16,
                        }}
                      >
                        <Flame size={16} style={{ color: colors.fire.critical.fg }} aria-hidden="true" />
                        <span style={{ fontSize: 13, fontWeight: 500, color: colors.text.secondary }}>
                          Top 10 divisions by fire detections
                        </span>
                      </div>

                      <div role="list" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {divisionBuckets.map((d, i) => {
                          const maxCount = divisionBuckets[0]?.count ?? 1;
                          const pct = (d.count / maxCount) * 100;
                          return (
                            <motion.div
                              key={d.division}
                              role="listitem"
                              initial={{ opacity: 0, x: -8 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ ...transitions.base, delay: i * 0.04 }}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 12,
                                padding: '8px 12px',
                                borderRadius: 8,
                                background: i === 0 ? colors.fire.confirmed.bg : 'transparent',
                                border: `1px solid ${i === 0 ? colors.fire.confirmed.border : colors.border.divider}`,
                              }}
                            >
                              {/* Rank */}
                              <span
                                className="mono"
                                style={{
                                  fontSize: 11,
                                  color: colors.text.disabled,
                                  minWidth: 20,
                                  textAlign: 'right',
                                  fontVariantNumeric: 'tabular-nums',
                                }}
                              >
                                {i + 1}
                              </span>

                              {/* Division name */}
                              <span
                                style={{
                                  flex: '0 0 180px',
                                  fontSize: 13,
                                  color: colors.text.primary,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={d.division}
                              >
                                {d.division}
                              </span>

                              {/* Progress bar */}
                              <div
                                style={{
                                  flex: 1,
                                  height: 6,
                                  borderRadius: 999,
                                  background: colors.bg.raised,
                                  overflow: 'hidden',
                                }}
                                aria-hidden="true"
                              >
                                <motion.div
                                  initial={{ width: 0 }}
                                  animate={{ width: `${pct}%` }}
                                  transition={{ duration: 0.6, delay: i * 0.04, ease: [0.2, 0, 0, 1] }}
                                  style={{
                                    height: '100%',
                                    borderRadius: 999,
                                    background:
                                      i === 0
                                        ? colors.fire.confirmed.fg
                                        : i < 3
                                        ? colors.fire.watch.fg
                                        : colors.fire.info.fg,
                                  }}
                                />
                              </div>

                              {/* Count + badge */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
                                <span
                                  className="mono"
                                  style={{
                                    fontSize: 13,
                                    fontWeight: 600,
                                    color: colors.text.primary,
                                    fontVariantNumeric: 'tabular-nums',
                                    minWidth: 56,
                                    textAlign: 'right',
                                  }}
                                >
                                  {d.count.toLocaleString()}
                                </span>
                                <StatusBadge band="confirmed" label="CONFIRMED" size="sm" />
                              </div>
                            </motion.div>
                          );
                        })}
                      </div>
                    </motion.section>
                  )}
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
