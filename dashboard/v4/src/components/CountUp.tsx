// Spring-animated number that tweens from 0 (or a prior value) to target.
// Respects prefers-reduced-motion by snapping to the final value instantly.

import { useEffect, useRef } from 'react';
import {
  motion,
  useMotionValue,
  useTransform,
  animate,
  useReducedMotion,
  type MotionValue,
} from '../lib/motion';

interface CountUpProps {
  value: number;
  /** Animation duration in seconds. */
  duration?: number;
  /** Number of decimals to display. */
  decimals?: number;
  /** Suffix string appended to the animated number (e.g. "%"). */
  suffix?: string;
  /** Prefix string (e.g. "~"). */
  prefix?: string;
  /** Use thousands separator. */
  separator?: boolean;
  /** Start the animation from this value instead of 0. */
  from?: number;
}

export default function CountUp({
  value,
  duration = 1.2,
  decimals = 0,
  suffix = '',
  prefix = '',
  separator = true,
  from = 0,
}: CountUpProps) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : from);
  const rendered = useTransform(mv, (v) => format(v, decimals, separator));
  const prev = useRef(from);

  useEffect(() => {
    if (reduce) {
      mv.set(value);
      return;
    }
    const start = prev.current;
    const controls = animate(mv, value, {
      duration,
      ease: [0.22, 1, 0.36, 1] as const,
      onComplete: () => {
        prev.current = value;
      },
    });
    prev.current = start;
    return controls.stop;
  }, [value, duration, reduce, mv]);

  return (
    <span>
      {prefix}
      <motion.span>{rendered as unknown as MotionValue<string>}</motion.span>
      {suffix}
    </span>
  );
}

function format(n: number, decimals: number, separator: boolean): string {
  const rounded = Number(n).toFixed(decimals);
  if (!separator) return rounded;
  const [whole, frac] = rounded.split('.');
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return frac !== undefined ? `${withCommas}.${frac}` : withCommas;
}
