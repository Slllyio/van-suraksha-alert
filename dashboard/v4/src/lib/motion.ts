// Framer-motion wrapper — respects prefers-reduced-motion, uses design tokens.
// Import everything from here, not directly from framer-motion, so motion discipline
// stays centralized.

import {
  motion,
  AnimatePresence,
  useReducedMotion,
  useMotionValue,
  useTransform,
  animate,
  type Transition,
  type Variants,
  type MotionValue,
} from 'framer-motion';
import { duration, ease, spring, stagger } from '../designTokens';

export {
  motion,
  AnimatePresence,
  useReducedMotion,
  useMotionValue,
  useTransform,
  animate,
};
export type { Transition, Variants, MotionValue };

// ---- Ready-made transitions ----

export const transitions = {
  fast: {
    duration: duration.fast,
    ease: ease.standard,
  } satisfies Transition,

  base: {
    duration: duration.base,
    ease: ease.standard,
  } satisfies Transition,

  slow: {
    duration: duration.slow,
    ease: ease.emphasized,
  } satisfies Transition,

  exit: {
    duration: duration.fast,
    ease: ease.exit,
  } satisfies Transition,

  springGentle: spring.gentle,
  springDefault: spring.default,
  springMapPin: spring.mapPin,
} as const;

// ---- Common variants ----

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: transitions.base },
  exit: { opacity: 0, y: 4, transition: transitions.exit },
};

export const fade: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: transitions.base },
  exit: { opacity: 0, transition: transitions.exit },
};

export const slideInRight: Variants = {
  hidden: { x: '100%', opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: transitions.slow,
  },
  exit: {
    x: '100%',
    opacity: 0,
    transition: transitions.exit,
  },
};

export const staggerContainer = (staggerDelay: number = stagger.card): Variants => ({
  hidden: { opacity: 1 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: staggerDelay,
      delayChildren: 0.04,
    },
  },
});

// ---- Hook: reduced-motion aware variants ----

/**
 * Returns the supplied variants unchanged unless `prefers-reduced-motion` is on,
 * in which case returns instant/no-op variants. Use on every animated component.
 */
export function useAccessibleVariants(variants: Variants): Variants {
  const reduce = useReducedMotion();
  if (!reduce) return variants;

  const flattened: Variants = {};
  for (const key of Object.keys(variants)) {
    flattened[key] = {
      opacity: key === 'hidden' ? 0 : 1,
      transition: { duration: 0 },
    };
  }
  return flattened;
}
