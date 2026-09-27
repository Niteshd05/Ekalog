"use client";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, Link2, RefreshCw, ScanSearch, ShieldCheck, Wand2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { JsonView } from "@/components/events";
import { Button, Counter, Empty, Glass, InfoTip, PageHeader, Pill, Section, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, cls, CLASS_NAMES, compact } from "@/lib/format";
import { useLive } from "@/lib/live";

type Recon = {
  id: number; raw: string; rebuilt: string; match: boolean; vault_match: boolean; sha256_ingest: string; sha256_rebuilt: string;
  sha256_vault: string; method: string; template: string | null; bytes: number; rebuild_us: number;
  diff: { offset: number; rebuilt: string; raw: string }[]; normalized_fields: string[]; verbatim_fields: string[]; unmapped_fields: string[];
};

function Seal({ ok }: { ok: boolean }) {
  const text = ok ? "SHA-256 MATCH · 0 BYTES LOST · " : "HASH MISMATCH · CHECK DIFF · ";
  const col = ok ? "#34D399" : "#FB7185";
  return (
    <motion.div initial={{ scale: 2.2, opacity: 0, rotate: -25 }} animate={{ scale: 1, opacity: 1, rotate: -8 }}
      transition={{ type: "spring", stiffness: 180, damping: 12, delay: 0.35 }} className="relative h-36 w-36 shrink-0">
      <svg viewBox="0 0 200 200" className="absolute inset-0 animate-[spin_24s_linear_infinite]">
        <defs><path id="circ" d="M100,100 m-78,0 a78,78 0 1,1 156,0 a78,78 0 1,1 -156,0" /></defs>
        <text fill={col} fontSize="15.5" fontFamily="var(--font-jet)" letterSpacing="2.2">
          <textPath href="#circ">{text + text}</textPath>
        </text>
      </svg>
      <div className="absolute inset-[26%] grid place-items-center rounded-full border-2"
        style={{ borderColor: col, boxShadow: `0 0 40px ${col}55, inset 0 0 20px ${col}33` }}>
        {ok ? <ShieldCheck className="h-9 w-9" style={{ color: col }} /> : <ScanSearch className="h-9 w-9" style={{ color: col }} />}
      </div>
    </motion.div>
  );
}

function VaultInner() {
  const params = useSearchParams();
  const stats = useLive((s) => s.stats);
  const [events, setEvents] = useState<any[]>([]);
  const [source, setSource] = useState<string>("");
  const [sel, setSel] = useState<number | null>(null);
  const [rc, setRc] = useState<Recon | null>(null);
  const [ev, setEv] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [proof, setProof] = useState<any>(null);
  const [proving, setProving] = useState(false);

  const load = useCallback(() => {
    const q = new URLSearchParams({ limit: "40" });
    if (source) q.set("source", source);
    api.get<any[]>(`/api/events?${q}`).then(setEvents).catch(() => {});
  }, [source]);
  useEffect(load, [load]);

  const reconstruct = async (id: number) => {
    setSel(id);
    setBusy(true);
    setRc(null);
    try {
      const [r, e] = await Promise.all([api.get<Recon>(`/api/events/${id}/reconstruct`), api.get<any>(`/api/events/${id}`)]);
      setEv(e);
      setTimeout(() => setRc(r), 250);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const id = Number(params.get("id"));
    if (id) reconstruct(id);
  }, [params]);

  const prove = async () => {
    setProving(true);
    try {
      setProof(await api.get("/api/vault/verify?n=5000"));
    } finally {
      setProving(false);
    }
  };

  const sources = Object.keys(stats?.sources ?? {});
  return (
    <div>
      <PageHeader eyebrow="Lossless Vault" title={<>We don&apos;t claim zero loss. <span className="text-grad">We prove it.</span></>}
        subtitle="Pick any event. EKALOG rebuilds the original log line using only the normalized OCSF record (the template, the field values, and verbatim copies of anything a type conversion could alter) and compares its SHA-256 with the hash taken the moment the line arrived."
        actions={<Button variant="primary" loading={proving} onClick={prove} icon={<BadgeCheck className="h-4 w-4" />}>Verify last 5,000 now</Button>} />

      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Events verified" value={stats?.verified ?? 0} tone="text-mint"
          hint="Each of these was rebuilt from its normalized record and hash-matched at ingest time (proof mode: every event)." />
        <Stat label="Failures" value={stats?.verify_failed ?? 0} tone={(stats?.verify_failed ?? 0) ? "text-rose" : "text-ink"}
          hint="Events whose rebuild did not match. Any failure blocks a parser at the validation gate - so this should stay 0." />
        <Glass className="p-5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted">
            Losslessness <InfoTip>verified / (verified + failed). Unmatched lines are stored verbatim in raw_data and quarantined, so they are lossless too.</InfoTip>
          </div>
          <div className="mt-3 font-display text-3xl font-semibold text-mint"><Counter value={(stats?.lossless_score ?? 1) * 100} decimals={3} suffix="%" /></div>
        </Glass>
        <Glass className="p-5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted">
            Hash-chain ledger <InfoTip>Every ingest batch is chained: chain = SHA-256(previous chain + batch root). Checkpoints are Ed25519-signed. Deleting or editing any stored event breaks the chain.</InfoTip>
          </div>
          <div className="mt-3 font-display text-xl font-semibold">
            {proof ? (proof.ledger.ok ? <span className="text-mint">Intact ✓</span> : <span className="text-rose">Broken at #{proof.ledger.broken_at}</span>) : <span className="text-muted">Not checked</span>}
          </div>
          {proof && <div className="mt-1 text-xs text-muted">{proof.ledger.batches} batches · {proof.ledger.signed_checkpoints} signed checkpoints</div>}
        </Glass>
      </div>

      <AnimatePresence>
        {proof && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0 }}>
            <Glass hover={false} className="mt-4 flex flex-wrap items-center gap-4 p-4">
              <ShieldCheck className={cls("h-6 w-6", proof.failed ? "text-rose" : "text-mint")} />
              <div className="text-sm">
                Rebuilt <b className="num">{compact(proof.verified)}</b> of <b className="num">{compact(proof.checked)}</b> stored events from their normalized records in{" "}
                <b className="num">{proof.ms} ms</b> · <b className={proof.failed ? "text-rose" : "text-mint"}>{proof.failed} failures</b>
              </div>
            </Glass>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-6 grid gap-6 xl:grid-cols-[380px_1fr]">
        <Section title="Pick an event" right={<Button variant="subtle" onClick={load} icon={<RefreshCw className="h-3.5 w-3.5" />}>Refresh</Button>}>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {["", ...sources].map((s) => (
              <button key={s || "all"} onClick={() => setSource(s)} className={cls("chip", source === s && "border-cyan/60 bg-cyan/10 text-cyan")}>{s || "all"}</button>
            ))}
          </div>
          <div className="flex max-h-[560px] flex-col gap-1 overflow-auto pr-1">
            {events.map((e) => (
              <button key={e.id} onClick={() => reconstruct(e.id)}
                className={cls("rounded-xl border px-3 py-2 text-left text-xs transition",
                  sel === e.id ? "border-cyan/50 bg-cyan/10" : "border-transparent hover:bg-white/[0.05]")}>
                <div className="flex justify-between">
                  <span className="font-medium">{CLASS_NAMES[e.class_uid] ?? e.class_name}</span>
                  <span className="num font-mono text-faint">#{e.id} · {clock(e.time)}</span>
                </div>
                <div className="mt-0.5 truncate font-mono text-muted">{e.ekalog?.source} · {e.src_endpoint?.ip ?? ""} {e.dst_endpoint?.ip ? "→ " + e.dst_endpoint.ip : ""}</div>
              </button>
            ))}
            {!events.length && <div className="py-10 text-center text-sm text-muted">No events yet - stream a source first.</div>}
          </div>
        </Section>

        <Section title="Reconstruction" hint="Left: the raw bytes exactly as received (from the append-only vault). Right: rebuilt from the normalized record alone. The seal only appears when the SHA-256 hashes match.">
          {!sel && <Empty icon={<Wand2 className="h-6 w-6" />} title="Select an event to rebuild" body="Any event, any vendor. The rebuild takes microseconds." />}
          {sel && busy && <div className="shimmer h-64 rounded-2xl" />}
          {rc && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-5">
              <div className="flex flex-wrap items-center gap-5">
                <Seal ok={rc.match} />
                <div className="min-w-0 flex-1 space-y-2 text-sm">
                  <div className="font-display text-2xl font-semibold">{rc.match ? "Byte-exact." : "Mismatch"}</div>
                  <div className="text-muted">
                    {rc.bytes} bytes rebuilt in <b className="num text-ink">{rc.rebuild_us} µs</b> via <span className="text-ink">{rc.method}</span>.
                  </div>
                  <div className="grid gap-1 font-mono text-[11px]">
                    <div><span className="text-faint">ingest  </span><span className="text-mint">{rc.sha256_ingest}</span></div>
                    <div><span className="text-faint">rebuilt </span><span className={rc.match ? "text-mint" : "text-rose"}>{rc.sha256_rebuilt}</span></div>
                    <div><span className="text-faint">vault   </span><span className={rc.vault_match ? "text-mint" : "text-rose"}>{rc.sha256_vault}</span></div>
                  </div>
                </div>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <div className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted">Original bytes (vault)</div>
                  <pre className="mono-block text-[11.5px]">{rc.raw}</pre>
                </div>
                <div>
                  <div className="mb-1.5 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted">
                    Rebuilt from OCSF record {rc.match && <Pill tone="ok">identical</Pill>}
                  </div>
                  <pre className={cls("mono-block text-[11.5px]", rc.match ? "border-mint/30" : "border-rose/40")}>{rc.rebuilt}</pre>
                </div>
              </div>
              {rc.diff.length > 0 && (
                <div className="rounded-xl border border-rose/30 bg-rose/10 p-3 font-mono text-xs text-rose">
                  first difference at byte {rc.diff[0].offset}: rebuilt «{rc.diff[0].rebuilt}» vs raw «{rc.diff[0].raw}»
                </div>
              )}
              {rc.template && (
                <div>
                  <div className="mb-1.5 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted">
                    <Link2 className="h-3.5 w-3.5" /> Recipe: parser template
                    <InfoTip>Literal text comes from the signed parser version referenced by the event; each ‹slot› is filled from an OCSF field, an 'unmapped' field, or a verbatim copy.</InfoTip>
                  </div>
                  <pre className="mono-block text-[11px] text-muted">{rc.template}</pre>
                </div>
              )}
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="text-muted">Filled from:</span>
                {rc.normalized_fields.slice(0, 14).map((f) => <Pill key={f} tone="info">{f}</Pill>)}
                {rc.unmapped_fields.length > 0 && <Pill tone="muted">{rc.unmapped_fields.length} unmapped fields</Pill>}
                {rc.verbatim_fields.length > 0 && (
                  <span title="Values whose typed form cannot reproduce the original text exactly (e.g. timestamps) are also kept verbatim.">
                    <Pill tone="violet">verbatim: {rc.verbatim_fields.join(", ")}</Pill>
                  </span>
                )}
              </div>
              {ev && (
                <details className="group">
                  <summary className="cursor-pointer text-sm text-cyan">Show the full normalized OCSF record</summary>
                  <JsonView value={ev} className="mt-2 max-h-96" />
                </details>
              )}
            </motion.div>
          )}
        </Section>
      </div>
    </div>
  );
}

export default function Vault() {
  return <Suspense><VaultInner /></Suspense>;
}
