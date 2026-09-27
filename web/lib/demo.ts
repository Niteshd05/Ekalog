"use client";
// One-click guided demo: learn a parser for every sample vendor that has none yet, then stream them all.
import { api, ParserSummary, Sample, waitJob } from "./api";
import { toast } from "./live";

export const DEMO_EPS = 180; // per source -> ~1.3k events/s across 7 vendors, easy on any laptop

export async function runDemo(onStep: (msg: string) => void) {
  const [samples, parsers] = await Promise.all([
    api.get<Sample[]>("/api/samples"),
    api.get<ParserSummary[]>("/api/parsers"),
  ]);
  const bound = new Set(parsers.flatMap((p) => p.sources));
  const vendors = samples.filter((s) => s.kind === "samples");
  for (const s of vendors) {
    const source = s.name.replace(/\.[^.]+$/, "");
    if (bound.has(source)) continue;
    onStep(`Learning a parser for ${s.name}…`);
    const fd = new FormData();
    fd.append("sample", s.path);
    fd.append("source", source);
    const { job_id } = await api.form<{ job_id: string }>("/api/sources/onboard", fd);
    const j = await waitJob(job_id);
    if (j.stage === "error") toast({ tone: "danger", title: `Could not onboard ${s.name}`, body: j.error });
  }
  onStep("Streaming all sources…");
  for (const s of vendors) {
    await api.post("/api/ingest/replay", { sample: s.path, source: s.name.replace(/\.[^.]+$/, ""), eps: DEMO_EPS, loop: true });
  }
  onStep("");
  toast({ tone: "ok", title: "Demo is live", body: `${vendors.length} vendors streaming. Try Drift Sentinel or Injection Guard next.` });
}
