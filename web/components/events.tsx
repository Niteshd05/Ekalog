"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, BadgeCheck, ShieldAlert, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { api, SlimEvent } from "@/lib/api";
import { clock, cls, CLASS_NAMES, SEVERITY } from "@/lib/format";
import { useLive } from "@/lib/live";
import { Button, Pill, spring } from "./ui";

/** Tiny dependency-free JSON syntax highlighter. */
export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const text = JSON.stringify(value, null, 2) ?? "";
  const parts: ReactNode[] = [];
  const re = /("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1]) {
      parts.push(<span key={k++} className={m[2] ? "text-cyan" : "text-mint"}>{m[1]}</span>);
      if (m[2]) parts.push(m[2]);
    } else if (m[3]) parts.push(<span key={k++} className="text-violet">{m[3]}</span>);
    else parts.push(<span key={k++} className="text-amber">{m[4]}</span>);
    last = re.lastIndex;
  }
  parts.push(text.slice(last));
  return <pre className={cls("mono-block", className)}>{parts}</pre>;
}

export function EventRow({ e, onClick }: { e: SlimEvent & { _at?: number }; onClick?: () => void }) {
  const sev = SEVERITY[e.severity_id] ?? SEVERITY[0];
  const fresh = e._at && Date.now() - e._at < 400;
  return (
    <motion.button layout="position" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2 }}
      onClick={onClick}
      className={cls("group grid w-full grid-cols-[72px_1fr_auto] items-center gap-3 rounded-xl border-l-2 px-3 py-2 text-left text-xs transition hover:bg-white/[0.05]",
        e.injection ? "border-rose bg-rose/[0.06]" : e.status === "unmatched" ? "border-amber bg-amber/[0.04]" : fresh ? "border-cyan bg-cyan/[0.05]" : "border-transparent")}>
      <span className="num font-mono text-faint">{clock(e.time)}</span>
      <span className="flex min-w-0 items-center gap-2">
        <span className={cls("shrink-0 font-medium", sev.tone)}>{CLASS_NAMES[e.class_uid] ?? e.class_name}</span>
        <span className="truncate font-mono text-muted">
          {e.status === "unmatched" ? "quarantined - awaiting parser" :
            e.title ? e.title : !e.src && e.user ? `user ${e.user}` : `${e.src ?? "?"} → ${e.dst ?? "?"}${e.dst_port ? ":" + e.dst_port : ""}`}
        </span>
      </span>
      <span className="flex items-center gap-2">
        {e.action && <span className="hidden text-faint sm:inline">{e.action}</span>}
        <span className="hidden rounded-md bg-white/5 px-1.5 py-0.5 text-[10px] text-muted md:inline">{e.vendor || e.source}</span>
        {e.injection ? <ShieldAlert className="h-3.5 w-3.5 text-rose" /> :
          e.status === "unmatched" ? <TriangleAlert className="h-3.5 w-3.5 text-amber" /> :
            e.verified ? <BadgeCheck className="h-3.5 w-3.5 text-mint" /> : null}
      </span>
    </motion.button>
  );
}

export function EventDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const [ev, setEv] = useState<any>(null);
  useEffect(() => {
    setEv(null);
    if (id != null) api.get(`/api/events/${id}`).then(setEv).catch(() => setEv({ error: "Event no longer in store" }));
  }, [id]);
  return (
    <AnimatePresence>
      {id != null && (
        <motion.div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-[2px]" initial={{ opacity: 0 }}
          animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.aside className="glass m-3 flex w-full max-w-2xl flex-col overflow-hidden" initial={{ x: 60 }} animate={{ x: 0 }}
            exit={{ x: 60 }} transition={spring} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-white/10 p-5">
              <div>
                <div className="text-xs uppercase tracking-wider text-muted">Normalized OCSF event #{id}</div>
                <div className="mt-1 font-display text-lg font-semibold">{ev?.class_name ?? "Loading…"}</div>
              </div>
              <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close"><X className="h-5 w-5" /></button>
            </div>
            {ev && !ev.error && (
              <div className="flex flex-wrap gap-2 border-b border-white/10 px-5 py-3">
                <Pill tone="info">parser {ev.ekalog?.parser?.id ?? "-"} v{ev.ekalog?.parser?.version ?? "-"}</Pill>
                <Pill tone="muted">template {ev.ekalog?.template_id ?? "-"}</Pill>
                <Pill tone={ev.ekalog?.lossless?.verified ? "ok" : "warn"}>
                  {ev.ekalog?.lossless?.verified ? "round-trip verified" : "not verified"}
                </Pill>
                {ev.ekalog?.injection?.detected && <Pill tone="danger">injection attempt</Pill>}
              </div>
            )}
            <div className="flex-1 overflow-auto p-5">{ev && <JsonView value={ev} className="max-h-none" />}</div>
            <div className="flex justify-end gap-2 border-t border-white/10 p-4">
              <Button href={`/vault?id=${id}`} variant="primary" icon={<ArrowRight className="h-4 w-4" />}>Prove it's lossless</Button>
            </div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function LiveStream({ limit = 40, filter }: { limit?: number; filter?: (e: SlimEvent) => boolean }) {
  const events = useLive((s) => s.events);
  const [open, setOpen] = useState<number | null>(null);
  const list = (filter ? events.filter(filter) : events).slice(0, limit);
  return (
    <>
      <div className="flex flex-col gap-0.5">
        {list.map((e) => <EventRow key={e.id} e={e} onClick={() => setOpen(e.id)} />)}
        {!list.length && (
          <div className="py-10 text-center text-sm text-muted">
            Waiting for events… <Link href="/onboard" className="text-cyan hover:underline">onboard a source</Link> or run the demo.
          </div>
        )}
      </div>
      <EventDrawer id={open} onClose={() => setOpen(null)} />
    </>
  );
}
