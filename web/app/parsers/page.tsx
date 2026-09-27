"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Boxes, Check, Copy, Database, Download, FileCode2, Fingerprint, PackageOpen, Upload, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Empty, Glass, LabeledBy, PageHeader, Pill, Section, spring } from "@/components/ui";
import { api, download, ParserSummary, TemplateT } from "@/lib/api";
import { cls, CLASS_NAMES } from "@/lib/format";
import { toast } from "@/lib/live";

/** Schema Explorer: vendor fields (left) flow into OCSF paths (right); unmapped fields flow into "preserved". */
function SchemaFlow({ t }: { t: TemplateT }) {
  const slots = t.slots.filter((s) => s.name);
  const targets = useMemo(() => {
    const set = Array.from(new Set(slots.map((s) => s.ocsf ?? "__kept")));
    return set.sort((a, b) => (a === "__kept" ? 1 : b === "__kept" ? -1 : a.localeCompare(b)));
  }, [t.tid]);
  const rowH = 24;
  const h = Math.max(slots.length, targets.length) * rowH + 20;
  const W = 760;
  const lx = 190;
  const rx = W - 230;
  const ly = (i: number) => 14 + i * ((h - 28) / Math.max(1, slots.length - 1 || 1));
  const ry = (i: number) => 14 + i * ((h - 28) / Math.max(1, targets.length - 1 || 1));
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="overflow-x-auto">
      <svg width={W} height={h} className="min-w-[760px]">
        {slots.map((s, i) => {
          const j = targets.indexOf(s.ocsf ?? "__kept");
          const y1 = ly(i);
          const y2 = ry(j);
          const kept = !s.ocsf;
          const on = hover === null || hover === s.name || hover === (s.ocsf ?? "__kept");
          return (
            <motion.path key={s.pos} d={`M${lx},${y1} C${(lx + rx) / 2},${y1} ${(lx + rx) / 2},${y2} ${rx},${y2}`}
              fill="none" stroke={kept ? "#8B5CF6" : s.labeled_by === "llm" ? "#C084FC" : "#22D3EE"}
              strokeOpacity={on ? (kept ? 0.35 : 0.6) : 0.06} strokeWidth={on ? 1.6 : 1}
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.8, delay: i * 0.015 }} />
          );
        })}
        {slots.map((s, i) => (
          <g key={`l${s.pos}`} onMouseEnter={() => setHover(s.name)} onMouseLeave={() => setHover(null)} className="cursor-default">
            <circle cx={lx} cy={ly(i)} r={3} fill={s.ocsf ? "#22D3EE" : "#8B5CF6"} />
            <text x={lx - 10} y={ly(i) + 4} textAnchor="end" fontSize={11} fontFamily="var(--font-jet)" fill="#c7d2e8">{s.name}</text>
          </g>
        ))}
        {targets.map((p, j) => (
          <g key={`r${p}`} onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)} className="cursor-default">
            <circle cx={rx} cy={ry(j)} r={3.5} fill={p === "__kept" ? "#8B5CF6" : "#34D399"} />
            <text x={rx + 10} y={ry(j) + 4} fontSize={11} fontFamily="var(--font-jet)" fill={p === "__kept" ? "#a78bfa" : "#a7f3d0"}>
              {p === "__kept" ? "unmapped (preserved)" : p}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function ExportModal({ pid, onClose }: { pid: string | null; onClose: () => void }) {
  const [flavor, setFlavor] = useState("grok");
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (pid) api.get<string>(`/api/parsers/${pid}/export?flavor=${flavor}`).then(setText);
  }, [pid, flavor]);
  return (
    <AnimatePresence>
      {pid && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div className="glass flex max-h-[85vh] w-full max-w-4xl flex-col p-6" initial={{ scale: 0.97 }} animate={{ scale: 1 }} transition={spring} onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="font-display text-lg font-semibold">Export {pid}</div>
                <div className="text-sm text-muted">EKALOG feeds your existing pipeline - it does not have to replace it.</div>
              </div>
              <button onClick={onClose} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <div className="mb-3 flex gap-2">
              {[["grok", "Logstash Grok"], ["vrl", "Vector VRL"], ["regex", "Fluent Bit / regex"]].map(([k, l]) => (
                <button key={k} onClick={() => setFlavor(k)} className={cls("chip", flavor === k && "border-cyan/60 bg-cyan/10 text-cyan")}>{l}</button>
              ))}
              <div className="ml-auto flex gap-2">
                <Button variant="subtle" icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied" : "Copy"}</Button>
                <Button icon={<Download className="h-4 w-4" />} onClick={() => download(new Blob([text]), `${pid}.${flavor === "grok" ? "grok.conf" : flavor === "vrl" ? "vrl" : "regex.txt"}`)}>Download</Button>
              </div>
            </div>
            <pre className="mono-block flex-1 text-[11px] text-muted">{text}</pre>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function Parsers() {
  const [list, setList] = useState<ParserSummary[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [tab, setTab] = useState(0);
  const [exp, setExp] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);
  const [pending, setPending] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.get<ParserSummary[]>("/api/parsers").then((l) => {
    setList(l);
    if (!sel && l[0]) setSel(l[0].id);
  });
  useEffect(() => { load(); }, []);
  useEffect(() => {
    setTab(0);
    if (sel) api.get<any>(`/api/parsers/${sel}`).then(setDetail);
  }, [sel]);

  const importPack = async (f: File, trust = false) => {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("trust", String(trust));
    const r = await api.form<any>("/api/packs/import", fd);
    setReport(r);
    setPending(r.needs_trust ? f : null);
    if (r.ok) {
      toast({ tone: "ok", title: "Pack imported", body: `${r.parsers.length} parser(s) verified and activated` });
      load();
    }
  };

  const t: TemplateT | undefined = detail?.templates?.[tab];

  return (
    <div>
      <PageHeader eyebrow="Parser registry" title={<>Signed, versioned, <span className="text-grad">portable</span></>}
        subtitle="Every parser is an immutable artifact with a content hash, an Ed25519 signature and embedded test vectors. Carry them into an air-gapped SOC as a .ekapack - import refuses anything tampered with or failing its tests."
        actions={<>
          <input ref={fileRef} type="file" accept=".ekapack,.zip" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importPack(f); e.target.value = ""; }} />
          <Button icon={<Upload className="h-4 w-4" />} onClick={() => fileRef.current?.click()}>Import .ekapack</Button>
          <Button variant="primary" icon={<PackageOpen className="h-4 w-4" />} disabled={!list.length}
            onClick={async () => download(await api.blob("/api/packs/export", {}), `ekalog-${Date.now()}.ekapack`)}>Export all as .ekapack</Button>
        </>} />

      <AnimatePresence>
        {report && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <Glass hover={false} className={cls("mb-6 p-5", report.ok ? "border-mint/30" : "border-rose/40")}>
              <div className="mb-3 flex items-center justify-between">
                <div className="font-display font-semibold">{report.ok ? "Pack verified & imported" : "Pack refused"}</div>
                <button onClick={() => setReport(null)} className="text-muted"><X className="h-4 w-4" /></button>
              </div>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {report.checks.map((c: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    {c.ok ? <Check className="h-4 w-4 text-mint" /> : <X className="h-4 w-4 text-rose" />}{c.check}
                    <span className="truncate text-xs text-muted">{c.detail}</span>
                  </div>
                ))}
              </div>
              {pending && (
                <div className="mt-4 flex items-center gap-3 rounded-xl border border-amber/30 bg-amber/10 p-3 text-sm">
                  <Fingerprint className="h-4 w-4 text-amber" /> Unknown signer <span className="font-mono">{report.signer_fingerprint}</span>. Only trust it if you know who built this pack.
                  <Button className="ml-auto" onClick={() => importPack(pending, true)}>Trust & import</Button>
                </div>
              )}
            </Glass>
          </motion.div>
        )}
      </AnimatePresence>

      {!list.length ? (
        <Glass hover={false}><Empty icon={<Boxes className="h-6 w-6" />} title="No parsers yet" body="Onboard a sample or import a .ekapack." action={<Button href="/onboard">Onboard a source</Button>} /></Glass>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
          <div className="flex flex-col gap-3">
            {list.map((p) => (
              <button key={p.id} onClick={() => setSel(p.id)} className={cls("glass specular p-4 text-left transition", sel === p.id ? "border-cyan/50" : "opacity-85 hover:opacity-100")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-display font-semibold">{p.source_hint.vendor || "Custom"} {p.source_hint.product}</span>
                  <Pill tone={p.status === "active" ? "ok" : "warn"}>v{p.version}</Pill>
                </div>
                <div className="mt-1 font-mono text-[11px] text-faint">{p.id}</div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                  <span className="chip">{p.templates} templates</span>
                  {p.metrics.holdout_coverage != null && <span className="chip">holdout {(p.metrics.holdout_coverage * 100).toFixed(1)}%</span>}
                  {p.metrics.onboard_seconds != null && <span className="chip">learned in {p.metrics.onboard_seconds}s</span>}
                  <span className={cls("chip", p.provenance.labeler === "rules+llm" && "border-violet/40 text-violet")}>{p.provenance.labeler ?? "imported"}</span>
                </div>
              </button>
            ))}
          </div>

          {detail && (
            <div className="flex flex-col gap-6">
              <Section title={`${detail.id} · v${detail.version}`} right={<div className="flex gap-2">
                <Button variant="subtle" icon={<FileCode2 className="h-4 w-4" />} onClick={() => setExp(detail.id)}>Export Grok / VRL</Button>
                <Button variant="subtle" icon={<Database className="h-4 w-4" />} onClick={async () => download(await api.blob("/api/export/parquet"), "ekalog-ocsf.parquet")}>Parquet (ML)</Button>
              </div>}>
                <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <div><div className="text-xs text-muted">SHA-256</div><div className="truncate font-mono text-xs">{detail.sha256}</div></div>
                  <div><div className="text-xs text-muted">Signed by</div><div className="font-mono text-xs">{detail.provenance?.signer ?? "-"}</div></div>
                  <div><div className="text-xs text-muted">Model</div><div className="font-mono text-xs">{detail.provenance?.model ?? "none (rules)"}</div></div>
                  <div><div className="text-xs text-muted">Test vectors</div><div className="font-mono text-xs">{detail.tests?.length ?? 0}</div></div>
                  <div><div className="text-xs text-muted">Sources</div><div className="font-mono text-xs">{detail.sources.join(", ") || "-"}</div></div>
                  <div><div className="text-xs text-muted">Sample</div><div className="truncate font-mono text-xs">{detail.provenance?.sample?.file ?? "-"}</div></div>
                  <div><div className="text-xs text-muted">Round-trip</div><div className="font-mono text-xs">{detail.metrics?.roundtrip_verified ?? "-"} ok / {detail.metrics?.roundtrip_failed ?? 0} fail</div></div>
                  <div><div className="text-xs text-muted">Single-core</div><div className="font-mono text-xs">{detail.metrics?.eps_single_core?.toLocaleString() ?? "-"} ev/s</div></div>
                </div>
              </Section>

              <Section title="Schema explorer" hint="How each vendor field lands in OCSF. Cyan = named by rules, lilac = named by the local AI, violet = kept as-is under 'unmapped' (never discarded). Hover to trace a field.">
                <div className="mb-4 flex flex-wrap gap-2">
                  {detail.templates.map((x: TemplateT, i: number) => (
                    <button key={x.tid} onClick={() => setTab(i)} className={cls("chip", i === tab && "border-cyan/60 bg-cyan/10 text-cyan")}>
                      {CLASS_NAMES[x.class_uid] ?? x.class_uid} · {x.count}×
                    </button>
                  ))}
                </div>
                {t && <SchemaFlow t={t} />}
              </Section>

              {t && (
                <Section title="Template & field provenance">
                  <pre className="mono-block mb-4 text-[11px] text-muted">{t.display}</pre>
                  <div className="flex flex-wrap gap-2">
                    {t.slots.map((s) => (
                      <span key={s.pos} className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-2 py-1 text-xs">
                        <span className="font-mono">{s.name}</span><LabeledBy by={s.labeled_by} />
                      </span>
                    ))}
                  </div>
                </Section>
              )}
            </div>
          )}
        </div>
      )}
      <ExportModal pid={exp} onClose={() => setExp(null)} />
    </div>
  );
}
