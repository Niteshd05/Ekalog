"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Filter, Lock, Plus, Search, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { EventDrawer } from "@/components/events";
import { Button, Glass, PageHeader, Pill, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, cls, CLASS_NAMES, SEVERITY } from "@/lib/format";

type F = { field: string; op: string; value: string };
const EXAMPLES = [
  "Blocked connections from outside to SSH",
  "High or critical severity detections",
  "Traffic to Germany",
  "Everything from 185.220.101.4",
  "Prompt injection attempts",
  "Denied RDP in the last 30 minutes",
];
const OP_LABEL: Record<string, string> = { eq: "=", neq: "≠", contains: "contains", gt: ">", lt: "<", gte: "≥", lte: "≤", in_cidr: "in", not_in_cidr: "not in", starts_with: "starts with" };

export default function Ask() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState<F[]>([]);
  const [minutes, setMinutes] = useState(0);
  const [summary, setSummary] = useState("");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [meta, setMeta] = useState<{ fields: Record<string, string>; ops: string[] } | null>(null);
  const [draft, setDraft] = useState<F>({ field: "dst_port", op: "eq", value: "22" });
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    api.get<any>("/api/search/fields").then(setMeta).catch(() => {});
  }, []);

  const ask = async (question = q) => {
    if (!question.trim()) return;
    setQ(question);
    setBusy(true);
    setErr("");
    try {
      const r = await api.post<any>("/api/ask", { question, limit: 200 });
      if (!r.ok) {
        setErr(r.error);
        return;
      }
      setFilters(r.filters);
      setMinutes(r.minutes);
      setSummary(r.summary);
      setRes(r);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  const rerun = async (fs: F[], mins = minutes) => {
    setFilters(fs);
    setRes(await api.post("/api/search", { filters: fs, minutes: mins, limit: 200 }));
  };

  return (
    <div>
      <PageHeader eyebrow="Ask EKALOG" title={<>Search in <span className="text-grad">plain English</span></>}
        subtitle="Ask a question the way you'd ask a colleague. The local model turns it into a precise, typed OCSF filter that you can see and edit - then the database answers. The model never sees a single event."
        actions={<Pill tone="ok"><Lock className="h-3 w-3" /> schema-only AI · your data stays in the database</Pill>} />

      <Glass hover={false} className="p-3">
        <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="flex items-center gap-3">
          <Search className="ml-2 h-5 w-5 text-cyan" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. blocked connections from outside to SSH today"
            className="w-full bg-transparent py-3 text-lg outline-none placeholder:text-faint" />
          <Button type="submit" variant="primary" loading={busy} icon={<Sparkles className="h-4 w-4" />}>Ask</Button>
        </form>
      </Glass>
      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((e) => <button key={e} onClick={() => ask(e)} className="chip text-muted transition hover:border-cyan/40 hover:text-ink">{e}</button>)}
      </div>

      <AnimatePresence>
        {busy && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-6 flex items-center gap-3 text-sm text-violet">
            <Bot className="h-4 w-4 animate-pulse" /> Local model is translating your question - it only knows the field names…
          </motion.div>
        )}
      </AnimatePresence>
      {err && (
        <Glass hover={false} className="mt-6 p-4 text-sm text-amber">{err}. You can still build the filter by hand below.</Glass>
      )}

      <Section className="mt-6" title="Filter" hint="Exactly what will run against the event store. Remove a chip or add one - no AI needed for edits."
        right={res && <span className="text-xs text-muted">{res.count} results · {res.ms} ms{res.llm_seconds ? ` · AI ${res.llm_seconds}s` : ""}</span>}>
        {summary && <div className="mb-3 text-sm text-muted">Understood as: <span className="text-ink">{summary}</span></div>}
        <div className="flex flex-wrap items-center gap-2">
          {filters.map((f, i) => (
            <span key={i} className="chip border-cyan/30 bg-cyan/10 font-mono text-cyan">
              {f.field} <span className="text-muted">{OP_LABEL[f.op] ?? f.op}</span> {String(f.value)}
              <button onClick={() => rerun(filters.filter((_, j) => j !== i))} aria-label="Remove"><X className="h-3 w-3" /></button>
            </span>
          ))}
          {minutes > 0 && <span className="chip">last {minutes} min <button onClick={() => { setMinutes(0); rerun(filters, 0); }}><X className="h-3 w-3" /></button></span>}
          {!filters.length && <span className="text-sm text-faint">No filter yet.</span>}
        </div>
        {meta && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/5 pt-4">
            <Filter className="h-4 w-4 text-muted" />
            <select className="field w-auto py-1.5 text-sm" value={draft.field} onChange={(e) => setDraft({ ...draft, field: e.target.value })}>
              {Object.keys(meta.fields).map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <select className="field w-auto py-1.5 text-sm" value={draft.op} onChange={(e) => setDraft({ ...draft, op: e.target.value })}>
              {meta.ops.map((o) => <option key={o} value={o}>{OP_LABEL[o] ?? o}</option>)}
            </select>
            <input className="field w-48 py-1.5 font-mono text-sm" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => rerun([...filters, draft])}>Add</Button>
          </div>
        )}
      </Section>

      {res && (
        <Section className="mt-6" title="Results">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-faint">
                <tr><th className="py-2 pr-3">Time</th><th className="pr-3">Class</th><th className="pr-3">Source → Destination</th><th className="pr-3">Action</th><th className="pr-3">Severity</th><th>Device</th></tr>
              </thead>
              <tbody>
                {res.events.map((e: any) => (
                  <tr key={e.id} onClick={() => setOpen(e.id)} className="cursor-pointer border-t border-white/5 transition hover:bg-white/[0.04]">
                    <td className="num py-2 pr-3 font-mono text-xs text-muted">{clock(e.time)}</td>
                    <td className="pr-3">{CLASS_NAMES[e.class_uid] ?? e.class_name}{e.ekalog?.injection?.detected && <Pill tone="danger" className="ml-2">injection</Pill>}</td>
                    <td className="pr-3 font-mono text-xs">{e.src_endpoint?.ip ?? "-"} → {e.dst_endpoint?.ip ?? "-"}{e.dst_endpoint?.port ? `:${e.dst_endpoint.port}` : ""}</td>
                    <td className="pr-3 text-xs">{e.action ?? e.disposition ?? ""}</td>
                    <td className={cls("pr-3 text-xs", (SEVERITY[e.severity_id] ?? SEVERITY[0]).tone)}>{(SEVERITY[e.severity_id] ?? SEVERITY[0]).label}</td>
                    <td className="text-xs text-muted">{e.metadata?.product?.name || e.ekalog?.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!res.events.length && <div className="py-10 text-center text-sm text-muted">No matching events. Try removing a filter.</div>}
          </div>
        </Section>
      )}
      <EventDrawer id={open} onClose={() => setOpen(null)} />
    </div>
  );
}
