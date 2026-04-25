import { useState } from 'react';
import {
  Flame,
  LayoutDashboard,
  MapPin,
  LineChart as LineChartIcon,
  ListChecks,
  Satellite,
  HelpCircle,
  Bell,
  Clock,
  Sparkles,
} from 'lucide-react';
import AIBriefDrawer from './components/AIBriefDrawer';
import {
  motion,
  AnimatePresence,
  fadeUp,
  staggerContainer,
  transitions,
  useAccessibleVariants,
} from './lib/motion';
import { colors, layout as layoutTokens } from './designTokens';
import { playCue, hapticTap } from './lib/feedback';
import LiveMapTab from './tabs/LiveMapTab';
import DivisionsTab from './tabs/DivisionsTab';
import ModelCardTab from './tabs/ModelCardTab';
import ValidationTab from './tabs/ValidationTab';
import ViirsTab from './tabs/ViirsTab';
import './theme.css';

type TabId = 'map' | 'divisions' | 'model' | 'validation' | 'viirs';

const TABS: { id: TabId; label: string; Icon: typeof MapPin }[] = [
  { id: 'map',        label: 'Live Map',    Icon: MapPin },
  { id: 'divisions',  label: 'Divisions',   Icon: LayoutDashboard },
  { id: 'model',      label: 'Model Card',  Icon: LineChartIcon },
  { id: 'validation', label: 'Validation',  Icon: ListChecks },
  { id: 'viirs',      label: 'VIIRS Fires', Icon: Satellite },
];

export default function App() {
  const [tab, setTab] = useState<TabId>('map');
  const [briefOpen, setBriefOpen] = useState(false);
  const headerVariants = useAccessibleVariants(fadeUp);
  const stagger = useAccessibleVariants(staggerContainer());

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <a href="#main" className="skip-link">Skip to main content</a>

      <motion.header
        initial="hidden"
        animate="visible"
        variants={headerVariants}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: `0 ${layoutTokens.cardPadding} 0 20px`,
          height: layoutTokens.headerHeight,
          background: `linear-gradient(90deg, ${colors.bg.surface} 0%, #1a2d4a 40%, ${colors.bg.surface} 100%)`,
          backgroundSize: '200% 100%',
          borderBottom: `1px solid ${colors.border.subtle}`,
          gap: 16,
          flexShrink: 0,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Ambient atmosphere glow sweeping slowly across the header */}
        <motion.div
          aria-hidden
          animate={{ backgroundPosition: ['0% 0%', '100% 0%', '0% 0%'] }}
          transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `radial-gradient(600px circle at 30% 50%, ${colors.accent.muted} 0%, transparent 50%)`,
            backgroundSize: '200% 100%',
            pointerEvents: 'none',
            opacity: 0.7,
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, position: 'relative', zIndex: 1 }}>
          <motion.div
            initial={{ rotate: -20, opacity: 0, scale: 0.5 }}
            animate={{
              rotate: 0,
              opacity: 1,
              scale: 1,
              boxShadow: [
                `0 0 0 0 ${colors.fire.critical.border}`,
                `0 0 0 6px rgba(239, 68, 68, 0)`,
                `0 0 0 0 ${colors.fire.critical.border}`,
              ],
            }}
            transition={{
              rotate: transitions.springGentle,
              opacity: transitions.springGentle,
              scale: transitions.springGentle,
              boxShadow: { duration: 2.4, repeat: Infinity, ease: 'easeOut' },
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 34,
              height: 34,
              borderRadius: 10,
              background: colors.fire.critical.bg,
              border: `1px solid ${colors.fire.critical.border}`,
            }}
          >
            {/* Breathing flame — subtle scale loop */}
            <motion.div
              animate={{ scale: [1, 1.12, 1], rotate: [0, -3, 3, 0] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
              style={{ display: 'inline-flex' }}
            >
              <Flame size={18} color={colors.fire.critical.fg} strokeWidth={2.4} />
            </motion.div>
          </motion.div>
          <div>
            <h1 style={{ fontSize: 17, lineHeight: 1.1 }}>
              <span style={{ color: colors.text.primary, fontWeight: 600 }}>Jwala</span>
              <span style={{ color: colors.fire.critical.fg, fontWeight: 600 }}>Netra</span>
            </h1>
            <div
              className="micro"
              style={{ fontSize: 10, marginTop: 2, color: colors.text.tertiary }}
            >
              MP Forest Fire EWS · v17.5
            </div>
          </div>
        </div>

        <motion.nav
          variants={stagger}
          initial="hidden"
          animate="visible"
          style={{
            display: 'flex',
            gap: 4,
            background: 'rgba(15, 23, 42, 0.6)',
            border: `1px solid ${colors.border.subtle}`,
            borderRadius: 999,
            padding: 4,
          }}
          role="tablist"
          aria-label="Portal sections"
        >
          {TABS.map(({ id, label, Icon }) => {
            const active = tab === id;
            return (
              <motion.button
                key={id}
                role="tab"
                aria-selected={active}
                aria-controls={`panel-${id}`}
                variants={fadeUp}
                onClick={() => {
                  if (tab !== id) {
                    setTab(id);
                    playCue('tab');
                    hapticTap(8);
                  }
                }}
                whileHover={!active ? { color: colors.text.primary } : undefined}
                whileTap={{ scale: 0.95 }}
                transition={transitions.fast}
                style={{
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '8px 16px',
                  borderRadius: 999,
                  background: 'transparent',
                  color: active ? colors.accent.base : colors.text.tertiary,
                  fontSize: 13,
                  fontWeight: 500,
                  letterSpacing: '0.01em',
                  cursor: 'pointer',
                  zIndex: 1,
                }}
              >
                {active && (
                  <motion.span
                    layoutId="active-tab-pill"
                    aria-hidden
                    transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                    style={{
                      position: 'absolute',
                      inset: 0,
                      borderRadius: 999,
                      background: `linear-gradient(120deg, ${colors.accent.muted}, rgba(138,180,248,.28), ${colors.accent.muted})`,
                      backgroundSize: '200% 100%',
                      border: `1px solid rgba(138,180,248,.36)`,
                      zIndex: -1,
                    }}
                  />
                )}
                <Icon size={14} />
                <span>{label}</span>
              </motion.button>
            );
          })}
        </motion.nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Brief me button — glowing AI trigger */}
          <motion.button
            onClick={() => {
              setBriefOpen(true);
              playCue('open');
              hapticTap(8);
            }}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.96 }}
            animate={{
              boxShadow: briefOpen
                ? 'none'
                : [
                    '0 0 0 0 rgba(59,130,246,0)',
                    '0 0 8px 2px rgba(59,130,246,0.45)',
                    '0 0 0 0 rgba(59,130,246,0)',
                  ],
            }}
            transition={{
              ...transitions.fast,
              boxShadow: { duration: 2.4, repeat: Infinity, ease: 'easeOut' },
            }}
            aria-label="Open AI daily brief"
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 13px',
              borderRadius: 999,
              background: briefOpen
                ? colors.accent.muted
                : 'linear-gradient(120deg, rgba(59,130,246,0.22), rgba(59,130,246,0.12))',
              border: `1px solid ${briefOpen ? colors.accent.base : 'rgba(59,130,246,0.42)'}`,
              color: colors.accent.hover,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              letterSpacing: '0.01em',
            }}
          >
            <Sparkles size={13} />
            <span>Brief me</span>
          </motion.button>

          <motion.button
            whileHover={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
            whileTap={{ scale: 0.95 }}
            transition={transitions.fast}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 36, height: 36, borderRadius: 8, color: colors.text.tertiary,
            }}
            aria-label="Notifications"
          >
            <Bell size={16} />
          </motion.button>
          <motion.button
            whileHover={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
            whileTap={{ scale: 0.95 }}
            transition={transitions.fast}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 36, height: 36, borderRadius: 8, color: colors.text.tertiary,
            }}
            aria-label="Help"
          >
            <HelpCircle size={16} />
          </motion.button>
          <div
            className="mono"
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 11, color: colors.text.tertiary,
            }}
          >
            <Clock size={12} />
            <span>IST · live</span>
          </div>
        </div>
      </motion.header>

      {/* AI Brief Drawer — portal-level overlay, not scoped to any tab */}
      <AIBriefDrawer open={briefOpen} onClose={() => setBriefOpen(false)} />

      <main
        id="main"
        style={{ flex: 1, minHeight: 0, overflow: 'hidden', position: 'relative' }}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={transitions.base}
            style={{ position: 'absolute', inset: 0 }}
            id={`panel-${tab}`}
            role="tabpanel"
          >
            {tab === 'map'        && <LiveMapTab />}
            {tab === 'divisions'  && <DivisionsTab />}
            {tab === 'model'      && <ModelCardTab />}
            {tab === 'validation' && <ValidationTab />}
            {tab === 'viirs'      && <ViirsTab />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
