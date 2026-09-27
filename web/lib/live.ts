"use client";
// Single WebSocket, single store. The server batches everything into one frame per tick (10 Hz),
// and we apply each frame as ONE state update, so React renders at most 10x/s no matter the EPS.
import { useSyncExternalStore } from "react";
import type { SlimEvent, Stats } from "./api";
import { wsUrl } from "./api";

export type FoundryMsg = { job_id: string; stage: string; kind: string; source: string; t: number; [k: string]: any };
export type JobState = { msgs: FoundryMsg[]; tokens: string; kind: string; source: string; stage: string };
export type Toast = { id: number; tone: "info" | "ok" | "warn" | "danger"; title: string; body?: string; href?: string };
export type DriftMsg = { source: string; parser?: string; state: string; ts?: number; [k: string]: any };
export type GuardMsg = { id: number; source: string; score: number; indicators: string[]; ts?: number };

export type LiveState = {
  connected: boolean;
  stats: Stats | null;
  events: (SlimEvent & { _at: number })[];
  jobs: Record<string, JobState>;
  drift: DriftMsg[];
  guard: GuardMsg[];
  eps: { t: number; eps: number; failed: number }[];
  toasts: Toast[];
};

const initial: LiveState = { connected: false, stats: null, events: [], jobs: {}, drift: [], guard: [], eps: [], toasts: [] };
let state: LiveState = initial;
const listeners = new Set<() => void>();

function commit(next: LiveState) {
  state = next;
  listeners.forEach((l) => l());
}

export function getLive() {
  return state;
}

export function useLive<T>(sel: (s: LiveState) => T): T {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => sel(state),
    () => sel(initial),
  );
}

let toastId = 1;
let lastGuardToast = 0;
export function toast(t: Omit<Toast, "id">, ttl = 6000) {
  const id = toastId++;
  commit({ ...state, toasts: [...state.toasts.slice(-4), { ...t, id }] });
  setTimeout(() => dismissToast(id), ttl);
}
export function dismissToast(id: number) {
  commit({ ...state, toasts: state.toasts.filter((x) => x.id !== id) });
}

// ------------------------------------------------------------------ frame handling
function applyFrame(frame: { type: string; payload: any[] }) {
  if (frame.type !== "batch") return;
  let next = { ...state };
  const newToasts: Omit<Toast, "id">[] = [];
  for (const m of frame.payload) {
    switch (m.type) {
      case "stats": {
        next.stats = m.payload;
        const last = next.eps[next.eps.length - 1];
        const now = Date.now();
        if (!last || now - last.t >= 1000) {
          const failed = Object.values(m.payload.sources || {}).reduce(
            (a: number, s: any) => a + (s.fail_rate > 0 ? s.fail_rate : 0), 0) as number;
          next.eps = [...next.eps.slice(-119), { t: now, eps: m.payload.eps, failed }];
        }
        break;
      }
      case "events": {
        const at = Date.now();
        const evs = (m.payload as SlimEvent[]).map((e) => ({ ...e, _at: at })).reverse();
        next.events = [...evs, ...next.events].slice(0, 200);
        break;
      }
      case "foundry": {
        const p = m.payload as FoundryMsg;
        const prev = next.jobs[p.job_id] ?? { msgs: [], tokens: "", kind: p.kind, source: p.source, stage: "queued" };
        const job: JobState =
          p.stage === "llm_tokens"
            ? { ...prev, tokens: (prev.tokens + p.text).slice(-12000) }
            : { ...prev, msgs: [...prev.msgs, p], stage: p.stage };
        next.jobs = { ...next.jobs, [p.job_id]: job };
        if (p.stage === "done" && p.kind === "onboard")
          newToasts.push({ tone: "ok", title: `Parser ready: ${p.parser_id} v${p.version}`,
            body: `Learned in ${p.elapsed}s · ${p.gates_passed ? "all gates passed" : "held for review"}`, href: "/parsers" });
        if (p.stage === "error") newToasts.push({ tone: "danger", title: "Onboarding failed", body: p.message });
        break;
      }
      case "drift": {
        const p = m.payload as DriftMsg;
        next.drift = [...next.drift.slice(-99), { ...p, ts: p.ts ?? Date.now() / 1000 }];
        if (p.state === "detected")
          newToasts.push({ tone: "warn", title: `Format drift on ${p.source}`,
            body: `${(p.fail_rate * 100).toFixed(1)}% of lines no longer match. Quarantining - nothing is dropped.`, href: "/drift" });
        if (p.state === "healed")
          newToasts.push({ tone: "ok", title: `Parser healed → v${p.version}`,
            body: `${p.replayed} quarantined events replayed in ${p.seconds}s.`, href: "/drift" });
        if (p.state === "cleared")
          newToasts.push({ tone: "info", title: `Drift alarm cleared on ${p.source}`,
            body: `No new line shapes - ${p.replayed} held lines replayed through the current parser.`, href: "/drift" });
        if (p.state === "failed") newToasts.push({ tone: "danger", title: `Auto-heal needs review (${p.source})`, href: "/drift" });
        break;
      }
      case "guard": {
        const p = m.payload as GuardMsg;
        next.guard = [...next.guard.slice(-199), { ...p, ts: Date.now() / 1000 }];
        if (Date.now() - lastGuardToast > 4000) {
          lastGuardToast = Date.now();
          newToasts.push({ tone: "danger", title: "Prompt injection detected in a log",
            body: `${p.indicators.join(", ")} · score ${p.score.toFixed(2)}`, href: "/guard" });
        }
        break;
      }
    }
  }
  commit(next);
  newToasts.forEach((t) => toast(t));
}

// ------------------------------------------------------------------ connection
let ws: WebSocket | null = null;
let started = false;
export function connectLive() {
  if (started || typeof window === "undefined") return;
  started = true;
  let backoff = 500;
  const open = () => {
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";
    const dec = new TextDecoder();
    ws.onopen = () => {
      backoff = 500;
      commit({ ...state, connected: true });
    };
    ws.onmessage = (ev) => {
      try {
        const text = typeof ev.data === "string" ? ev.data : dec.decode(ev.data);
        applyFrame(JSON.parse(text));
      } catch {}
    };
    ws.onclose = () => {
      commit({ ...state, connected: false });
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 8000);
    };
  };
  open();
}
