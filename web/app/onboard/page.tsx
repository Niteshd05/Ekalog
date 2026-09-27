"use client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot, Check, CircleX, Clock, Cpu, FileCode2, FileUp, Fingerprint, Loader2, Pickaxe, Play, ShieldCheck, Stamp, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Glass, InfoTip, LabeledBy, PageHeader, Pill, Section, spring } from "@/components/ui";
import { api, download, Sample, TemplateT } from "@/lib/api";
import { bytes, cls, CLASS_NAMES } from "@/lib/format";
import { FoundryMsg, useLive } from "@/lib/live";

type Phase = "idle" | "active" | "done" | "fail";

function StageCard({ n, title, icon, phase, children, hint }: {
  n: number; title: string; icon: React.ReactNode; phase: Phase; children: React.ReactNode; hint: string;
}) {
  return (
    <Glass layout hover={false}
      className={cls("flex min-h-[260px] flex-col p-5 transition-colors",
        phase === "active" && "border-cyan/40 shadow-[0_0_40px_rgba(34,211,238,0.15)]",
        phase === "done" && "border-mint/25", phase === "fail" && "border-rose/40")}>
      <div className="mb-3 flex items-center gap-3">
        <div className={cls("grid h-9 w-9 place-items-center rounded-xl border",
          phase === "done" ? "border-mint/30 bg-mint/10 text-mint" : phase === "active" ? "border-cyan/40 bg-cyan/10 text-cyan" :
            phase === "fail" ? "border-rose/40 bg-rose/10 text-rose" : "border-white/10 bg-white/5 text-faint")}>
          {phase === "active" ? <Loader2 className="h-4 w-4 animate-spin" /> : phase === "done" ? <Check className="h-4 w-4" /> : icon}
        </div>
        <div>
          <div className="font-mono text-[10px] tracking-[0.2em] text-faint">STAGE {n}</div>
          <div className="flex items-center gap-1.5 font-display font-semibold">{title}<InfoTip>{hint}</InfoTip></div>
        </div>
      </div>
      <div className={cls("flex-1 text-sm", phase === "idle" && "opacity-40")}>{children}</div>
    </Glass>
  );
}

function Highlighted({ text }: { text: string }) {
  // render template display with slots highlighted: <name:type>
  const parts = text.split(/(<[a-z0-9_.]+:[a-z0-9]+>)/g);
  return (
    <>
      {parts.map((p, i) =>
        /^<[a-z0-9_.]+:[a-z0-9]+>$/.test(p) ? <span key={i} className="rounded bg-cyan/15 px-0.5 text-cyan">{p}</span> : <span key={i}>{p}</span>)}
    </>
  );
}

export default function Onboard() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [sample, setSample] = useState<Sample | null>(null);
  const [source, setSource] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [startAt, setStartAt] = useState(0);
  const [now, setNow] = useState(0);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [tab, setTab] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [err, setErr] = useState("");
  const job = useLive((s) => (jobId ? s.jobs[jobId] : undefined));
  const tokRef = useRef<HTMLPreElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get<Sample[]>("/api/samples").then((s) => setSamples(s.filter((x) => x.kind !== "attack"))).catch(() => {});
  }, []);

  const msgs = job?.msgs ?? [];
  const get = (stage: string) => msgs.filter((m) => m.stage === stage);
  const one = (stage: string): FoundryMsg | undefined => get(stage).at(-1);
  const mined = one("mined");
  const rules = one("rules_labeled");
  const llmReq = one("llm_request");
  const llmDone = one("llm_done");
  const gates = get("gate");
  const done = one("done");
  const error = one("error");
  const running = !!jobId && !done && !error;

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [running]);
  useEffect(() => {
    if (tokRef.current) tokRef.current.scrollTop = tokRef.current.scrollHeight;
  }, [job?.tokens]);
  useEffect(() => {
    if (done && jobId) api.get<any>(`/api/foundry/${jobId}`).then((j) => setResult(j.result));
  }, [done, jobId]);

  const elapsed = done ? done.elapsed : running ? (now - startAt) / 1000 : 0;
  const phase = (has: boolean, active: boolean): Phase => (has ? "done" : active ? "active" : "idle");
  const pMine = phase(!!mined, running);
  const pLabel = phase(!!llmDone, !!mined && running);
  const gatesFail = gates.some((g) => !g.ok);
  const pVal: Phase = gates.length >= 6 ? (gatesFail ? "fail" : "done") : llmDone && running ? "active" : "idle";
  const pSeal: Phase = done ? (done.gates_passed ? "done" : "fail") : "idle";

  const start = async () => {
    setErr("");
    setResult(null);
    setTab(0);
    const fd = new FormData();
    if (file) fd.append("file", file);
    else if (sample) fd.append("sample", sample.path);
    else return;
    fd.append("source", source || (file?.name ?? sample!.name).replace(/\.[^.]+$/, ""));
    try {
      const r = await api.form<{ job_id: string; sample_path?: string }>("/api/sources/onboard", fd);
      setStartAt(Date.now());
      setNow(Date.now());
      setJobId(r.job_id);
      if (r.sample_path && file) setSample({ name: file.name, path: r.sample_path, kind: "samples", bytes: file.size, preview: [] });
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const stream = async () => {
    if (!sample || !result) return;
    setStreaming(true);
    await api.post("/api/ingest/replay", { sample: sample.path, source: source || sample.name.replace(/\.[^.]+$/, ""), eps: 300, loop: true });
  };

  const templates: TemplateT[] = result?.templates ?? [];
  const t = templates[tab];
  const pickedName = file?.name ?? sample?.name;

  return (
    <div>
      <PageHeader eyebrow="Parser Foundry" title={<>Add a log source <span className="text-grad">in seconds</span></>}
        subtitle="Drop a sample from any firewall, router, VPN or IDS. EKALOG learns its structure, names every field (rules first, then the local AI for the rest), validates the result on lines it has never seen, and seals a signed parser. Nobody writes a regex."
        actions={<Pill tone="violet"><Cpu className="h-3 w-3" /> AI runs locally · no data leaves this machine</Pill>} />

      {/* INPUT */}
      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Glass hover={false}
          className={cls("flex flex-col items-center justify-center gap-3 border-dashed p-8 text-center transition", drag && "border-cyan/60 bg-cyan/5")}
          onDragOver={(e: React.DragEvent) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e: React.DragEvent) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) { setFile(f); setSample(null); }
          }}>
          <div className="grid h-14 w-14 place-items-center rounded-2xl border border-white/10 bg-white/5 text-cyan"><FileUp className="h-6 w-6" /></div>
          <div className="font-display text-lg font-semibold">{pickedName ?? "Drop a log file here"}</div>
          <div className="text-sm text-muted">
            {file ? bytes(file.size) : sample ? "sample from the demo set" : "any text log: syslog, key=value, CSV, TSV, JSON, CEF, LEEF…"}
          </div>
          <input ref={inputRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setSample(null); } }} />
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <Button onClick={() => inputRef.current?.click()}>Browse…</Button>
            {(file || sample) && <Button variant="subtle" icon={<X className="h-4 w-4" />} onClick={() => { setFile(null); setSample(null); }}>Clear</Button>}
          </div>
        </Glass>
        <Glass hover={false} className="flex flex-col gap-4 p-6">
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">Or pick a sample device</div>
            <div className="flex flex-wrap gap-2">
              {samples.filter((s) => s.kind === "samples").map((s) => (
                <button key={s.path} onClick={() => { setSample(s); setFile(null); setSource(s.name.replace(/\.[^.]+$/, "")); }}
                  className={cls("chip transition hover:border-cyan/40", sample?.path === s.path && "border-cyan/60 bg-cyan/10 text-cyan")}>
                  {s.name}
                </button>
              ))}
            </div>
          </div>
          <label className="text-xs font-medium uppercase tracking-wider text-muted">
            Source name <span className="normal-case tracking-normal text-faint">(how this stream is identified)</span>
            <input className="field mt-2 font-mono text-sm normal-case tracking-normal" placeholder="e.g. hq-fortigate" value={source}
              onChange={(e) => setSource(e.target.value.replace(/[^a-zA-Z0-9_.:-]/g, ""))} />
          </label>
          {sample?.preview?.length ? <pre className="mono-block max-h-24 text-[11px] text-muted">{sample.preview.join("\n")}</pre> : null}
          <Button variant="primary" disabled={!file && !sample} loading={running} onClick={start} icon={<Pickaxe className="h-4 w-4" />}>
            {running ? "Learning…" : "Learn a parser"}
          </Button>
          {err && <div className="text-sm text-rose">{err}</div>}
        </Glass>
      </div>

      {/* THEATRE */}
      {jobId && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring} className="mt-8">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="font-display text-xl font-semibold">Foundry run <span className="font-mono text-sm text-faint">#{jobId}</span></div>
            <div className="flex items-center gap-3 text-sm">
              <span className="text-muted">Hand-written parser: <b className="text-ink">1–2 weeks</b> <span className="text-faint">(PS estimate)</span></span>
              <span className="chip border-cyan/30 bg-cyan/10 text-cyan"><Clock className="h-3.5 w-3.5" /> EKALOG: <span className="num font-semibold">{elapsed.toFixed(1)} s</span></span>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StageCard n={1} title="Mine templates" icon={<Pickaxe className="h-4 w-4" />} phase={pMine}
              hint="EkaMiner clusters lines by structure. It keeps every separator byte, so the parser is lossless by construction - unlike Drain, which discards them.">
              {mined ? (
                <div>
                  <div className="font-display text-3xl font-semibold text-cyan num">{mined.templates}</div>
                  <div className="text-xs text-muted">templates from {mined.lines.toLocaleString()} lines in {mined.ms} ms</div>
                  <div className="mt-3 flex max-h-36 flex-col gap-1.5 overflow-auto">
                    <AnimatePresence>
                      {(mined.preview ?? []).slice(0, 6).map((p: any, i: number) => (
                        <motion.div key={p.tid} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.08 }}
                          className="truncate rounded-lg border border-white/10 bg-black/30 px-2 py-1 font-mono text-[10.5px] text-muted" title={p.display}>
                          <span className="mr-1 text-faint">{p.count}×</span><Highlighted text={p.display} />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </div>
              ) : <div className="text-muted">Reading structure…</div>}
            </StageCard>

            <StageCard n={2} title="Name the fields" icon={<Bot className="h-4 w-4" />} phase={pLabel}
              hint="Rules first (the device's own keys, file headers, documented vendor layouts). The local model only fills the gaps - and only ever sees typed placeholders, never raw log text.">
              {rules && (
                <div className="mb-2 text-xs text-muted">
                  <span className="text-ink num">{rules.mapped}</span>/{rules.slots} fields mapped by rules
                  {rules.vendor && <> · detected <span className="text-ink">{rules.vendor} {rules.product}</span></>}
                </div>
              )}
              {llmReq && !llmDone && (
                <div className="mb-2 flex items-center gap-2 text-xs text-violet"><Bot className="h-3.5 w-3.5" />{llmReq.model} labeling {llmReq.templates} template(s)…</div>
              )}
              <pre ref={tokRef} className="mono-block h-32 text-[10.5px] text-violet/90">{job?.tokens || (rules ? (llmDone ? "(no AI needed - rules covered every field)" : "…") : "")}</pre>
              {llmDone && (
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                  {llmDone.used ? <Pill tone="violet">AI labeled {llmDone.slots_labeled}</Pill> : <Pill tone="muted">{llmDone.error ? "AI offline - rules only" : "AI not needed"}</Pill>}
                  {llmDone.cache_hits > 0 && <Pill tone="info">{llmDone.cache_hits} cached</Pill>}
                  {llmDone.rejected > 0 && <Pill tone="warn">{llmDone.rejected} AI answers rejected by type gate</Pill>}
                  {llmDone.skipped_injection > 0 && <Pill tone="danger">{llmDone.skipped_injection} withheld (injection)</Pill>}
                </div>
              )}
            </StageCard>

            <StageCard n={3} title="Validate" icon={<ShieldCheck className="h-4 w-4" />} phase={pVal}
              hint="20% of the sample is held out and never used for learning. The parser must cover it, rebuild every line byte-exact, pass type and OCSF checks, and make semantic sense.">
              <div className="flex flex-col gap-2">
                {gates.map((g, i) => (
                  <motion.div key={g.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.12 }}
                    className="flex items-start gap-2">
                    {g.ok ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-mint" /> : <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-rose" />}
                    <div>
                      <div className="text-[13px]">{g.label}</div>
                      <div className="text-[11px] text-muted">{g.detail}</div>
                    </div>
                  </motion.div>
                ))}
                {!gates.length && <div className="text-muted">Waiting for labels…</div>}
              </div>
            </StageCard>

            <StageCard n={4} title="Seal & activate" icon={<Stamp className="h-4 w-4" />} phase={pSeal}
              hint="The parser becomes an immutable artifact: semantic version, SHA-256 content hash, Ed25519 signature, embedded test vectors. It is hot-swapped into the data plane with no restart.">
              {done ? (
                <motion.div initial={{ scale: 1.3, opacity: 0, rotate: -8 }} animate={{ scale: 1, opacity: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 200, damping: 14 }}>
                  <div className="flex items-center gap-2">
                    <span className="font-display text-xl font-semibold">{done.parser_id}</span>
                    <Pill tone={done.status === "active" ? "ok" : "warn"}>v{done.version} · {done.status === "active" ? "live" : "needs review"}</Pill>
                  </div>
                  <div className="mt-3 flex items-center gap-2 font-mono text-[11px] text-muted"><Fingerprint className="h-3.5 w-3.5 text-cyan" />sha256:{done.sha256?.slice(0, 24)}…</div>
                  <div className="mt-1 text-[11px] text-muted">Ed25519-signed · {done.metrics?.templates} templates · holdout {(done.metrics?.holdout_coverage * 100).toFixed(1)}%</div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {sample && <Button variant="primary" onClick={stream} disabled={streaming} icon={<Play className="h-4 w-4" />}>{streaming ? "Streaming ✓" : "Stream it now"}</Button>}
                    <Button icon={<FileCode2 className="h-4 w-4" />} onClick={async () => download(await api.blob(`/api/parsers/${done.parser_id}/export?flavor=grok`), `${done.parser_id}.grok.conf`)}>Grok</Button>
                  </div>
                </motion.div>
              ) : error ? <div className="text-rose">{error.message}</div> : <div className="text-muted">Awaiting validation…</div>}
            </StageCard>
          </div>
        </motion.div>
      )}

      {/* MAPPING */}
      {templates.length > 0 && (
        <Section className="mt-8" title="What EKALOG learned" hint="Each template is one message shape. Every variable slot is named and, where it fits, mapped to an OCSF field. Unmapped slots are not lost - they are kept under 'unmapped' with their names.">
          <div className="mb-4 flex flex-wrap gap-2">
            {templates.map((x, i) => (
              <button key={x.tid} onClick={() => setTab(i)}
                className={cls("chip transition", i === tab ? "border-cyan/60 bg-cyan/10 text-cyan" : "hover:border-white/20")}>
                {CLASS_NAMES[x.class_uid] ?? x.class_uid} · {x.count}×
              </button>
            ))}
          </div>
          {t && (
            <>
              <div className="mono-block mb-4 text-[11px] text-muted"><Highlighted text={t.display} /></div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wider text-faint">
                    <tr><th className="py-2 pr-3">Field</th><th className="pr-3">Example</th><th className="pr-3">Type</th><th className="pr-3">OCSF path</th><th>Named by</th></tr>
                  </thead>
                  <tbody>
                    {t.slots.map((s) => (
                      <tr key={s.pos} className="border-t border-white/5">
                        <td className="py-2 pr-3 font-mono text-[12.5px]">{s.name}</td>
                        <td className="max-w-[220px] truncate pr-3 font-mono text-[12px] text-muted" title={s.examples.join(", ")}>{s.examples[0] ?? ""}</td>
                        <td className="pr-3 text-xs text-muted">{s.type}</td>
                        <td className="pr-3 font-mono text-[12px]">{s.ocsf ? <span className="text-cyan">{s.ocsf}</span> : <span className="text-faint">unmapped (kept)</span>}</td>
                        <td><LabeledBy by={s.labeled_by} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Section>
      )}
      <RecentJobs />
    </div>
  );
}

function RecentJobs() {
  const [jobs, setJobs] = useState<any[]>([]);
  useEffect(() => {
    api.get<any[]>("/api/foundry/jobs").then(setJobs).catch(() => {});
  }, []);
  const shown = useMemo(() => jobs.slice(0, 8), [jobs]);
  if (!shown.length) return null;
  return (
    <Section className="mt-8" title="Recent foundry runs">
      <div className="grid gap-2 md:grid-cols-2">
        {shown.map((j) => (
          <div key={j.id} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm">
            <div>
              <div className="font-mono">{j.source} <span className="text-faint">· {j.kind}</span></div>
              <div className="text-xs text-muted">{j.result?.parser_id ?? j.filename} {j.result?.version ? `v${j.result.version}` : ""}</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="num text-xs text-muted">{j.elapsed}s</span>
              <Pill tone={j.stage === "done" ? (j.result?.gates_passed ? "ok" : "warn") : j.stage === "error" ? "danger" : "info"}>{j.stage}</Pill>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
