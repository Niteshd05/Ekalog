"use client";
import { motion } from "framer-motion";
import { Check, GitCompareArrows, HeartPulse, History, Loader2, Radar, RotateCcw, ShieldCheck, Siren, Zap } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, Empty, Glass, PageHeader, Pill, Section, SOURCE_STATUS } from "@/components/ui";
import { api, ParserSummary, waitJob } from "@/lib/api";
import { cls } from "@/lib/format";
import { toast, useLive } from "@/lib/live";

type DriftSource = { source: string; status: string; parser: string | null; total: number; failed: number; fail_rate: number;
  timeline: [number, number, number, string][] };

async function ensureFortigate(onStep: (s: string) => void) {
  const parsers = await api.get<ParserSummary[]>("/api/parsers");
  if (!parsers.some((p) => p.sources.includes("fortigate"))) {
    onStep("Learning the FortiOS 6 parser first…");
    const fd = new FormData();
    fd.append("sample", "samples/fortigate.log");
    fd.append("source", "fortigate");
    const { job_id } = await api.form<{ job_id: string }>("/api/sources/onboard", fd);
    await waitJob(job_id);
  }
  const replays = await api.get<any[]>("/api/ingest/replays");
  if (!replays.some((r) => r.running && r.source === "fortigate")) {
    onStep("Streaming normal FortiGate traffic…");
    await api.post("/api/ingest/replay", { sample: "samples/fortigate.log", source: "fortigate", eps: 250, loop: true });
    await new Promise((r) => setTimeout(r, 2500));
  }
}

const STEPS = [
  { k: "detected", label: "Drift detected", icon: Siren, d: "Unmatched-line rate crossed 5% on a rolling window" },
  { k: "healing", label: "Quarantined", icon: ShieldCheck, d: "Unparsed lines held, never dropped" },
  { k: "relearn", label: "Re-learning", icon: Radar, d: "Foundry mines only the new shapes" },
  { k: "healed", label: "Hot-swapped", icon: Zap, d: "New signed version, no restart" },
  { k: "replayed", label: "Queue replayed", icon: RotateCcw, d: "Quarantine drained into the new parser" },
];

function DriftInner() {
  const params = useSearchParams();
  const [data, setData] = useState<{ sources: DriftSource[]; alarms: any[]; heal_jobs: any[] } | null>(null);
  const [sel, setSel] = useState<string>("fortigate");
  const [busy, setBusy] = useState("");
  const [parser, setParser] = useState<any>(null);
  const drift = useLive((s) => s.drift);
  const jobs = useLive((s) => s.jobs);
  const quarantine = useLive((s) => s.stats?.sources?.[sel]);
  const autoRan = useRef(false);

  useEffect(() => {
    const load = () => api.get<any>("/api/drift").then(setData).catch(() => {});
    load();
    const t = setInterval(load, 1000);
    return () => clearInterval(t);
  }, []);
  const src = data?.sources.find((s) => s.source === sel) ?? data?.sources[0];
  useEffect(() => {
    if (!src && data?.sources.length) setSel(data.sources[0].source);
  }, [data, src]);
  const pid = src?.parser;
  const lastHeal = [...drift].reverse().find((d) => d.source === src?.source && d.state === "healed");
  useEffect(() => {
    if (pid) api.get<any>(`/api/parsers/${pid}`).then(setParser).catch(() => {});
  }, [pid, lastHeal?.version]);

  const simulate = async () => {
    try {
      await ensureFortigate(setBusy);
      setSel("fortigate");
      setBusy("Streaming FortiOS 7.x logs (new fields + reordered)…");
      await api.post("/api/drift/simulate?source=fortigate&eps=400");
      toast({ tone: "info", title: "Firmware upgrade simulated", body: "FortiOS 7 adds poluuid & srccountry and moves service before proto." });
    } finally {
      setTimeout(() => setBusy(""), 1500);
    }
  };
  useEffect(() => {
    if (params.get("simulate") && !autoRan.current) {
      autoRan.current = true;
      simulate();
    }
  }, [params]);

  // derive stepper state from the latest episode for this source
  const episode = useMemo(() => {
    const evs = drift.filter((d) => d.source === src?.source);
    const startIdx = evs.map((d) => d.state).lastIndexOf("detected");
    return startIdx >= 0 ? evs.slice(startIdx) : [];
  }, [drift, src?.source]);
  const has = (k: string) => episode.some((e) => e.state === k);
  const healed = episode.find((e) => e.state === "healed");
  const healingMsg = episode.find((e) => e.state === "healing");
  const healJob = Object.entries(jobs).reverse().find(([, j]) => j.kind === "heal" && j.source === src?.source);
  const stepDone = (k: string) =>
    k === "detected" ? has("detected") : k === "healing" ? has("healing") : k === "relearn" ? !!healed || healJob?.[1].stage === "done" :
      k === "healed" ? !!healed : k === "replayed" ? !!healed && (healed.replayed ?? 0) >= 0 : false;
  const activeIdx = STEPS.findIndex((s) => !stepDone(s.k));
  const failed = episode.some((e) => e.state === "failed");

  const chart = (src?.timeline ?? []).slice(-120).map(([t, total, fail]) => ({
    t: new Date(t * 1000).toISOString().slice(14, 19), ok: total - fail, fail,
  }));

  return (
    <div>
      <PageHeader eyebrow="Drift Sentinel" title={<>Parsers that <span className="text-grad">heal themselves</span></>}
        subtitle="A firmware upgrade quietly changes the log format and every other pipeline starts dropping fields for weeks. EKALOG notices within seconds, quarantines what it can't parse (nothing is dropped), re-learns only the new shapes, hot-swaps a new signed version and replays the queue."
        actions={<Button variant="primary" loading={!!busy} onClick={simulate} icon={<HeartPulse className="h-4 w-4" />}>
          {busy || "Simulate FortiOS 7 upgrade"}</Button>} />

      {!data?.sources.length ? (
        <Glass hover={false}><Empty icon={<HeartPulse className="h-6 w-6" />} title="No sources streaming yet"
          body="Press “Simulate FortiOS 7 upgrade”: EKALOG will learn the FortiGate parser, stream normal traffic, then switch the device to the new firmware format." /></Glass>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap gap-2">
            {data.sources.map((s) => {
              const st = SOURCE_STATUS[s.status] ?? SOURCE_STATUS.learning;
              return (
                <button key={s.source} onClick={() => setSel(s.source)}
                  className={cls("glass flex items-center gap-3 rounded-2xl px-4 py-2.5 text-left transition", s.source === src?.source ? "border-cyan/50" : "opacity-80 hover:opacity-100")}>
                  <span className="font-mono text-sm">{s.source}</span>
                  <Pill tone={st.tone} pulse={s.status === "drifting" || s.status === "healing"}>{st.label}</Pill>
                </button>
              );
            })}
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <Section title={`Parse health · ${src?.source ?? ""}`} hint="Events per second that matched the active parser (cyan) vs lines that did not (amber). An amber spike is a format change."
              right={<span className="text-xs text-muted">unmatched now <b className={cls("num", (src?.fail_rate ?? 0) > 0.05 ? "text-amber" : "text-ink")}>{((src?.fail_rate ?? 0) * 100).toFixed(1)}%</b></span>}>
              <div className="h-64">
                <ResponsiveContainer>
                  <AreaChart data={chart}>
                    <CartesianGrid stroke="rgba(255,255,255,.04)" vertical={false} />
                    <XAxis dataKey="t" tick={{ fill: "#5b6a88", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
                    <YAxis width={40} tick={{ fill: "#5b6a88", fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: "#0a0e1a", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12, fontSize: 12 }} />
                    <Area type="monotone" dataKey="ok" name="parsed/s" stackId="1" stroke="#22D3EE" fill="#22D3EE33" isAnimationActive={false} />
                    <Area type="monotone" dataKey="fail" name="unmatched/s" stackId="1" stroke="#FBBF24" fill="#FBBF2455" isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
                <span>total <b className="num text-ink">{(src?.total ?? 0).toLocaleString()}</b></span>
                <span>unmatched ever <b className="num text-ink">{(src?.failed ?? 0).toLocaleString()}</b></span>
                <span>parser <b className="font-mono text-ink">{src?.parser ?? "-"}</b></span>
                {quarantine && <span>status <b className="text-ink">{SOURCE_STATUS[quarantine.status]?.label}</b></span>}
              </div>
            </Section>

            <Section title="Self-healing run" hint="Driven live by the engine. Each step is a real event from the pipeline, not an animation script.">
              {!episode.length ? (
                <div className="py-8 text-center text-sm text-muted">No drift episode yet for this source.</div>
              ) : (
                <div className="flex flex-col gap-3">
                  {STEPS.map((s, i) => {
                    const done = stepDone(s.k);
                    const active = !failed && i === activeIdx;
                    const I = s.icon;
                    return (
                      <motion.div key={s.k} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                        className={cls("flex items-center gap-3 rounded-2xl border p-3", done ? "border-mint/25 bg-mint/[0.05]" : active ? "border-cyan/40 bg-cyan/[0.06]" : "border-white/5 opacity-50")}>
                        <div className={cls("grid h-8 w-8 place-items-center rounded-xl", done ? "bg-mint/15 text-mint" : active ? "bg-cyan/15 text-cyan" : "bg-white/5 text-faint")}>
                          {done ? <Check className="h-4 w-4" /> : active ? <Loader2 className="h-4 w-4 animate-spin" /> : <I className="h-4 w-4" />}
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium">{s.label}</div>
                          <div className="text-[11px] text-muted">
                            {s.k === "detected" && episode[0] ? `${(episode[0].fail_rate * 100).toFixed(1)}% unmatched · ${episode[0].novel_shapes} new line shape(s)` :
                              s.k === "healing" && healingMsg ? `${healingMsg.quarantined} lines in quarantine` :
                                s.k === "healed" && healed ? `v${healed.from} → v${healed.version} in ${healed.seconds}s` :
                                  s.k === "replayed" && healed ? `${healed.replayed} events replayed, 0 lost` : s.d}
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                  {episode.some((e) => e.state === "cleared") && (
                    <div className="rounded-xl border border-cyan/30 bg-cyan/10 p-3 text-sm text-cyan">False alarm cleared: the held lines matched the current parser after all and were replayed. No new version was needed.</div>
                  )}
                  {failed && <div className="rounded-xl border border-rose/30 bg-rose/10 p-3 text-sm text-rose">The new version failed a validation gate, so it was NOT activated. Lines stay in quarantine for review.</div>}
                  {healJob && !healed && healJob[1].tokens && (
                    <pre className="mono-block h-24 text-[10.5px] text-violet/90">{healJob[1].tokens.slice(-800)}</pre>
                  )}
                </div>
              )}
            </Section>
          </div>

          {healed && healed.diff?.length > 0 && (
            <Section className="mt-6" title={`What changed in the firmware · v${healed.from} → v${healed.version}`}
              hint="For each new message shape, the closest old template is found and field names are compared.">
              <div className="grid gap-4 lg:grid-cols-2">
                {healed.diff.map((d: any) => (
                  <div key={d.template} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="mb-3 flex items-center gap-2 text-xs text-muted"><GitCompareArrows className="h-4 w-4 text-cyan" />
                      template <span className="font-mono text-ink">{d.template}</span> · {(d.similarity * 100).toFixed(0)}% similar to {d.based_on}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {d.added.map((f: string) => <span key={f} className="chip border-mint/40 bg-mint/10 text-mint">+ {f}</span>)}
                      {d.removed.map((f: string) => <span key={f} className="chip border-rose/40 bg-rose/10 text-rose">− {f}</span>)}
                      {d.reordered.slice(0, 6).map((f: string) => <span key={f} className="chip border-amber/40 bg-amber/10 text-amber">↕ {f}</span>)}
                      {!d.added.length && !d.removed.length && !d.reordered.length && <span className="text-xs text-muted">same fields, new layout</span>}
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {parser && (
            <Section className="mt-6" title={`Version history · ${parser.id}`} hint="Every version is immutable and signed. Old events still reference (and can be rebuilt with) the version that parsed them. Roll back with one click.">
              <div className="flex flex-col gap-2">
                {[...parser.versions].reverse().map((v: any) => (
                  <div key={v.version} className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                    <History className="h-4 w-4 text-muted" />
                    <span className="font-display font-semibold">v{v.version}</span>
                    <Pill tone={v.status === "active" ? "ok" : v.status === "pending_review" ? "warn" : "muted"}>{v.status.replace("_", " ")}</Pill>
                    <span className="font-mono text-[11px] text-faint">sha256:{v.sha256.slice(0, 16)}…</span>
                    <span className="text-xs text-muted">{new Date(v.created * 1000).toLocaleTimeString()}</span>
                    {v.status !== "active" && (
                      <Button className="ml-auto" variant="subtle" icon={<RotateCcw className="h-3.5 w-3.5" />}
                        onClick={async () => { await api.post(`/api/parsers/${parser.id}/activate`, { version: v.version }); toast({ tone: "info", title: `Activated v${v.version}` }); setParser(await api.get(`/api/parsers/${parser.id}`)); }}>
                        Activate
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}
        </>
      )}
    </div>
  );
}

export default function Drift() {
  return <Suspense><DriftInner /></Suspense>;
}
