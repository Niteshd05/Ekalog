"use client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity, Bot, Boxes, CircleAlert, CircleCheck, Command, FileSearch, Gauge, HeartPulse, Info, Layers,
  Search, ShieldAlert, Sparkles, Upload, Wifi, WifiOff, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { api, Health } from "@/lib/api";
import { cls } from "@/lib/format";
import { connectLive, dismissToast, useLive } from "@/lib/live";
import { Pill, spring } from "./ui";

export const NAV = [
  { href: "/", label: "Overview", sub: "Live pipeline", icon: Activity },
  { href: "/onboard", label: "Onboard", sub: "Add a log source", icon: Upload },
  { href: "/vault", label: "Lossless Vault", sub: "Prove nothing was lost", icon: FileSearch },
  { href: "/drift", label: "Drift Sentinel", sub: "Self-healing parsers", icon: HeartPulse },
  { href: "/guard", label: "Injection Guard", sub: "AI-safe log handling", icon: ShieldAlert },
  { href: "/ask", label: "Ask EKALOG", sub: "Search in plain English", icon: Search },
  { href: "/parsers", label: "Parsers", sub: "Registry, schema & exports", icon: Boxes },
  { href: "/bench", label: "Benchmarks", sub: "Measured performance", icon: Gauge },
];

function Aurora() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#0d1530_0%,#05070d_60%)]" />
      <div className="absolute -left-1/4 -top-1/3 h-[80vh] w-[80vw] rounded-full opacity-40 blur-[80px] [animation:aurora_30s_ease-in-out_infinite]"
        style={{ background: "radial-gradient(closest-side, rgba(34,211,238,.35), transparent)" }} />
      <div className="absolute -right-1/4 top-1/4 h-[70vh] w-[70vw] rounded-full opacity-40 blur-[80px] [animation:aurora_36s_ease-in-out_infinite_reverse]"
        style={{ background: "radial-gradient(closest-side, rgba(139,92,246,.35), transparent)" }} />
      <div className="absolute -bottom-1/3 left-1/4 h-[60vh] w-[60vw] rounded-full opacity-30 blur-[80px] [animation:aurora_42s_ease-in-out_infinite]"
        style={{ background: "radial-gradient(closest-side, rgba(52,211,153,.28), transparent)" }} />
      {/* 4% grain kills gradient banding */}
      <svg className="absolute inset-0 h-full w-full opacity-[0.04]">
        <filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch" /></filter>
        <rect width="100%" height="100%" filter="url(#n)" />
      </svg>
    </div>
  );
}

function Sidebar() {
  const path = usePathname();
  const stats = useLive((s) => s.stats);
  const drifting = stats ? Object.values(stats.sources).some((s) => s.status === "drifting" || s.status === "healing") : false;
  const injections = stats?.injection ?? 0;
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-1 p-4 lg:flex">
      <Link href="/" className="mb-6 flex items-center gap-3 px-2 pt-2">
        <div className="relative grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-cyan to-violet font-display text-lg font-bold text-bg-0 shadow-[0_0_30px_rgba(34,211,238,0.4)]">
          ए
        </div>
        <div>
          <div className="font-display text-lg font-bold tracking-tight">EKALOG</div>
          <div className="text-[11px] text-muted">One schema for every log</div>
        </div>
      </Link>
      <nav className="flex flex-col gap-1">
        {NAV.map((n) => {
          const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
          const Icon = n.icon;
          const badge = n.href === "/drift" && drifting ? "warn" : n.href === "/guard" && injections ? "danger" : null;
          return (
            <Link key={n.href} href={n.href}
              className={cls("group relative flex items-center gap-3 rounded-2xl px-3 py-2.5 transition",
                active ? "text-ink" : "text-muted hover:bg-white/[0.04] hover:text-ink")}>
              {active && (
                <motion.span layoutId="nav-active" transition={spring}
                  className="absolute inset-0 rounded-2xl border border-white/10 bg-white/[0.07] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]" />
              )}
              <Icon className={cls("relative h-4.5 w-4.5", active && "text-cyan")} />
              <span className="relative flex flex-col leading-tight">
                <span className="text-sm font-medium">{n.label}</span>
                <span className="text-[11px] text-faint group-hover:text-muted">{n.sub}</span>
              </span>
              {badge && <span className={cls("relative ml-auto h-2 w-2 rounded-full animate-pulse", badge === "warn" ? "bg-amber" : "bg-rose")} />}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-[11px] leading-relaxed text-muted">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-ink"><Sparkles className="h-3.5 w-3.5 text-violet" /> SIH 2026 · SIH26156</div>
        NTRO · Universal Log Pre-processing Framework. Team CODERS+1.
      </div>
    </aside>
  );
}

function StatusBar() {
  const connected = useLive((s) => s.connected);
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    const load = () => api.get<Health>("/api/health").then(setHealth).catch(() => setHealth(null));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);
  const llm = health?.llm;
  const eg = health?.egress;
  return (
    <div className="sticky top-0 z-30 -mx-4 mb-6 flex flex-wrap items-center gap-2 border-b border-white/5 bg-bg-0/60 px-4 py-3 backdrop-blur-xl md:-mx-8 md:px-8">
      <div className="mr-auto flex items-center gap-2 lg:hidden">
        <span className="font-display font-bold">EKALOG</span>
      </div>
      <span title="Live connection to the EKALOG engine">
        <Pill tone={connected ? "ok" : "danger"} pulse={connected}>
          {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          {connected ? "Live" : "Reconnecting"}
        </Pill>
      </span>
      <span title={llm?.up ? `Local model via Ollama at ${llm.url}. Cloud models blocked: ${(llm.blocked_cloud_models || []).join(", ") || "none"}` : "Ollama not reachable: EKALOG keeps working with deterministic labeling"}>
        <Pill tone={llm?.up && llm.model ? "violet" : "warn"}>
          <Bot className="h-3 w-3" /> {llm?.up && llm.model ? `Local AI · ${llm.model.split(":")[0]}` : "AI offline · rules only"}
        </Pill>
      </span>
      <span title={eg ? (eg.air_gapped ? "No public endpoint reachable from this host" : `Egress reachable: ${eg.reachable.join(", ")}. EKALOG itself makes no outbound calls.`) : ""}>
        <Pill tone={eg?.air_gapped ? "ok" : "info"}>
          {eg?.air_gapped ? <CircleCheck className="h-3 w-3" /> : <Info className="h-3 w-3" />}
          {eg ? (eg.air_gapped ? "AIR-GAPPED ✓" : "Internet detected · EKALOG uses none") : "Network check…"}
        </Pill>
      </span>
      <button onClick={() => window.dispatchEvent(new Event("ekalog:palette"))}
        className="ml-auto hidden items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-muted transition hover:text-ink md:flex">
        <Command className="h-3.5 w-3.5" /> Jump anywhere <span className="kbd">Ctrl K</span>
      </button>
    </div>
  );
}

function Toaster() {
  const toasts = useLive((s) => s.toasts);
  const router = useRouter();
  const icon = { ok: CircleCheck, warn: CircleAlert, danger: ShieldAlert, info: Info };
  const color = { ok: "text-mint", warn: "text-amber", danger: "text-rose", info: "text-cyan" };
  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-[min(380px,calc(100vw-2.5rem))] flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => {
          const I = icon[t.tone];
          return (
            <motion.div key={t.id} layout initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40 }} transition={spring}
              className="glass pointer-events-auto flex cursor-pointer gap-3 rounded-2xl !bg-bg-1/95 p-4"
              onClick={() => t.href && router.push(t.href)}>
              <I className={cls("mt-0.5 h-5 w-5 shrink-0", color[t.tone])} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{t.title}</div>
                {t.body && <div className="mt-0.5 text-xs leading-relaxed text-muted">{t.body}</div>}
              </div>
              <button onClick={(e) => { e.stopPropagation(); dismissToast(t.id); }} className="text-faint hover:text-ink" aria-label="Dismiss">
                <X className="h-4 w-4" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

type Cmd = { label: string; hint: string; run: () => void; icon: any };

function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const router = useRouter();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("ekalog:palette", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("ekalog:palette", onOpen);
    };
  }, []);
  const cmds: Cmd[] = useMemo(() => [
    ...NAV.map((n) => ({ label: `Go to ${n.label}`, hint: n.sub, icon: n.icon, run: () => router.push(n.href) })),
    { label: "Run the full demo", hint: "Onboard all 7 sample vendors and stream them", icon: Sparkles, run: () => { router.push("/"); setTimeout(() => window.dispatchEvent(new Event("ekalog:demo")), 300); } },
    { label: "Simulate firmware upgrade", hint: "FortiOS 7 changes the log format", icon: HeartPulse, run: () => router.push("/drift?simulate=1") },
    { label: "Stream the attack file", hint: "Prompt-injection payloads inside FortiGate logs", icon: ShieldAlert, run: () => router.push("/guard?stream=1") },
    { label: "Stop all streams", hint: "Pause every replay", icon: Layers, run: () => api.post("/api/ingest/stop") },
  ], [router]);
  const list = cmds.filter((c) => (c.label + c.hint).toLowerCase().includes(q.toLowerCase()));
  useEffect(() => setSel(0), [q, open]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/50 p-4 pt-[15vh] backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)}>
          <motion.div className="glass w-full max-w-xl overflow-hidden" initial={{ y: -10, scale: 0.98 }} animate={{ y: 0, scale: 1 }}
            exit={{ y: -10, scale: 0.98 }} transition={spring} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
              <Search className="h-4 w-4 text-muted" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a page or an action…"
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint"
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, list.length - 1)); }
                  if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
                  if (e.key === "Enter" && list[sel]) { list[sel].run(); setOpen(false); }
                }} />
              <span className="kbd">Esc</span>
            </div>
            <div className="max-h-80 overflow-auto p-2">
              {list.map((c, i) => {
                const I = c.icon;
                return (
                  <button key={c.label} onMouseEnter={() => setSel(i)} onClick={() => { c.run(); setOpen(false); }}
                    className={cls("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left", i === sel ? "bg-white/[0.08]" : "")}>
                    <I className="h-4 w-4 text-cyan" />
                    <span className="text-sm">{c.label}</span>
                    <span className="ml-auto text-xs text-faint">{c.hint}</span>
                  </button>
                );
              })}
              {!list.length && <div className="px-3 py-6 text-center text-sm text-muted">No match</div>}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  useEffect(() => connectLive(), []);
  return (
    <>
      <Aurora />
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="min-w-0 flex-1 px-4 pb-16 md:px-8">
          <StatusBar />
          {/* enter-only transition: App Router swaps children before an exit animation could run */}
          <motion.div key={path} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
            {children}
          </motion.div>
        </main>
      </div>
      <MobileNav />
      <Toaster />
      <CommandPalette />
    </>
  );
}

function MobileNav() {
  const path = usePathname();
  return (
    <nav className="glass fixed inset-x-3 bottom-3 z-40 flex justify-around rounded-2xl p-1.5 lg:hidden">
      {NAV.slice(0, 6).map((n) => {
        const I = n.icon;
        const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} className={cls("rounded-xl p-2.5", active ? "bg-white/10 text-cyan" : "text-muted")} aria-label={n.label}>
            <I className="h-5 w-5" />
          </Link>
        );
      })}
    </nav>
  );
}
