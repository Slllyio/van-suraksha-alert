// Ambient floating particles — lightweight canvas-based ember/ash drift above
// the map. Respects prefers-reduced-motion (renders a static layer).
// Absolute-positioned, pointer-events: none, so it never blocks interaction.

import { useEffect, useRef } from 'react';
import { useReducedMotion } from '../lib/motion';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  hue: number; // 0–20 (red) for ember; 200–220 for cool ash
}

export default function FloatingParticles({ count = 14 }: { count?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    // Initialize particles — subtle embers + ash, low alpha + slow drift so
    // they read as atmosphere, not foreground noise.
    const particles: Particle[] = Array.from({ length: count }, () => ({
      x: Math.random() * canvas.clientWidth,
      y: Math.random() * canvas.clientHeight,
      vx: (Math.random() - 0.5) * 0.08,
      vy: -0.05 - Math.random() * 0.1, // gentle upward
      size: 0.3 + Math.random() * 1.0,
      alpha: 0.06 + Math.random() * 0.12,
      hue: Math.random() < 0.5 ? 14 + Math.random() * 14 : 210 + Math.random() * 20,
    }));

    let raf = 0;
    const tick = () => {
      if (!ctx) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        // Wrap/respawn at edges
        if (p.y < -4) {
          p.y = h + 4;
          p.x = Math.random() * w;
        }
        if (p.x < -4) p.x = w + 4;
        if (p.x > w + 4) p.x = -4;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${p.hue}, 70%, 60%, ${p.alpha})`;
        ctx.fill();
      }
      if (!reduce) raf = requestAnimationFrame(tick);
    };

    if (reduce) {
      // Render a single static frame
      tick();
    } else {
      raf = requestAnimationFrame(tick);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [count, reduce]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 2,
        opacity: 0.8,
      }}
    />
  );
}
