// Audio + haptic cues — minimal Web Audio beep (no external samples) + vibrate.
// Both are opt-in: a user gesture must happen first (browser autoplay policy).
// Lightweight — total JS ~1 KB, no dependencies.

let ctx: AudioContext | null = null;
let muted = false;

function getCtx(): AudioContext | null {
  if (muted) return null;
  if (ctx) return ctx;
  try {
    const AC =
      (window as unknown as { AudioContext?: typeof AudioContext }).AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    return ctx;
  } catch {
    return null;
  }
}

export type CueKind = 'open' | 'close' | 'tab' | 'alert';

const CUE_CONFIG: Record<CueKind, { freq: number; duration: number; type: OscillatorType; gain: number }> = {
  open:  { freq: 880, duration: 0.09, type: 'sine',     gain: 0.04 },
  close: { freq: 620, duration: 0.07, type: 'sine',     gain: 0.03 },
  tab:   { freq: 1040, duration: 0.04, type: 'triangle', gain: 0.02 },
  alert: { freq: 440, duration: 0.12, type: 'square',   gain: 0.05 },
};

/** Play a short UI cue. Silently no-ops if audio is unavailable or muted. */
export function playCue(kind: CueKind): void {
  const c = getCtx();
  if (!c) return;
  try {
    const cfg = CUE_CONFIG[kind];
    const now = c.currentTime;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = cfg.type;
    osc.frequency.setValueAtTime(cfg.freq, now);
    // Quick attack + exponential decay to avoid pops
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(cfg.gain, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + cfg.duration);
    osc.connect(gain);
    gain.connect(c.destination);
    osc.start(now);
    osc.stop(now + cfg.duration + 0.02);
  } catch {
    /* autoplay policy or closed context — ignore */
  }
}

/** Vibrate on devices that support it (mobile). No-op on desktop. */
export function hapticTap(pattern: number | number[] = 10): void {
  if (typeof navigator === 'undefined') return;
  const nav = navigator as Navigator & { vibrate?: (p: number | number[]) => boolean };
  if (typeof nav.vibrate === 'function') {
    try {
      nav.vibrate(pattern);
    } catch {
      /* ignore */
    }
  }
}

export function setAudioMuted(next: boolean): void {
  muted = next;
  if (!next && !ctx) getCtx();
  if (next && ctx) {
    ctx.close().catch(() => {});
    ctx = null;
  }
}

export function isAudioMuted(): boolean {
  return muted;
}
