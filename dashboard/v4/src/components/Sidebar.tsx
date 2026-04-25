import type { ReactNode } from 'react';
import { motion, staggerContainer, fadeUp, useAccessibleVariants } from '../lib/motion';
import { colors, layout as layoutTokens } from '../designTokens';

interface SidebarProps {
  children: ReactNode;
  width?: string;
}

export function Sidebar({ children, width = layoutTokens.sidebarWidth }: SidebarProps) {
  const stagger = useAccessibleVariants(staggerContainer());
  return (
    <motion.aside
      data-role="sidebar"
      aria-label="Map controls and alert summary"
      variants={stagger}
      initial="hidden"
      animate="visible"
      style={{
        width,
        flexShrink: 0,
        background: colors.bg.surface,
        borderRight: `1px solid ${colors.border.subtle}`,
        padding: '18px 16px',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 22,
      }}
    >
      {children}
    </motion.aside>
  );
}

interface SidebarSectionProps {
  label: string;
  children: ReactNode;
}

export function SidebarSection({ label, children }: SidebarSectionProps) {
  return (
    <motion.div variants={fadeUp}>
      <div
        className="micro"
        style={{
          fontSize: 11,
          fontWeight: 500,
          color: colors.text.tertiary,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: 12,
        }}
      >
        {label}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{children}</div>
    </motion.div>
  );
}

export default Sidebar;
