"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, BookOpen, EyeOff, Play, ShieldAlert, ShieldCheck, Skull } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Button, Glass, InfoTip, PageHeader, Pill, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, cls } from "@/lib/format";
import { toast, useLive } from "@/lib/live";

type Verdict = { detected: boolean; score: number; indicators: string[]; spans: [number, number][]; line: string;
  llm_view: string; llm_withheld: boolean; threshold: number; reference: string };

const EXPLAIN: Record<string, string> = {
  instruction_override: "Tries to override the AI's instructions (“ignore previous instructions…”)",
  verdict_steering: "Tries to steer the verdict (“classify as benign”, “ignore these alerts”)",
  benign_framing: "Social-engineering cover story (“authorized testing”, “routine maintenance”)",
  ai_addressing: "Speaks directly to an AI analyst inside a log field",
  role_token: "Chat-template control tokens (<|im_start|>, [INST], ### Instruction)",
  log_forgery: "Embedded newline + fake syslog header: forges a second log entry (OWASP log injection)",
  control_chars: "Terminal escape / control characters that can hide or rewrite text",
  zero_width: "Invisible zero-width characters used to split keywords past filters",
  unicode_escapes: "Long runs of \\u / \\x escapes hiding text",
  encoded_instruction: "Base64 or escaped payload that decodes to an instruction",
};

function Highlight({ text, spans }: { text: string; spans: [number, number][] }) {
  const sorted = [...spans].sort((a, b) => a[0] - b[0]);
  const out: React.ReactNode[] = [];
  let pos = 0;
  sorted.forEach(([s, e], i) => {
    if (s < pos) return;
    out.push(<span key={`t${i}`}>{text.slice(pos, s)}</span>);
    out.push(<mark key={`m${i}`} className="rounded bg-rose/25 px-0.5 text-rose">{text.slice(s, e)}</mark>);
    pos = e;
  });
  out.push(<span key="end">{text.slice(pos)}</span>);
  return <>{out}</>;
}

function visible(s: string) {
  // make invisible / control characters visible for the analyst
  return s.replace(/[\u200b-\u200f\u2060-\u2064\ufeff]/g, "⟨ZW⟩").replace(/\r/g, "⟨CR⟩").replace(/\n/g, "⟨LF⟩").replace(/\x1b/g, "⟨ESC⟩");
}

function GuardInner() {
  const params = useSearchParams();
  const [presets, setPresets] = useState<string[]>([]);
  const [line, setLine] = useState("");
  const [v, setV] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [alerts, setAlerts] = useState<any[]>([]);
  const live = useLive((s) => s.guard);
  const once = useRef(false);

  useEffect(() => {
    api.get<string[]>("/api/samples/lines?path=attack/injection.log&limit=20").then((p) => {
      setPresets(p);
      if (p[0]) setLine(p[0]);
    }).catch(() => {});
  }, []);
  useEffect(() => {
    api.get<any[]>("/api/guard/alerts").then(setAlerts).catch(() => {});
  }, [live.length]);

  const test = async (l = line) => {
    setBusy(true);
    try {
      setV(await api.post<Verdict>("/api/guard/test", { line: l }));
    } finally {
      setBusy(false);
    }
  };
  const streamAttacks = async () => {
    await api.post("/api/ingest/replay", { sample: "attack/injection.log", source: "fortigate", eps: 4 });
    toast({ tone: "info", title: "Attack file streaming", body: "11 poisoned FortiGate lines entering the pipeline at 4/s." });
  };
  useEffect(() => {
    if (params.get("stream") && !once.current) {
      once.current = true;
      streamAttacks();
    }
  }, [params]);

  return (
    <div>
      <PageHeader eyebrow="Injection Guard" title={<>Logs are attacker-controlled. <span className="text-grad">Our AI knows it.</span></>}
        subtitle="Attackers now hide instructions inside log fields to trick AI-powered SIEMs into calling an attack benign. EKALOG's model never reads raw log text - and every such payload becomes a detection instead of an evasion."
        actions={<Button variant="danger" onClick={streamAttacks} icon={<Skull className="h-4 w-4" />}>Stream the attack file</Button>} />

      <Glass hover={false} className="mb-6 grid gap-4 p-5 md:grid-cols-[auto_1fr]">
        <BookOpen className="h-6 w-6 text-amber" />
        <div className="text-sm leading-relaxed text-muted">
          <b className="text-ink">Grounded threat model.</b> In <i>“Just Testing, Move Along: Evasion of LLM-based System Log Interpretation by Prompt Injection”</i>{" "}
          (arXiv:2607.24174, July 2026), enriched log injections reached an <b className="text-rose">86.7% attack success rate</b> against Llama-3.3 and Qwen-3,
          getting malicious traces classified as benign. See also arXiv:2607.14493 on passive injection in <i>network security logs</i>.
        </div>
      </Glass>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <Section title="Test a log line" hint="Paste any log line, or pick one of the real payloads from the attack corpus.">
          <div className="mb-3 flex flex-wrap gap-1.5">
            {presets.map((p, i) => (
              <button key={i} onClick={() => { setLine(p); test(p); }} className="chip hover:border-rose/40">attack #{i + 1}</button>
            ))}
            <button onClick={() => { const l = 'date=2026-09-27 time=10:00:00 devname="FGT60F-HQ" srcip=10.1.2.3 dstip=8.8.8.8 action="accept" msg="normal traffic"'; setLine(l); test(l); }}
              className="chip hover:border-mint/40">clean line</button>
          </div>
          <textarea className="field h-36 font-mono text-xs" value={line} onChange={(e) => setLine(e.target.value)} spellCheck={false} />
          <div className="mt-3 flex justify-end">
            <Button variant="primary" loading={busy} onClick={() => test()} icon={<ShieldCheck className="h-4 w-4" />}>Inspect</Button>
          </div>
        </Section>

        <AnimatePresence mode="wait">
          {v ? (
            <motion.div key={v.line + v.score} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
              <Glass hover={false} className={cls("h-full p-6", v.detected ? "border-rose/40 shadow-[0_0_60px_rgba(251,113,133,0.15)]" : "border-mint/30")}>
                <div className="flex items-center gap-3">
                  {v.detected ? <ShieldAlert className="h-9 w-9 text-rose" /> : <ShieldCheck className="h-9 w-9 text-mint" />}
                  <div>
                    <div className={cls("font-display text-xl font-bold tracking-wide", v.detected ? "text-rose" : "text-mint")}>
                      {v.detected ? "PROMPT INJECTION BLOCKED" : "NO INJECTION FOUND"}
                    </div>
                    <div className="text-xs text-muted">score {v.score.toFixed(2)} · threshold {v.threshold}</div>
                  </div>
                </div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${v.score * 100}%` }} transition={{ duration: 0.8 }}
                    className={cls("h-full rounded-full", v.detected ? "bg-gradient-to-r from-amber to-rose" : "bg-mint")} />
                </div>
                <div className="mt-4 flex flex-col gap-2">
                  {v.indicators.map((i) => (
                    <div key={i} className="flex gap-2 text-sm"><Pill tone="danger">{i}</Pill><span className="text-muted">{EXPLAIN[i]}</span></div>
                  ))}
                </div>
                {v.detected && (
                  <div className="mt-4 rounded-2xl border border-white/10 bg-black/30 p-3 text-xs leading-relaxed text-muted">
                    The event is <b className="text-ink">still normalized losslessly</b> and stored, tagged <span className="font-mono text-rose">ekalog.injection.detected = true</span>,
                    and raised as an alert. Its template is <b className="text-ink">withheld from the model</b> during parser learning.
                  </div>
                )}
              </Glass>
            </motion.div>
          ) : (
            <Glass hover={false} className="grid h-full place-items-center p-6 text-sm text-muted">Pick an attack or paste a line.</Glass>
          )}
        </AnimatePresence>
      </div>

      {v && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Section title="The raw line (what a naive AI SIEM reads)" hint="Suspicious spans are highlighted. Invisible characters are made visible.">
            <pre className="mono-block text-[11.5px]"><Highlight text={visible(v.line)} spans={v.line === visible(v.line) ? v.spans : []} /></pre>
            <div className="mt-3 flex items-start gap-2 rounded-xl border border-rose/20 bg-rose/[0.06] p-3 text-xs text-muted">
              <Bot className="mt-0.5 h-4 w-4 shrink-0 text-rose" />
              A model that reads this line directly receives the attacker&apos;s instructions verbatim - exactly the setup the paper exploited.
            </div>
          </Section>
          <Section title="What EKALOG's model is allowed to see" hint="Typed values become tags, free text is elided, and templates flagged by the Guard are not sent at all. The model's answer is a JSON enum - it can name a field, never issue a verdict.">
            <pre className="mono-block text-[11.5px] text-violet/90">{v.llm_withheld ? "⟨ withheld: this template is never sent to the model ⟩" : v.llm_view}</pre>
            <div className="mt-3 flex items-start gap-2 rounded-xl border border-mint/20 bg-mint/[0.06] p-3 text-xs text-muted">
              <EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-mint" />
              Structural defense: no raw text in, only enum-constrained JSON out, never executed, never a verdict.
            </div>
          </Section>
        </div>
      )}

      <Section className="mt-6" title="Live detections" hint="Injection attempts seen in ingested traffic. Each is also a normal OCSF event with the injection tag."
        right={<Pill tone={alerts.length ? "danger" : "muted"}>{alerts.length} total</Pill>}>
        <div className="flex max-h-96 flex-col gap-2 overflow-auto">
          {alerts.map((a) => (
            <motion.div key={a.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
              className="rounded-2xl border border-rose/20 bg-rose/[0.04] p-3">
              <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs">
                <span className="num font-mono text-faint">#{a.id} · {clock(a.time)}</span>
                <span className="font-mono">{a.source}</span>
                {a.indicators.map((i: string) => <Pill key={i} tone="danger">{i}</Pill>)}
                <span className="ml-auto text-muted">score {a.score.toFixed(2)}</span>
              </div>
              <div className="truncate font-mono text-[11px] text-muted" title={a.line}>{visible(a.line)}</div>
            </motion.div>
          ))}
          {!alerts.length && (
            <div className="py-8 text-center text-sm text-muted">
              Nothing yet. <button onClick={streamAttacks} className="text-rose hover:underline">Stream the attack file</button> to see detections arrive live.
            </div>
          )}
        </div>
      </Section>
    </div>
  );
}

export default function Guard() {
  return <Suspense><GuardInner /></Suspense>;
}
