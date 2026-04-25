// DivisionsTab — 87 MP forest divisions grid with clickable detail panel.
// Data: GET /api/v2/division-overview → { data: { divisions: DivisionDetail[] } }
// Detail: right-edge slide-in, Escape to close, matching MapFlyout pattern.

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Search,
  ChevronDown,
  MapPin,
  TrendingUp,
  AlertTriangle,
  Snowflake,
  EyeOff,
  X,
  BarChart2,
  Layers,
} from 'lucide-react';
import {
  motion,
  AnimatePresence,
  slideInRight,
  staggerContainer,
  fadeUp,
  transitions,
  useAccessibleVariants,
} from '../lib/motion';
import { colors, fontFamily, radius, shadow } from '../designTokens';
import StatusBadge from '../components/StatusBadge';
import ConfidenceTier from '../components/ConfidenceTier';
import CountUp from '../components/CountUp';
import { api, type DivisionDetail } from '../lib/api';

// ---- Types ----------------------------------------------------------------

type SortKey =
  | 'critical_desc'
  | 'alpha'
  | 'max_risk_desc'
  | 'silent_first';

// ---- Helpers ---------------------------------------------------------------

function toTier(c: DivisionDetail['confidence']) {
  if (c === 'HIGH' || c === 'MEDIUM' || c === 'LOW') return c;
  return 'MEDIUM' as const;
}

function sortDivisions(list: DivisionDetail[], key: SortKey): DivisionDetail[] {
  const copy = [...list];
  switch (key) {
    case 'critical_desc':
      return copy.sort((a, b) => b.critical - a.critical || b.alert - a.alert);
    case 'alpha':
      return copy.sort((a, b) => a.name.localeCompare(b.name));
    case 'max_risk_desc':
      return copy.sort((a, b) => b.max_risk - a.max_risk);
    case 'silent_first':
      return copy.sort(
        (a, b) =>
          Number(b.silent_in_danger) - Number(a.silent_in_danger) ||
          b.critical - a.critical,
      );
  }
}

// ---- Sub-components --------------------------------------------------------

function StatRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        padding: '5px 0',
      }}
    >
      <span style={{ fontSize: 12, color: colors.text.tertiary }}>{label}</span>
      <span
        className="mono"
        style={{
          fontSize: 13,
          color: accent ?? colors.text.primary,
          fontFamily: fontFamily.mono,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </span>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 500,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: colors.text.tertiary,
        marginBottom: 8,
      }}
    >
      {children}
    </div>
  );
}

// ---- Detail panel ----------------------------------------------------------

interface DetailPanelProps {
  division: DivisionDetail | null;
  onClose: () => void;
}

function DetailPanel({ division, onClose }: DetailPanelProps) {
  const slideVariants = useAccessibleVariants(slideInRight);
  const panelRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!division) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [division, onClose]);

  // Reset scroll to top when the user clicks a different division —
  // otherwise the panel keeps the previous scroll position which can
  // hide the new division's header below the fold.
  useEffect(() => {
    panelRef.current?.scrollTo(0, 0);
  }, [division?.name]);

  return (
    <AnimatePresence>
      {division && (
        <motion.aside
          ref={panelRef as React.RefObject<HTMLElement>}
          key={division.name}
          variants={slideVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          role="dialog"
          // aria-labelledby alone — redundant aria-label was dropped
          // (some AT read both, causing duplicate announcement).
          aria-labelledby="division-detail-title"
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            bottom: 12,
            // Responsive — clamp so DetailPanel doesn't cover the full
            // grid on small tablets. min ensures readability.
            width: 'min(400px, calc(100vw - 24px))',
            minWidth: 280,
            background: 'rgba(30, 41, 59, 0.95)',
            backdropFilter: 'blur(24px) saturate(150%)',
            WebkitBackdropFilter: 'blur(24px) saturate(150%)',
            border: `1px solid ${colors.border.base}`,
            borderRadius: 16,
            padding: '20px 20px 28px',
            overflowY: 'auto',
            boxShadow: shadow[4],
            zIndex: 20,
            display: 'flex',
            flexDirection: 'column',
            gap: 0,
          }}
        >
          {/* Close button */}
          <motion.button
            onClick={onClose}
            whileHover={{ backgroundColor: 'rgba(255,255,255,0.08)' }}
            whileTap={{ scale: 0.92 }}
            transition={transitions.fast}
            aria-label="Close division detail"
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              // 44×44 minimum touch target — matches MapFlyout +
              // AIBriefDrawer post-polish.
              width: 44,
              height: 44,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: colors.text.tertiary,
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <X size={16} />
          </motion.button>

          {/* Header */}
          <div style={{ marginBottom: 16, paddingRight: 36 }}>
            <ConfidenceTier tier={toTier(division.confidence)} size="sm" />
            <h2
              style={{
                fontSize: 22,
                fontWeight: 600,
                color: colors.text.primary,
                letterSpacing: '-0.01em',
                marginTop: 8,
                marginBottom: 2,
              }}
              id="division-detail-title"
            >
              {division.name}
            </h2>
            <div
              className="mono"
              style={{
                fontSize: 11,
                color: colors.text.tertiary,
                fontFamily: fontFamily.mono,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <MapPin size={10} aria-hidden="true" />
              {division.center_lat.toFixed(4)}° N,&nbsp;
              {division.center_lon.toFixed(4)}° E
            </div>
          </div>

          {/* Alert breakdown */}
          <section
            style={{
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
              marginBottom: 14,
            }}
          >
            <SectionHeading>Alert breakdown</SectionHeading>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <StatusBadge band="critical" count={division.critical} size="sm" pulse={division.critical > 0} />
              <StatusBadge band="alert" count={division.alert} size="sm" />
              <StatusBadge band="watch" count={division.watch} size="sm" />
            </div>
            <div
              style={{
                marginTop: 10,
                display: 'flex',
                gap: 8,
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: 11, color: colors.text.tertiary }}>Total alerts:</span>
              <span
                className="mono"
                style={{
                  fontSize: 20,
                  fontWeight: 600,
                  color: colors.text.primary,
                  fontFamily: fontFamily.mono,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                <CountUp value={division.total} duration={0.8} />
              </span>
            </div>
          </section>

          {/* Risk metrics */}
          <section
            style={{
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
              marginBottom: 14,
            }}
          >
            <SectionHeading>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <TrendingUp size={10} aria-hidden="true" />
                Risk metrics
              </span>
            </SectionHeading>
            <StatRow
              label="Mean risk"
              value={division.mean_risk.toFixed(4)}
              accent={colors.fire.alert.fg}
            />
            <StatRow
              label="Max risk"
              value={division.max_risk.toFixed(4)}
              accent={
                division.max_risk > 0.5
                  ? colors.fire.critical.fg
                  : division.max_risk > 0.25
                  ? colors.fire.alert.fg
                  : colors.fire.watch.fg
              }
            />
            <StatRow
              label="Hawkes high %"
              value={`${(division.hawkes_high_pct * 100).toFixed(1)}%`}
              accent={colors.accent.base}
            />
          </section>

          {/* Critical breakdown */}
          <section
            style={{
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
              marginBottom: 14,
            }}
          >
            <SectionHeading>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <BarChart2 size={10} aria-hidden="true" />
                CRITICAL breakdown
              </span>
            </SectionHeading>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 8,
              }}
            >
              <div
                style={{
                  background: `${colors.fire.critical.bg}`,
                  border: `1px solid ${colors.fire.critical.border}`,
                  borderRadius: radius.sm,
                  padding: '8px 12px',
                }}
              >
                <div style={{ fontSize: 10, color: colors.fire.critical.fg, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                  Organic
                </div>
                <div
                  className="mono"
                  style={{
                    fontSize: 22,
                    fontWeight: 600,
                    color: colors.fire.critical.fg,
                    fontFamily: fontFamily.mono,
                  }}
                >
                  <CountUp value={division.n_critical_organic} duration={0.7} />
                </div>
                <div style={{ fontSize: 10, color: colors.text.tertiary, marginTop: 2 }}>
                  model-predicted
                </div>
              </div>
              <div
                style={{
                  // Floor-promoted is a coverage-diagnostic concept,
                  // NOT a severity. Use coverage.priorWatch tokens to
                  // avoid colliding with the ALERT severity band per
                  // the 51fdab25 token decoupling.
                  background: colors.coverage.priorWatch.bg,
                  border: `1px solid ${colors.coverage.priorWatch.border}`,
                  borderRadius: radius.sm,
                  padding: '8px 12px',
                }}
              >
                <div style={{ fontSize: 10, color: colors.coverage.priorWatch.fg, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                  Floor-promoted
                </div>
                <div
                  className="mono"
                  style={{
                    fontSize: 22,
                    fontWeight: 600,
                    color: colors.coverage.priorWatch.fg,
                    fontFamily: fontFamily.mono,
                  }}
                >
                  <CountUp value={division.n_critical_floor_promoted} duration={0.7} />
                </div>
                <div style={{ fontSize: 10, color: colors.text.tertiary, marginTop: 2 }}>
                  coverage floor
                </div>
              </div>
            </div>
          </section>

          {/* Cold-start + silent flags */}
          <section
            style={{
              paddingTop: 14,
              borderTop: `1px solid ${colors.border.subtle}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <SectionHeading>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Layers size={10} aria-hidden="true" />
                Diagnostic flags
              </span>
            </SectionHeading>

            {/* Cold-start count */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 10px',
                background: 'rgba(148, 163, 184, 0.06)',
                borderRadius: radius.sm,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: colors.text.secondary }}>
                <Snowflake size={13} color={colors.accent.base} aria-hidden="true" />
                Cold-start cells
              </span>
              <span
                className="mono"
                style={{ fontSize: 13, fontFamily: fontFamily.mono, color: colors.accent.base, fontVariantNumeric: 'tabular-nums' }}
              >
                <CountUp value={division.n_cold_start} duration={0.6} />
              </span>
            </div>
            <div style={{ fontSize: 11, color: colors.text.tertiary, paddingLeft: 4, lineHeight: 1.5 }}>
              Cells promoted due to insufficient Hawkes history (cold-start heuristic applied).
            </div>

            {/* Silent-in-danger */}
            {division.silent_in_danger && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={transitions.base}
                style={{
                  display: 'flex',
                  gap: 8,
                  padding: '10px 12px',
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: `1px solid rgba(239, 68, 68, 0.28)`,
                  borderRadius: radius.sm,
                  marginTop: 4,
                }}
              >
                <EyeOff size={14} color={colors.fire.critical.fg} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: colors.fire.critical.fg }}>
                    Silent-in-danger
                  </div>
                  <div style={{ fontSize: 11, color: colors.text.tertiary, marginTop: 3, lineHeight: 1.5 }}>
                    This division has high-risk cells but no organic CRITICAL alerts — blind-spot
                    coverage floor has been applied. Treat all CRITICAL alerts here as lower-confidence.
                  </div>
                </div>
              </motion.div>
            )}
          </section>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

// ---- Toolbar ----------------------------------------------------------------

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'critical_desc', label: 'By CRITICAL count (DESC)' },
  { value: 'alpha',         label: 'Alphabetical' },
  { value: 'max_risk_desc', label: 'By risk (max_risk DESC)' },
  { value: 'silent_first',  label: 'Silent in danger first' },
];

interface ToolbarProps {
  search: string;
  onSearch: (v: string) => void;
  sort: SortKey;
  onSort: (v: SortKey) => void;
  shown: number;
  total: number;
}

function Toolbar({ search, onSearch, sort, onSort, shown, total }: ToolbarProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '12px 20px',
        borderBottom: `1px solid ${colors.border.subtle}`,
        flexShrink: 0,
        flexWrap: 'wrap',
      }}
    >
      {/* Search */}
      <div
        style={{
          position: 'relative',
          flex: '1 1 180px',
          minWidth: 140,
          maxWidth: 280,
        }}
      >
        <Search
          size={13}
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: 10,
            top: '50%',
            transform: 'translateY(-50%)',
            color: colors.text.tertiary,
            pointerEvents: 'none',
          }}
        />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Filter divisions…"
          aria-label="Filter divisions by name"
          style={{
            width: '100%',
            paddingLeft: 30,
            paddingRight: 10,
            paddingTop: 6,
            paddingBottom: 6,
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: radius.sm,
            color: colors.text.primary,
            fontSize: 13,
            fontFamily: fontFamily.ui,
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Sort */}
      <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 180, maxWidth: 280 }}>
        <select
          value={sort}
          onChange={(e) => onSort(e.target.value as SortKey)}
          aria-label="Sort divisions"
          style={{
            width: '100%',
            appearance: 'none',
            WebkitAppearance: 'none',
            padding: '6px 30px 6px 10px',
            background: colors.bg.surface,
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: radius.sm,
            color: colors.text.secondary,
            fontSize: 13,
            fontFamily: fontFamily.ui,
            cursor: 'pointer',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          size={13}
          aria-hidden="true"
          style={{
            position: 'absolute',
            right: 10,
            top: '50%',
            transform: 'translateY(-50%)',
            color: colors.text.tertiary,
            pointerEvents: 'none',
          }}
        />
      </div>

      {/* Counter */}
      <div
        className="mono"
        style={{
          fontSize: 12,
          color: colors.text.tertiary,
          whiteSpace: 'nowrap',
          fontFamily: fontFamily.mono,
          fontVariantNumeric: 'tabular-nums',
          marginLeft: 'auto',
        }}
        aria-live="polite"
        aria-atomic="true"
      >
        {shown} of {total} divisions
      </div>
    </div>
  );
}

// ---- Card ------------------------------------------------------------------

interface DivisionCardProps {
  division: DivisionDetail;
  onSelect: (d: DivisionDetail) => void;
  variants: ReturnType<typeof useAccessibleVariants>;
  isSelected: boolean;
}

function DivisionCard({ division: d, onSelect, variants, isSelected }: DivisionCardProps) {
  return (
    <motion.article
      key={d.name}
      variants={variants}
      whileHover={{ y: -2, backgroundColor: colors.bg.raised, borderColor: colors.border.base }}
      whileTap={{ scale: 0.985 }}
      transition={transitions.fast}
      onClick={() => onSelect(d)}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      aria-label={`${d.name} division — ${d.critical} critical, ${d.alert} alert, ${d.watch} watch`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(d);
        }
      }}
      style={{
        background: isSelected ? colors.bg.raised : colors.bg.surface,
        border: `1px solid ${isSelected ? colors.border.strong : colors.border.subtle}`,
        borderRadius: 12,
        padding: 16,
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        outline: isSelected ? `2px solid ${colors.accent.base}40` : 'none',
        outlineOffset: 1,
      }}
    >
      {/* Name row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <h3
          style={{
            fontSize: 14,
            fontWeight: 500,
            color: colors.text.primary,
            lineHeight: 1.2,
          }}
        >
          {d.name}
        </h3>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center', flexShrink: 0 }}>
          {d.silent_in_danger && (
            <EyeOff
              size={12}
              color={colors.fire.critical.fg}
              aria-label="Silent in danger"
              title="Silent-in-danger: blind-spot floor applied"
            />
          )}
          <ConfidenceTier tier={toTier(d.confidence)} size="sm" />
        </div>
      </div>

      {/* Badges */}
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
        {d.critical > 0 && <StatusBadge band="critical" count={d.critical} size="sm" />}
        {d.alert > 0 && <StatusBadge band="alert" count={d.alert} size="sm" />}
        {d.watch > 0 && <StatusBadge band="watch" count={d.watch} size="sm" />}
        {d.critical === 0 && d.alert === 0 && d.watch === 0 && (
          <span style={{ fontSize: 11, color: colors.text.disabled }}>No alerts today</span>
        )}
      </div>

      {/* Footer: risk + hawkes */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: 2,
          paddingTop: 10,
          borderTop: `1px solid ${colors.border.subtle}`,
        }}
      >
        <span
          className="mono"
          style={{ fontSize: 11, color: colors.text.tertiary, fontFamily: fontFamily.mono }}
        >
          <span style={{ color: colors.text.disabled }}>risk </span>
          <span style={{ color: colors.text.secondary }}>{d.max_risk.toFixed(3)}</span>
        </span>
        <span
          className="mono"
          style={{ fontSize: 11, color: colors.text.tertiary, fontFamily: fontFamily.mono }}
        >
          <span style={{ color: colors.text.disabled }}>λ% </span>
          <span style={{ color: colors.accent.base }}>
            {(d.hawkes_high_pct * 100).toFixed(0)}%
          </span>
        </span>
        {d.n_cold_start > 0 && (
          <span
            style={{ fontSize: 10, color: colors.accent.base, display: 'flex', alignItems: 'center', gap: 3 }}
            title={`${d.n_cold_start} cold-start cells`}
          >
            <Snowflake size={10} aria-hidden="true" />
            {d.n_cold_start}
          </span>
        )}
      </div>
    </motion.article>
  );
}

// ---- Loading / error states ------------------------------------------------

function SkeletonCard() {
  // Shimmer animation matching ViirsTab.SkeletonBlock — pulse opacity
  // so the loading state feels alive, not broken.
  return (
    <div
      style={{
        background: colors.bg.surface,
        border: `1px solid ${colors.border.subtle}`,
        borderRadius: 12,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {[80, 48, 30].map((w) => (
        <motion.div
          key={w}
          animate={{ opacity: [0.4, 0.8, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
          style={{
            height: 14,
            width: `${w}%`,
            borderRadius: 6,
            background: 'rgba(148, 163, 184, 0.08)',
          }}
        />
      ))}
    </div>
  );
}

// ---- Main component --------------------------------------------------------

export default function DivisionsTab() {
  const [divisions, setDivisions] = useState<DivisionDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DivisionDetail | null>(null);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('critical_desc');

  // Fetch
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    api
      .divisionOverview(controller.signal)
      .then((data) => {
        setDivisions(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'AbortError') return;
        const msg =
          err instanceof Error ? err.message : 'Failed to load division data';
        setError(msg);
        setLoading(false);
      });

    return () => controller.abort();
  }, []);

  // Filter + sort (memoised)
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const list = needle
      ? divisions.filter((d) => d.name.toLowerCase().includes(needle))
      : divisions;
    return sortDivisions(list, sort);
  }, [divisions, search, sort]);

  const handleSelect = useCallback((d: DivisionDetail) => {
    setSelected((prev) => (prev?.name === d.name ? null : d));
  }, []);

  const handleClose = useCallback(() => setSelected(null), []);

  // Motion variants
  const containerVariants = useAccessibleVariants(staggerContainer(0.03));
  const itemVariants = useAccessibleVariants(fadeUp);

  // ---- Render ----------------------------------------------------------------

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Visually-hidden h1 for landmark consistency with the other
          tabs (ViirsTab, ValidationTab, ModelCardTab open with a
          visible h1). Screen readers + landmark navigation now include
          this tab in the heading hierarchy. */}
      <h1
        style={{
          position: 'absolute', width: 1, height: 1,
          padding: 0, margin: -1, overflow: 'hidden',
          clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap', border: 0,
        }}
      >
        Forest Divisions
      </h1>
      {/* Toolbar — always visible */}
      <Toolbar
        search={search}
        onSearch={setSearch}
        sort={sort}
        onSort={setSort}
        shown={filtered.length}
        total={divisions.length || 87}
      />

      {/* Scrollable grid area */}
      <div style={{ flex: 1, overflowY: 'auto', position: 'relative' }}>
        {/* Error state */}
        {error && (
          <div
            role="alert"
            style={{
              margin: 24,
              padding: '14px 18px',
              background: 'rgba(239, 68, 68, 0.08)',
              border: `1px solid rgba(239, 68, 68, 0.28)`,
              borderRadius: 10,
              color: colors.fire.critical.fg,
              fontSize: 13,
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
            }}
          >
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
            <div>
              <strong>Failed to load divisions</strong>
              <div style={{ marginTop: 4, color: colors.text.tertiary, fontSize: 12 }}>{error}</div>
            </div>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !error && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
              padding: 20,
            }}
            aria-label="Loading divisions"
            aria-busy="true"
          >
            {Array.from({ length: 12 }, (_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Empty search result */}
        {!loading && !error && filtered.length === 0 && (
          <div
            style={{
              padding: 40,
              textAlign: 'center',
              color: colors.text.tertiary,
              fontSize: 13,
            }}
          >
            No divisions match &ldquo;{search}&rdquo;
          </div>
        )}

        {/* Grid */}
        {!loading && !error && filtered.length > 0 && (
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
              padding: 20,
              // leave room for the detail panel overlay on wide screens
              paddingRight: selected ? 428 : 20,
              transition: 'padding-right 0.28s ease',
            }}
          >
            {filtered.map((d) => (
              <DivisionCard
                key={d.name}
                division={d}
                onSelect={handleSelect}
                variants={itemVariants}
                isSelected={selected?.name === d.name}
              />
            ))}
          </motion.div>
        )}

        {/* Detail panel (absolutely positioned over scroll area) */}
        <DetailPanel division={selected} onClose={handleClose} />
      </div>
    </div>
  );
}
