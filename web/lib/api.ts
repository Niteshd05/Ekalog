// Thin typed client for the EKALOG API. Same-origin in production (static export served by FastAPI);
// in dev, Next rewrites /api to :8000.

export type SlimEvent = {
  id: number;
  time: number;
  class_uid: number;
  class_name: string;
  severity_id: number;
  activity_id: number;
  src?: string;
  dst?: string;
  dst_port?: number;
  action?: string;
  vendor?: string;
  source: string;
  status: "parsed" | "unmatched";
  verified: boolean | null;
  injection: boolean;
  title?: string;
  user?: string;
};

export type SourceHealth = {
  source: string;
  status: "learning" | "stable" | "drifting" | "healing" | "healed" | "unknown";
  parser: string | null;
  total: number;
  failed: number;
  fail_rate: number;
  novel_shapes: number;
};

export type Stats = {
  events: number;
  matched: number;
  unmatched: number;
  verified: number;
  verify_failed: number;
  injection: number;
  replayed: number;
  bytes: number;
  eps: number;
  queue: number;
  uptime: number;
  lossless_score: number;
  batch_p50_ms: number;
  batch_p99_ms: number;
  parsers: number;
  sources: Record<string, SourceHealth>;
  healing: string[];
  workers: number;
};

export type Slot = {
  pos: number;
  type: string;
  name: string;
  ocsf: string | null;
  labeled_by: string;
  quoted: boolean;
  examples: string[];
};

export type TemplateT = {
  tid: string;
  delims: string[];
  words: (string | null)[];
  slots: Slot[];
  class_uid: number;
  count: number;
  fixed: Record<string, number | string>;
  examples: string[];
  display: string;
};

export type ParserSummary = {
  id: string;
  version: string;
  status: string;
  sha256: string;
  templates: number;
  source_hint: { vendor?: string; product?: string; format?: string };
  metrics: Record<string, number>;
  provenance: Record<string, any>;
  sources: string[];
  versions: { version: string; sha256: string; status: string; created: number }[];
};

export type Health = {
  ok: boolean;
  version: string;
  llm: { up: boolean; model?: string | null; url: string; blocked_cloud_models?: string[]; local_models?: string[] };
  egress: { air_gapped: boolean; reachable: string[]; llm_endpoint_local: boolean };
  signer: string;
  syslog_udp: number | null;
  workers: number;
};

export type Sample = { name: string; kind: "samples" | "drift" | "attack"; path: string; bytes: number; preview: string[] };

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) {
    super(msg);
    this.status = status;
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}

export const api = {
  get: <T,>(path: string) => fetch(path, { cache: "no-store" }).then(handle<T>),
  post: <T,>(path: string, body?: unknown) =>
    fetch(path, {
      method: "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(handle<T>),
  form: <T,>(path: string, fd: FormData) => fetch(path, { method: "POST", body: fd }).then(handle<T>),
  blob: (path: string, body?: unknown) =>
    fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new ApiError(r.status, r.statusText);
      return r.blob();
    }),
};

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function wsUrl() {
  if (typeof window === "undefined") return "";
  const { protocol, hostname, host, port } = window.location;
  const proto = protocol === "https:" ? "wss:" : "ws:";
  // Next dev server does not proxy websockets; talk to the API directly.
  return port === "3000" ? `${proto}//${hostname}:8000/ws/live` : `${proto}//${host}/ws/live`;
}

/** Poll a foundry job until it finishes. */
export async function waitJob(jobId: string, timeoutMs = 300_000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const j = await api.get<any>(`/api/foundry/${jobId}`);
    if (j.stage === "done" || j.stage === "error") return j;
    await new Promise((r) => setTimeout(r, 700));
  }
  throw new Error("timeout");
}
