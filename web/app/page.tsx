"use client";
import { motion } from "framer-motion";
import { ArrowRight, BadgeCheck, Boxes, Gauge, Pause, Play, ShieldAlert, Sparkles, Upload, Zap } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LiveStream } from "@/components/events";
import { StaticPipeline } from "@/components/StaticPipeline";
import { Button, Counter, Empty, Glass, InfoTip, item, Pill, Section, SOURCE_STATUS, Stagger, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { runDemo } from "@/lib/demo";
import { compact } from "@/lib/format";
import { useLive } from "@/lib/live";

const PipelineScene = dynamic(() => import("@/components/PipelineScene"), { ssr: false, loading: () => <StaticPipeline /> });

function useLowGfx() {
  const [low, setLow] = useState(false);
  useEffect(() => {
    let l = false;
    try {
      l = localStorage.getItem("ekalog-lowgfx") === "1";
    } catch {}
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) l = true;
    const c = document.createElement("canvas");
    if (!c.getContext("webgl2") && !c.getContext("webgl")) l = true;
    setLow(l);
  }, []);
  const toggle = () => {
    setLow((v) => {
      try { localStorage.setItem("ekalog-lowgfx", v ? "0" : "1"); } catch {}
      return !v;
    });
  };
  return [low, toggle] as const;
}

const STAGES = [
  { k: "INGEST", d: "syslog · files · HTTP · every raw byte vaulted first" },
  { k: "MINE", d: "EkaMiner learns templates (no regex written by anyone)" },
  { k: "LABEL", d: "rules + local AI name fields → OCSF (offline)" },
  { k: "NORMALIZE", d: "one schema, round-trip verified per event" },
];

export default function Overview() {
  const stats = useLive((s) => s.stats);
  const eps = useLive((s) => s.eps);
  const jobs = useLive((s) => s.jobs);
  const [low, toggleLow] = useLowGfx();
  const [demo, setDemo] = useState("");
  const [running, setRunning] = useState(false);

  const foundryActive = Object.values(jobs).some((j) => !["done", "error"].includes(j.stage));
  const mix = useMemo(() => {
    const n = Math.max(1, stats?.events ?? 1);
    return {
      eps: stats?.eps ?? 0,
      bad: Math.min(0.5, (stats?.unmatched ?? 0) / n + (stats?.healing.length ? 0.15 : 0)),
      inj: Math.min(0.3, ((stats?.injection ?? 0) / n) * 20),
      foundry: foundryActive,
    };
  }, [stats, foundryActive]);

  const start = async () => {
    setRunning(true);
    try {
      await runDemo(setDemo);
    } finally {
      setRunning(false);
      setDemo("");
    }
  };
  useEffect(() => {
    const on = () => start();
    window.addEventListener("ekalog:demo", on);
    return () => window.removeEventListener("ekalog:demo", on);
  }, []);

  const sources = Object.values(stats?.sources ?? {});
  const hasData = (stats?.events ?? 0) > 0;
  const loss = stats ? stats.lossless_score * 100 : 100;

  return (
    <div className="flex flex-col gap-6">
      {/* HERO */}
      <Glass className="relative h-[440px] overflow-hidden p-0" hover={false}>
        <div className="absolute inset-0">{low ? <StaticPipeline /> : <PipelineScene mix={mix} />}</div>
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-bg-0 via-bg-0/30 to-transparent" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-bg-0/80 via-transparent to-transparent" />
        <div className="relative flex h-full flex-col justify-between p-6 md:p-8">
          <div className="flex items-start justify-between gap-4">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="max-w-xl">
              <Pill tone="info" pulse>{hasData ? "Pipeline live" : "Ready"}</Pill>
              <h1 className="mt-4 font-display text-4xl font-semibold leading-[1.05] tracking-tight md:text-5xl">
                <span className="text-grad">One schema</span> for every log.
              </h1>
              <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-muted">
                EKALOG learns a parser from a sample file, proves the normalized record loses zero bytes, heals itself
                when a vendor changes the format - and its AI can&apos;t be prompt-injected by the logs it reads. Fully offline.
              </p>
            </motion.div>
            <button onClick={toggleLow} className="pointer-events-auto rounded-lg px-2 py-1 text-[11px] text-faint hover:text-ink">
              {low ? "3D: off" : "3D: on"}
            </button>
          </div>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="hidden gap-2 md:flex">
              {STAGES.map((s, i) => (
                <div key={s.k} className="flex items-center gap-2">
                  <div className="rounded-xl border border-white/10 bg-black/40 px-3 py-2 backdrop-blur-md" title={s.d}>
                    <div className="font-mono text-[10px] tracking-[0.2em] text-cyan">{String(i + 1).padStart(2, "0")} {s.k}</div>
                    <div className="mt-0.5 max-w-[170px] text-[11px] leading-snug text-muted">{s.d}</div>
                  </div>
                  {i < 3 && <ArrowRight className="h-3.5 w-3.5 text-faint" />}
                </div>
              ))}
            </div>
            <div className="pointer-events-auto flex gap-2">
              {hasData ? (
                <Button icon={<Pause className="h-4 w-4" />} onClick={() => api.post("/api/ingest/stop")}>Pause streams</Button>
              ) : null}
              <Button variant="primary" loading={running} icon={<Play className="h-4 w-4" />} onClick={start}>
                {running ? demo || "Starting…" : hasData ? "Stream all samples" : "Run the full demo"}
              </Button>
            </div>
          </div>
        </div>
      </Glass>

      {/* KPI ROW */}
      <Stagger className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <motion.div variants={item}><Stat label="Events / sec" value={stats?.eps ?? 0} icon={<Zap className="h-3.5 w-3.5" />}
          hint="Events normalized per second right now (2-second window). The hot path contains no AI - only compiled templates."
          sub={`end-to-end batch p99 ${stats?.batch_p99_ms ?? 0} ms`} tone="text-cyan" /></motion.div>
        <motion.div variants={item}><Stat label="Normalized" value={stats?.events ?? 0}
          hint="Total events converted to OCSF since start, including replays from quarantine." sub={`${compact(stats?.bytes ?? 0)} characters processed`} /></motion.div>
        <Glass className="p-5" variants={item}>
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted">
            <BadgeCheck className="h-3.5 w-3.5" /> Losslessness
            <InfoTip>Every normalized event is rebuilt byte-for-byte from the normalized record alone and its SHA-256 compared to the hash taken at ingest. This is the share that matched.</InfoTip>
          </div>
          <div className="mt-3 font-display text-3xl font-semibold tracking-tight text-mint">
            <Counter value={loss} decimals={3} suffix="%" />
          </div>
          <div className="mt-1 text-xs text-muted"><span className="num">{compact(stats?.verified ?? 0)}</span> verified · <span className="num">{stats?.verify_failed ?? 0}</span> failed</div>
        </Glass>
        <motion.div variants={item}><Stat label="Active parsers" value={stats?.parsers ?? 0} icon={<Boxes className="h-3.5 w-3.5" />}
          hint="Signed, versioned parser artifacts currently serving traffic. Each was learned from a sample, not hand-written." sub={`${sources.length} sources seen`} /></motion.div>
        <motion.div variants={item}><Stat label="Injections caught" value={stats?.injection ?? 0} icon={<ShieldAlert className="h-3.5 w-3.5" />} tone={(stats?.injection ?? 0) ? "text-rose" : "text-ink"}
          hint="Log lines carrying prompt-injection or log-forgery payloads. They are still normalized losslessly and additionally flagged as a detection." sub="turned into detections" /></motion.div>
      </Stagger>

      {!hasData && !running && (
        <Glass hover={false}>
          <Empty icon={<Sparkles className="h-6 w-6" />} title="Start in under a minute"
            body={<>Three steps: <b className="text-ink">1.</b> drop a sample log, <b className="text-ink">2.</b> EKALOG learns and signs a parser, <b className="text-ink">3.</b> stream it and watch it normalize. Or let the guided demo do all seven vendors for you.</>}
            action={<div className="flex gap-2"><Button href="/onboard" icon={<Upload className="h-4 w-4" />}>Onboard a log</Button>
              <Button variant="primary" icon={<Play className="h-4 w-4" />} onClick={start}>Run the full demo</Button></div>} />
        </Glass>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <Section title="Live OCSF stream" hint="Newest normalized events. Click any row to see the full OCSF record and prove it is lossless."
          right={<span className="text-xs text-muted">click a row to inspect</span>}>
          <div className="max-h-[520px] overflow-auto pr-1"><LiveStream limit={60} /></div>
        </Section>
        <div className="flex flex-col gap-6">
          <Section title="Throughput" hint="Events per second over the last two minutes.">
            <div className="h-40">
              <ResponsiveContainer>
                <AreaChart data={eps.map((p) => ({ t: new Date(p.t).toISOString().slice(14, 19), eps: Math.round(p.eps) }))}>
                  <defs>
                    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.5} />
                      <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="t" hide />
                  <YAxis width={40} tick={{ fill: "#5b6a88", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: "#0a0e1a", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12, fontSize: 12 }} />
                  <Area type="monotone" dataKey="eps" stroke="#22D3EE" strokeWidth={2} fill="url(#g)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Section>
          <Section title="Sources" hint="Every stream EKALOG has seen, with its parser and health. Unknown sources can be onboarded straight from quarantine."
            right={<Link href="/drift" className="text-xs text-cyan hover:underline">Drift Sentinel →</Link>}>
            <div className="grid gap-2 sm:grid-cols-2">
              {sources.map((s) => {
                const st = SOURCE_STATUS[s.status] ?? SOURCE_STATUS.learning;
                return (
                  <div key={s.source} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-sm">{s.source}</span>
                      <Pill tone={st.tone} pulse={s.status === "healing" || s.status === "drifting"}>{st.label}</Pill>
                    </div>
                    <div className="mt-2 flex justify-between text-[11px] text-muted">
                      <span className="truncate">{s.parser ?? "no parser yet"}</span>
                      <span className="num">{compact(s.total)} ev · {(s.fail_rate * 100).toFixed(1)}% unmatched</span>
                    </div>
                  </div>
                );
              })}
              {!sources.length && <div className="col-span-2 py-6 text-center text-sm text-muted">No sources yet.</div>}
            </div>
          </Section>
          <Glass className="flex items-center gap-4 p-5">
            <Gauge className="h-8 w-8 text-violet" />
            <div className="flex-1 text-sm text-muted">
              Want hard numbers? Measured single-core throughput, latency percentiles and projections.
            </div>
            <Button href="/bench" icon={<ArrowRight className="h-4 w-4" />}>Benchmarks</Button>
          </Glass>
        </div>
      </div>
    </div>
  );
}
