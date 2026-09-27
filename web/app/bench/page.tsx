"use client";
import { Check, Gauge, Minus, Play, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, Empty, Glass, PageHeader, Pill, Section, Stat } from "@/components/ui";
import { api, ParserSummary } from "@/lib/api";
import { compact } from "@/lib/format";

type Cell = [0 | 1 | 2, string]; // 0 no, 1 partial, 2 yes
const MATRIX: { cap: string; cols: Cell[] }[] = [
  { cap: "How a new parser is created", cols: [[0, "Hand-written Grok"], [1, "LLM generates an integration"], [0, "Human-built packs"], [2, "Learned from a sample; rules + local AI only name fields"]] },
  { cap: "AI usable fully offline", cols: [[0, "No AI"], [1, "Possible via a self-hosted OpenAI-compatible endpoint"], [0, "-"], [2, "Ollama only; non-local endpoints & cloud models refused"]] },
  { cap: "Target schema", cols: [[1, "ECS"], [1, "ECS, Elastic stack"], [1, "User-defined"], [2, "OCSF-first + Grok/VRL export"]] },
  { cap: "Proof that normalization lost nothing", cols: [[0, "No"], [0, "No round-trip guarantee"], [0, "No (reduction is a feature)"], [2, "Per-event byte-exact rebuild, SHA-256 verified"]] },
  { cap: "Vendor format drift", cols: [[0, "Silent failures until fixed"], [1, "Re-run generation manually"], [1, "Manual pack updates"], [2, "Detect → quarantine → re-learn → hot-swap → replay"]] },
  { cap: "Prompt injection via log content", cols: [[1, "N/A (no AI)"], [0, "LLM reads raw sample text"], [1, "N/A"], [2, "Model sees typed tags only; payloads become detections"]] },
  { cap: "Parser artifact", cols: [[1, "Config file"], [1, "Integration package"], [1, "Pack"], [2, "Signed, versioned, test-carrying .ekapack"]] },
];
const COLS = ["Logstash (Grok)", "Elastic Automatic Import", "Cribl Stream", "EKALOG"];

function Mark({ c }: { c: Cell }) {
  const I = c[0] === 2 ? Check : c[0] === 1 ? Minus : X;
  const tone = c[0] === 2 ? "text-mint" : c[0] === 1 ? "text-amber" : "text-rose";
  return (
    <div className="flex items-start gap-2">
      <I className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
      <span className="text-xs leading-snug text-muted">{c[1]}</span>
    </div>
  );
}

export default function Bench() {
  const [b, setB] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [parsers, setParsers] = useState<ParserSummary[]>([]);
  useEffect(() => {
    api.get<ParserSummary[]>("/api/parsers").then(setParsers).catch(() => {});
  }, []);
  const run = async () => {
    setBusy(true);
    try {
      setB(await api.get("/api/bench"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader eyebrow="Benchmarks" title={<>Measured, <span className="text-grad">not claimed</span></>}
        subtitle="Numbers below are measured live on this machine: parse + OCSF mapping + full round-trip verification per event, single core, no I/O. Projections are labelled as projections."
        actions={<Button variant="primary" loading={busy} onClick={run} icon={<Play className="h-4 w-4" />}>Run benchmark</Button>} />

      {!b ? (
        <Glass hover={false}><Empty icon={<Gauge className="h-6 w-6" />} title="Run the benchmark"
          body="Uses the sample files and whatever parsers are active. Onboard the samples first (or run the demo) for full coverage." /></Glass>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Stat label="Single-core throughput" value={b.single_core_eps} suffix=" ev/s" tone="text-cyan"
              hint="Measured over all sample files in-process with verification on every event." />
            <Stat label="p50 latency" value={b.p50_us} decimals={1} suffix=" µs" hint="Median time to parse, map and verify one event." />
            <Stat label="p99 latency" value={b.p99_us} decimals={1} suffix=" µs" hint="99th percentile per-event time." />
            <Glass className="p-5">
              <div className="text-xs font-medium uppercase tracking-wider text-muted">Projected / day</div>
              <div className="mt-3 font-display text-3xl font-semibold">{compact(b.projected_per_day_all_cores)}</div>
              <div className="mt-1 text-xs text-muted">{compact(b.projected_per_day_single_core)} on 1 core × {b.cpu_cores} logical cores, linear <Pill tone="warn" className="ml-1">projection</Pill></div>
            </Glass>
          </div>
          <Section className="mt-6" title="Per source (events/sec, single core)" hint={b.note}>
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={b.per_source}>
                  <XAxis dataKey="source" tick={{ fill: "#8fa0bf", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis width={50} tick={{ fill: "#5b6a88", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: "rgba(255,255,255,.04)" }} contentStyle={{ background: "#0a0e1a", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12, fontSize: 12 }} />
                  <Bar dataKey="eps" fill="#22D3EE" radius={[8, 8, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
              {b.per_source.map((s: any) => (
                <span key={s.source} className="chip">{s.source}: {s.verified}/{s.events} verified{s.unmatched ? ` · ${s.unmatched} unmatched` : ""}</span>
              ))}
            </div>
          </Section>
        </>
      )}

      {parsers.length > 0 && (
        <Section className="mt-6" title="Onboarding time: sample → working, signed parser" hint="Measured by the Foundry for each parser. The problem statement cites 1–2 weeks of manual regex engineering per format.">
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {parsers.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                <span className="text-sm">{p.source_hint.vendor} {p.source_hint.product}</span>
                <span className="num font-mono text-sm text-cyan">{p.metrics.onboard_seconds ?? "-"} s</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section className="mt-6" title="What exists today vs EKALOG" hint="Stated conservatively from public documentation. Elastic Automatic Import can use a self-hosted model through an OpenAI-compatible connector.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-faint">
                <th className="py-2 pr-4">Capability</th>
                {COLS.map((c) => <th key={c} className={`pr-4 ${c === "EKALOG" ? "text-cyan" : ""}`}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {MATRIX.map((r) => (
                <tr key={r.cap} className="border-t border-white/5 align-top">
                  <td className="py-3 pr-4 text-sm font-medium">{r.cap}</td>
                  {r.cols.map((c, i) => <td key={i} className={`py-3 pr-4 ${i === 3 ? "bg-cyan/[0.04]" : ""}`}><Mark c={c} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
