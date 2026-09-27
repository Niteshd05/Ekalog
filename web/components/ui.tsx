"use client";
import { motion } from "framer-motion";
import { Info, Loader2 } from "lucide-react";
import Link from "next/link";
import { ReactNode, useEffect, useRef, useState } from "react";
import { cls, nf } from "@/lib/format";

export const spring = { type: "spring" as const, stiffness: 260, damping: 30 };

export function Glass({ children, className, hover = true, as = "div", ...rest }: {
  children: ReactNode; className?: string; hover?: boolean; as?: "div" | "section"; [k: string]: any;
}) {
  const C = as === "section" ? motion.section : motion.div;
  return (
    <C className={cls("glass", hover && "specular", className)} {...rest}>
      {children}
    </C>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }: {
  eyebrow: string; title: ReactNode; subtitle: ReactNode; actions?: ReactNode;
}) {
  return (
    <motion.header initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}
      className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-cyan">{eyebrow}</div>
        <h1 className="font-display text-3xl font-semibold tracking-tight md:text-4xl">{title}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">{subtitle}</p>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </motion.header>
  );
}

type BtnProps = {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "ghost" | "danger" | "subtle";
  loading?: boolean; disabled?: boolean; icon?: ReactNode; href?: string; className?: string; title?: string;
  type?: "button" | "submit";
};
export function Button({ children, onClick, variant = "ghost", loading, disabled, icon, href, className, title, type = "button" }: BtnProps) {
  const base = "relative inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-medium transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/50";
  const styles = {
    primary: "text-bg-0 bg-gradient-to-r from-cyan to-[#67e8f9] shadow-[0_8px_30px_rgba(34,211,238,0.35)] hover:shadow-[0_8px_40px_rgba(34,211,238,0.55)] overflow-hidden",
    ghost: "border border-white/10 bg-white/[0.04] text-ink hover:bg-white/[0.08] hover:border-white/20",
    subtle: "text-muted hover:text-ink hover:bg-white/[0.05]",
    danger: "border border-rose/30 bg-rose/10 text-rose hover:bg-rose/20",
  }[variant];
  const inner = (
    <>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      <span>{children}</span>
      {variant === "primary" && !disabled && (
        <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent transition-transform duration-700 hover:translate-x-full" />
      )}
    </>
  );
  if (href) return <Link href={href} className={cls(base, styles, className)} title={title}>{inner}</Link>;
  return (
    <button type={type} onClick={onClick} disabled={disabled || loading} className={cls(base, styles, className)} title={title}>
      {inner}
    </button>
  );
}

/** Animated number that eases to its new value (never snaps). */
export function Counter({ value, decimals = 0, className, suffix }: { value: number; decimals?: number; className?: string; suffix?: string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    const b = value;
    if (a === b) return;
    // rAF is paused in hidden/background tabs: never let the displayed number freeze on a stale value
    setTimeout(() => {
      from.current = b;
      setShown(b);
    }, 700);
    if (typeof document !== "undefined" && document.hidden) return; // settle is intentionally not cleared
    let raf = 0;
    const tick = (now: number) => {
      // rAF timestamps can precede `start`; clamp or the ease overshoots wildly (negative counters)
      const t = Math.max(0, Math.min(1, (now - start) / 600));
      const e = 1 - Math.pow(1 - t, 3);
      const v = a + (b - a) * e;
      setShown(v);
      from.current = v;
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf); // settle survives: timeouts fire in order, newest value lands last
  }, [value]);
  const txt = decimals ? shown.toFixed(decimals) : nf.format(Math.round(shown));
  return <span className={cls("num", className)}>{txt}{suffix}</span>;
}

export function InfoTip({ children, className }: { children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className={cls("relative inline-flex", className)} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
      <button type="button" aria-label="Explain" className="text-faint transition hover:text-cyan">
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && (
        <motion.span initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
          className="glass absolute left-1/2 top-6 z-50 w-72 -translate-x-1/2 rounded-2xl p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-ink/90">
          {children}
        </motion.span>
      )}
    </span>
  );
}

export function Stat({ label, value, decimals, suffix, hint, tone = "text-ink", sub, icon }: {
  label: string; value: number; decimals?: number; suffix?: string; hint: ReactNode; tone?: string; sub?: ReactNode; icon?: ReactNode;
}) {
  return (
    <Glass className="p-5">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted">
        {icon}
        {label}
        <InfoTip>{hint}</InfoTip>
      </div>
      <div className={cls("mt-3 font-display text-3xl font-semibold tracking-tight", tone)}>
        <Counter value={value} decimals={decimals} suffix={suffix} />
      </div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </Glass>
  );
}

const TONES = {
  ok: "text-mint bg-mint/10 border-mint/25",
  warn: "text-amber bg-amber/10 border-amber/25",
  danger: "text-rose bg-rose/10 border-rose/25",
  info: "text-cyan bg-cyan/10 border-cyan/25",
  violet: "text-violet bg-violet/10 border-violet/25",
  muted: "text-muted bg-white/5 border-white/10",
};
export type Tone = keyof typeof TONES;

export function Pill({ tone = "muted", children, pulse, className }: { tone?: Tone; children: ReactNode; pulse?: boolean; className?: string }) {
  return (
    <span className={cls("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", TONES[tone], className)}>
      <span className={cls("h-1.5 w-1.5 rounded-full bg-current", pulse && "animate-pulse")} />
      {children}
    </span>
  );
}

export const SOURCE_STATUS: Record<string, { tone: Tone; label: string }> = {
  learning: { tone: "info", label: "Warming up" },
  stable: { tone: "ok", label: "Healthy" },
  drifting: { tone: "warn", label: "Format drift" },
  healing: { tone: "violet", label: "Self-healing" },
  healed: { tone: "ok", label: "Healed" },
  unknown: { tone: "danger", label: "Unknown source" },
};

export function LabeledBy({ by }: { by: string }) {
  const m: Record<string, [Tone, string, string]> = {
    "rule-key": ["info", "Key", "Named by the device itself (key=value / JSON key)"],
    "rule-schema": ["info", "Schema", "From the file header or the vendor's documented column layout"],
    "rule-pos": ["info", "Header", "Standard syslog/CEF header position"],
    "rule-iface": ["info", "Context", "Interface & direction words (inside/outside, inbound/outbound)"],
    "rule-ctx": ["muted", "Context", "Nearby words like src/dst/from/to"],
    "rule-order": ["muted", "Order", "Weak fallback: first IP = source"],
    llm: ["violet", "Local AI", "Labeled by the local model, then type-checked"],
    none: ["muted", "Kept", "Not mapped - preserved under 'unmapped'"],
  };
  const [tone, label, tip] = m[by] ?? m.none;
  return <span title={tip}><Pill tone={tone}>{label}</Pill></span>;
}

export function Empty({ icon, title, body, action }: { icon: ReactNode; title: string; body: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl border border-white/10 bg-white/5 text-cyan">{icon}</div>
      <div className="font-display text-lg font-semibold">{title}</div>
      <div className="max-w-md text-sm text-muted">{body}</div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Section({ title, hint, right, children, className }: {
  title: string; hint?: ReactNode; right?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <Glass className={cls("p-5", className)} hover={false}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-display text-base font-semibold">
          {title}
          {hint && <InfoTip>{hint}</InfoTip>}
        </div>
        {right}
      </div>
      {children}
    </Glass>
  );
}

export function Stagger({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div className={className} initial="hidden" animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.04 } } }}>
      {children}
    </motion.div>
  );
}
export const item = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: spring } };
