// AIBriefDrawer — full-height right-edge sliding drawer with daily AI briefing.
// Opens via the "Brief me" header button. Auto-fires initial summary on open,
// then accepts follow-up questions.
//
// Backend: POST /api/v2/ai/chat → SSE stream of {type:'delta'|'done'|'tool', ...}
// Fallback (backend unreachable): client-side stub using ai-tools.ts directly.

import { useCallback, useEffect, useRef, useState } from 'react';
import { X, Send, Sparkles, AlertTriangle, Bot } from 'lucide-react';
import { motion, AnimatePresence, transitions, useAccessibleVariants } from '../lib/motion';
import { colors, radius, shadow } from '../designTokens';
import { getDivisionOverview, getCriticalCells } from '../lib/ai-tools';

// ---- Types ------------------------------------------------------------------

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  streaming?: boolean;
}

let _msgSeq = 0;
const newMsgId = () => `m${++_msgSeq}-${Date.now().toString(36)}`;

interface AIBriefDrawerProps {
  open: boolean;
  onClose: () => void;
}

// ---- Slide-in variant -------------------------------------------------------

const drawerVariants = {
  hidden: { x: '100%', opacity: 0 },
  visible: { x: 0, opacity: 1, transition: { type: 'spring', stiffness: 280, damping: 28 } },
  exit: { x: '100%', opacity: 0, transition: transitions.slow },
} as const;

// ---- Streaming fetch --------------------------------------------------------

async function streamChat(
  messages: { role: string; content: string }[],
  onDelta: (chunk: string) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/v2/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  });

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(text || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6).trim();
      if (payload === '[DONE]') return;
      try {
        const obj = JSON.parse(payload) as { type: string; text?: string };
        if (obj.type === 'delta' && obj.text) onDelta(obj.text);
      } catch {
        // malformed chunk — skip
      }
    }
  }
}

// ---- Client-side stub (used when /api/v2/ai/chat is unreachable) -----------

async function buildStubBrief(): Promise<string> {
  const today = new Date().toLocaleDateString('en-IN', {
    timeZone: 'Asia/Kolkata',
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  let divText = '';
  let cellText = '';
  try {
    divText = await getDivisionOverview(8);
  } catch {
    divText = '(division data unavailable)';
  }
  try {
    cellText = await getCriticalCells();
  } catch {
    cellText = '(cell data unavailable)';
  }

  return (
    `DAILY FIRE BRIEF — ${today} (IST)\n\n` +
    `Model: v17.5 hurdle blend | R@top-5% 23.55%\n\n` +
    `TOP DIVISIONS BY CRITICAL ALERTS:\n${divText}\n\n` +
    `HIGH-PRIORITY CELLS:\n${cellText}\n\n` +
    `Recommended triage: start with divisions marked SILENT-IN-DANGER and ` +
    `cells with Hawkes λ > 0.30 — these represent new-outbreak risk, ` +
    `not contagion from recent fires.\n\n` +
    `[Note: LLM backend offline — showing structured data summary. ` +
    `Start Ollama with \`ollama serve\` for conversational follow-ups.]`
  );
}

// ---- Component --------------------------------------------------------------

export default function AIBriefDrawer({ open, onClose }: AIBriefDrawerProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const slideVariants = useAccessibleVariants(drawerVariants);

  // Scroll to bottom on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Close-button ref so we can focus the always-enabled escape hatch
  // on open. Focusing the textarea (the previous behavior) was a trap:
  // the textarea is `disabled` while streaming, so the first focusable
  // element on open was unusable.
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);

  // Focus close button when drawer opens. After streaming completes
  // (finalizeAssistant), the input field becomes the natural next
  // focus target if the user wants to type a follow-up.
  useEffect(() => {
    if (open) setTimeout(() => closeBtnRef.current?.focus(), 300);
  }, [open]);

  // After initial brief streams in, hand focus to the input so the
  // user can immediately type a follow-up question.
  useEffect(() => {
    if (open && !streaming && messages.length > 0) {
      const t = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [open, streaming, messages.length]);

  // Escape key dismissal
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const appendAssistantDelta = useCallback((chunk: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== 'assistant') {
        return [...prev, { id: newMsgId(), role: 'assistant', content: chunk, streaming: true }];
      }
      return [
        ...prev.slice(0, -1),
        { ...last, content: last.content + chunk, streaming: true },
      ];
    });
  }, []);

  const finalizeAssistant = useCallback(() => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== 'assistant') return prev;
      return [...prev.slice(0, -1), { ...last, streaming: false }];
    });
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;
      const userMsg: ChatMessage = { id: newMsgId(), role: 'user', content: text.trim() };
      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setError(null);
      setStreaming(true);

      const history = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        await streamChat(history, appendAssistantDelta, ctrl.signal);
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          finalizeAssistant();
          setStreaming(false);
          return;
        }
        // Backend unreachable — use client stub only for the initial brief
        if (messages.length === 0) {
          try {
            // Surface the degradation BEFORE the stream starts, so
            // officers (and AT users) know the brief is offline-mode
            // not full Ollama. role=status is read once on mount.
            setMessages((prev) => [
              ...prev,
              {
                id: newMsgId(),
                role: 'system',
                content: 'AI backend offline — showing client-side stub brief.',
              },
            ]);
            const brief = await buildStubBrief();
            // Stream it character by character for the demo feel
            for (const char of brief) {
              if (ctrl.signal.aborted) break;
              appendAssistantDelta(char);
              // eslint-disable-next-line no-await-in-loop
              await new Promise((r) => setTimeout(r, 4));
            }
          } catch (stubErr) {
            setError(`Could not generate brief: ${(stubErr as Error).message}`);
          }
        } else {
          setError(`AI backend unavailable: ${(err as Error).message}. Start Ollama to enable follow-ups.`);
        }
      } finally {
        finalizeAssistant();
        setStreaming(false);
      }
    },
    [streaming, messages, appendAssistantDelta, finalizeAssistant],
  );

  // Auto-fire on open (only once per open session)
  const firedRef = useRef(false);
  useEffect(() => {
    if (!open) {
      firedRef.current = false;
      setMessages([]);
      setError(null);
      abortRef.current?.abort();
      return;
    }
    if (firedRef.current) return;
    firedRef.current = true;
    sendMessage(
      "Give me a structured daily fire brief for today's JwalaNetra v17.5 predictions. " +
      'Include: total alert counts by band, top 5 divisions by CRITICAL count, ' +
      'any silent-in-danger divisions, and your top dispatch recommendation.',
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="brief-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={transitions.base}
            onClick={onClose}
            aria-hidden
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.42)',
              zIndex: 40,
            }}
          />

          {/* Drawer */}
          <motion.aside
            ref={drawerRef}
            key="brief-drawer"
            variants={slideVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            role="dialog"
            // aria-labelledby (not aria-label) so the visually-hidden
            // h2 below is announced AND the body content remains
            // readable. Same pattern as MapFlyout post 51fdab25.
            aria-labelledby="brief-drawer-title"
            // NOT aria-modal — no full focus trap implemented; honest
            // role="dialog" instead. AT users can still navigate
            // background but won't think it's hidden.
            tabIndex={-1}
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              // Responsive width clamp — same MapFlyout pattern. At
              // 360px viewport, drawer fills minus 48px gutter.
              width: 'min(420px, calc(100vw - 48px))',
              minWidth: 280,
              background: 'rgba(15, 23, 42, 0.97)',
              backdropFilter: 'blur(32px) saturate(160%)',
              WebkitBackdropFilter: 'blur(32px) saturate(160%)',
              borderLeft: `1px solid ${colors.border.base}`,
              display: 'flex',
              flexDirection: 'column',
              zIndex: 50,
              boxShadow: shadow[4],
              outline: 'none',
            }}
          >
            {/* Visually-hidden heading — referenced by aria-labelledby */}
            <h2
              id="brief-drawer-title"
              style={{
                position: 'absolute', width: 1, height: 1,
                padding: 0, margin: -1, overflow: 'hidden',
                clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap', border: 0,
              }}
            >
              AI Daily Briefing — chat panel
            </h2>
            {/* Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '14px 16px 12px',
                borderBottom: `1px solid ${colors.border.subtle}`,
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: 32, height: 32, borderRadius: radius.md,
                  background: 'rgba(59,130,246,0.18)',
                  border: `1px solid rgba(59,130,246,0.35)`,
                }}
              >
                <Bot size={16} color={colors.accent.base} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: colors.text.primary }}>
                  AI Brief
                </div>
                <div style={{ fontSize: 11, color: colors.text.tertiary, marginTop: 1 }}>
                  v17.5 · daily triage assistant
                </div>
              </div>
              <motion.button
                ref={closeBtnRef}
                onClick={onClose}
                whileHover={{ backgroundColor: 'rgba(255,255,255,0.07)' }}
                whileTap={{ scale: 0.93 }}
                transition={transitions.fast}
                aria-label="Close AI brief"
                style={{
                  // 44×44 minimum touch target (Apple HIG / WCAG)
                  width: 44, height: 44, borderRadius: radius.sm,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: colors.text.tertiary,
                }}
              >
                <X size={16} />
              </motion.button>
            </div>

            {/* Message list. aria-live='off' DURING streaming so AT
                doesn't fire on every SSE token (would be unusable);
                flips to 'polite' when streaming ends so the final
                message is announced once as a coherent unit. */}
            <div
              role="log"
              aria-live={streaming ? 'off' : 'polite'}
              aria-relevant="additions text"
              aria-label="Chat messages"
              tabIndex={0}
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: '16px 14px',
                display: 'flex',
                flexDirection: 'column',
                gap: 14,
                outline: 'none',
              }}
            >
              {messages.length === 0 && (
                <div
                  style={{
                    margin: 'auto',
                    textAlign: 'center',
                    color: colors.text.disabled,
                    fontSize: 13,
                  }}
                >
                  <Sparkles size={28} style={{ marginBottom: 10, opacity: 0.4 }} />
                  <div>Generating your daily brief…</div>
                </div>
              )}

              {/* System rows render as a compact role=status banner
                  separate from the chat-bubble flow (e.g. stub-fallback
                  notice). */}
              {messages.filter((m) => m.role === 'system').map((sys) => (
                <div
                  key={sys.id}
                  role="status"
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                    padding: '8px 10px',
                    background: colors.coverage.priorWatch.bg,
                    border: `1px solid ${colors.coverage.priorWatch.border}`,
                    borderRadius: radius.sm,
                    fontSize: 11,
                    color: colors.coverage.priorWatch.fg,
                    lineHeight: 1.45,
                  }}
                >
                  <Bot size={12} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
                  <span>{sys.content}</span>
                </div>
              ))}

              {messages.filter((m) => m.role !== 'system').map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div
                    style={{
                      maxWidth: '90%',
                      padding: '10px 13px',
                      borderRadius:
                        msg.role === 'user'
                          ? `${radius.lg} ${radius.lg} ${radius.xs} ${radius.lg}`
                          : `${radius.lg} ${radius.lg} ${radius.lg} ${radius.xs}`,
                      background:
                        msg.role === 'user'
                          ? 'rgba(59,130,246,0.22)'
                          : 'rgba(148,163,184,0.08)',
                      border: `1px solid ${msg.role === 'user' ? 'rgba(59,130,246,0.35)' : colors.border.subtle}`,
                      fontSize: 13,
                      lineHeight: 1.6,
                      color: colors.text.primary,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {msg.content}
                    {msg.streaming && (
                      <motion.span
                        aria-hidden="true"
                        animate={{ opacity: [1, 0, 1] }}
                        transition={{ duration: 0.9, repeat: Infinity }}
                        style={{ marginLeft: 2, color: colors.accent.base }}
                      >
                        ▍
                      </motion.span>
                    )}
                  </div>
                </div>
              ))}

              {error && (
                <div
                  role="alert"
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                    padding: '10px 12px',
                    background: colors.fire.critical.bg,
                    border: `1px solid ${colors.fire.critical.border}`,
                    borderRadius: radius.md,
                    fontSize: 12,
                    color: colors.fire.critical.fg,
                    lineHeight: 1.5,
                  }}
                >
                  <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                  <span>{error}</span>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* PII disclaimer — id allows the textarea to reference
                this via aria-describedby. */}
            <div
              id="brief-pii-note"
              style={{
                padding: '6px 14px',
                fontSize: 10,
                color: colors.text.disabled,
                borderTop: `1px solid ${colors.border.divider}`,
                flexShrink: 0,
              }}
            >
              Do not enter officer names, phone numbers, or personal data.
            </div>

            {/* Input row */}
            <div
              style={{
                padding: '10px 12px 14px',
                flexShrink: 0,
                display: 'flex',
                gap: 8,
                alignItems: 'flex-end',
              }}
            >
              {/* Visually-hidden label — placeholder isn't a label */}
              <label
                htmlFor="brief-input"
                style={{
                  position: 'absolute', width: 1, height: 1,
                  padding: 0, margin: -1, overflow: 'hidden',
                  clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap', border: 0,
                }}
              >
                Ask a follow-up question
              </label>
              <textarea
                id="brief-input"
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a follow-up…"
                rows={2}
                disabled={streaming}
                aria-describedby="brief-pii-note"
                aria-busy={streaming}
                style={{
                  flex: 1,
                  resize: 'none',
                  padding: '9px 12px',
                  background: 'rgba(148,163,184,0.08)',
                  border: `1px solid ${colors.border.base}`,
                  borderRadius: radius.md,
                  color: colors.text.primary,
                  fontSize: 13,
                  lineHeight: 1.5,
                  outline: 'none',
                  fontFamily: 'inherit',
                }}
              />
              <motion.button
                onClick={() => sendMessage(input)}
                disabled={streaming || !input.trim()}
                whileHover={!streaming && input.trim() ? { scale: 1.05 } : undefined}
                whileTap={!streaming && input.trim() ? { scale: 0.93 } : undefined}
                transition={transitions.fast}
                // Dynamic label distinguishes "streaming, wait" from
                // "input is empty, type first" — both are the disabled
                // state but mean different things to AT users.
                aria-label={
                  streaming
                    ? 'Sending — please wait for the assistant to finish'
                    : !input.trim()
                      ? 'Send message — type a question first'
                      : 'Send message'
                }
                aria-busy={streaming}
                style={{
                  // 44×44 minimum touch target (Apple HIG / WCAG)
                  width: 44, height: 44, borderRadius: radius.md,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background:
                    streaming || !input.trim()
                      ? 'rgba(59,130,246,0.12)'
                      : colors.accent.base,
                  color:
                    streaming || !input.trim()
                      ? colors.text.disabled
                      : '#fff',
                  flexShrink: 0,
                  cursor: streaming || !input.trim() ? 'default' : 'pointer',
                  transition: 'background 0.15s',
                }}
              >
                <Send size={16} aria-hidden="true" />
              </motion.button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
