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
} from 'lucide-react';
import {
  motion,
  AnimatePresence,
  fadeUp,
  staggerContainer,
  transitions,
  useAccessibleVariants,
} from './lib/motion';
import { colors, layout as layoutTokens } from './designTokens';
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
          background: colors.bg.surface,
          borderBottom: `1px solid ${colors.border.subtle}`,
          gap: 16,
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <motion.div
            initial={{ rotate: -20, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            transition={transitions.springGentle}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 32,
              height: 32,
              borderRadius: 8,
              background: colors.fire.critical.bg,
              border: `1px solid ${colors.fire.critical.border}`,
            }}
          >
            <Flame size={18} color={colors.fire.critical.fg} strokeWidth={2.4} />
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
          {TABS.map(({ id, label, Icon }) => (
            <motion.button
              key={id}
              role="tab"
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              variants={fadeUp}
              onClick={() => setTab(id)}
              whileTap={{ scale: 0.97 }}
              transition={transitions.fast}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 14px',
                borderRadius: 999,
                background: tab === id ? colors.accent.muted : 'transparent',
                color: tab === id ? colors.accent.base : colors.text.tertiary,
                fontSize: 13,
                fontWeight: 500,
                letterSpacing: '0.01em',
                cursor: 'pointer',
                transition:
                  'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard)',
              }}
            >
              <Icon size={14} />
              <span>{label}</span>
            </motion.button>
          ))}
        </motion.nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
