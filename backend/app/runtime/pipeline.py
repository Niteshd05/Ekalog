"""Data plane orchestration: ingest queue -> vault (before parsing) -> pure normalize -> store/sinks/drift.

Scalability model: `normalize_batch` is a pure function over an immutable Router snapshot, so it
can run in N worker processes (EKALOG_WORKERS) or N containers behind a Bus (Redis Streams/Kafka)
with no shared state. This process owns only persistence and the UI hub.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor

from ..config import settings
from ..core.lexer import tokenize
from ..foundry.service import Foundry
from .drift import DriftSentinel
from .executor import Item, normalize_batch, sha256_hex
from .hub import Hub
from .injection import scan
from .registry import Registry, Router
from .store import EventStore, Vault

# ---- worker-process side (only used when EKALOG_WORKERS > 0) ----
_W_ROUTER: dict = {"key": None, "router": None}


def _worker_normalize(snapshot_key: str, snapshot: dict | None, items: list[tuple], verify_every: int):
    from ..core.template import ParserArtifact
    if _W_ROUTER["key"] != snapshot_key:
        active = {pid: ParserArtifact.from_dict(d) for pid, d in snapshot["active"].items()}
        _W_ROUTER.update(key=snapshot_key, router=Router(active, snapshot["bindings"]))
    return normalize_batch([Item(*i) for i in items], _W_ROUTER["router"], verify_every)


def decode(raw: bytes | str) -> tuple[str, str]:
    if isinstance(raw, str):
        return raw, "utf-8"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"  # bijective: every byte round-trips


class Pipeline:
    def __init__(self, registry: Registry, store: EventStore, vault: Vault, hub: Hub, drift: DriftSentinel,
                 sinks: list):
        self.registry, self.store, self.vault, self.hub, self.drift, self.sinks = registry, store, vault, hub, drift, sinks
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=200_000)
        self.foundry: Foundry | None = None
        self.recent: deque = deque(maxlen=settings.recent_events)
        self.alerts: deque = deque(maxlen=500)
        self.started = time.time()
        self.totals = {"events": 0, "matched": 0, "unmatched": 0, "verified": 0, "verify_failed": 0,
                       "injection": 0, "replayed": 0, "bytes": 0}
        self._eps = deque(maxlen=50)  # (t, n)
        self.lat_us: deque = deque(maxlen=400)
        self.healing: set[str] = set()
        self.pool = ProcessPoolExecutor(settings.workers) if settings.workers > 0 else None

    # ---------------------------------------------------------------- ingest API
    async def submit(self, raw: bytes | str, source: str):
        await self.queue.put((raw, source, int(time.time() * 1000)))

    def submit_nowait(self, raw: bytes | str, source: str) -> bool:
        try:
            self.queue.put_nowait((raw, source, int(time.time() * 1000)))
            return True
        except asyncio.QueueFull:
            return False

    # ---------------------------------------------------------------- main loop
    async def run(self):
        while True:
            first = await self.queue.get()
            batch = [first]
            deadline = time.monotonic() + settings.batch_linger_ms / 1000
            while len(batch) < settings.batch_size:
                try:
                    batch.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:
                    if time.monotonic() >= deadline:
                        break
                    await asyncio.sleep(0.005)
            try:
                await self._process(batch)
            except Exception as e:  # noqa: BLE001 - the data plane must never die
                await self.hub.emit({"type": "error", "payload": {"where": "pipeline", "error": repr(e)[:300]}})

    async def _process(self, batch: list[tuple], replay_rows: list[tuple] | None = None):
        t0 = time.perf_counter()
        if replay_rows is None:
            decoded = [decode(r) for r, _, _ in batch]
            refs = self.vault.append_many([ln.encode(enc, "surrogateescape") for ln, enc in decoded])
            items = [Item(ln, src, enc, sha256_hex(ln, enc), ref, ms)
                     for (ln, enc), ref, (_, src, ms) in zip(decoded, refs, batch)]
        else:  # replay from quarantine: already vaulted, keep original refs/hashes
            now = int(time.time() * 1000)
            items = [Item(line, src, enc, h.removeprefix("sha256:"), ref, now) for src, line, enc, ref, h in replay_rows]
        router = self.registry.router
        if self.pool:
            snap = {"active": {pid: a.to_dict() for pid, a in router.active.items()}, "bindings": router.bindings}
            key = "|".join(f"{p}:{a.sha256}" for p, a in sorted(router.active.items())) + str(len(router.bindings))
            events, st = await asyncio.get_running_loop().run_in_executor(
                self.pool, _worker_normalize, key, snap, [tuple(i) for i in items], settings.verify_every)
        else:
            events, st = await asyncio.to_thread(normalize_batch, items, router, settings.verify_every)
        self.registry.absorb_router_bindings(router)
        await asyncio.to_thread(self._persist, items, events, replay_rows is not None)
        dt = time.perf_counter() - t0
        self.lat_us.append(dt * 1e6)  # end-to-end batch time: vault + normalize + verify + store + sinks
        for k in ("matched", "unmatched", "verified", "verify_failed"):
            self.totals[k] += st[k]
        self.totals["events"] += len(events)
        self._eps.append((time.time(), len(events)))
        self.hub.push_events(events)
        await self._after(items, events)

    def _persist(self, items: list[Item], events: list[dict], replay: bool):
        first = self.store.assign_ids(len(events))
        q_rows = []
        for i, (it, ev) in enumerate(zip(items, events)):
            ev["id"] = first + i
            v = scan(it.line)
            if v.indicators:
                ev["ekalog"]["injection"] = v.to_dict()
                if v.detected:
                    self.totals["injection"] += 1
                    self.alerts.append({"id": ev["id"], "source": it.source, "time": ev.get("time"),
                                        "line": it.line[:2000], **v.to_dict()})
            if ev["ekalog"]["status"] == "unmatched" and not replay:
                q_rows.append((it.source, it.line, it.enc, it.raw_ref, "sha256:" + it.ingest_hash, time.time()))
            self.totals["bytes"] += len(it.line)
        self.store.insert(events)
        self.store.quarantine(q_rows)
        for s in self.sinks:
            try:
                s.write(events)
            except Exception:  # noqa: BLE001 - a sink outage must not stop ingestion
                pass
        self.recent.extend(events)

    async def _after(self, items: list[Item], events: list[dict]):
        per_source: dict[str, tuple[list, list, str | None]] = {}
        for it, ev in zip(items, events):
            fails, shapes, pid = per_source.setdefault(it.source, ([], [], None))
            bad = ev["ekalog"]["status"] == "unmatched"
            fails.append(bad)
            if bad:
                shapes.append(tuple(tokenize(it.line)[1])[:40])
        for src, (fails, shapes, _) in per_source.items():
            pid = self.registry.bindings.get(src)
            alarm = self.drift.observe(src, pid, fails, shapes)
            if alarm:
                await self.hub.emit({"type": "drift", "payload": alarm})
                if settings.drift_auto_heal and src not in self.healing:
                    self.healing.add(src)
                    asyncio.create_task(self._heal(src, pid))
        for ev in events:
            inj = ev["ekalog"].get("injection")
            if inj and inj.get("detected"):
                await self.hub.emit({"type": "guard", "payload": {"id": ev["id"], "source": ev["ekalog"]["source"],
                                                                  "score": inj["score"], "indicators": inj["indicators"]}})

    # ---------------------------------------------------------------- self-healing loop
    async def _heal(self, source: str, pid: str):
        try:
            for _ in range(40):  # wait until enough evidence is quarantined (never drops anything meanwhile)
                if len(self.store.quarantined(source, settings.drift_heal_min_lines)) >= settings.drift_heal_min_lines:
                    break
                await asyncio.sleep(0.25)
            self.drift.mark(source, "healing")
            rows = self.store.quarantined(source, 5000)
            await self.hub.emit({"type": "drift", "payload": {"source": source, "parser": pid, "state": "healing",
                                                              "quarantined": len(rows)}})
            job = self.foundry.new_job(source, f"quarantine:{source}", kind="heal")
            art, diff = await self.foundry.heal(job, pid, [r[1] for r in rows])
            if art is None and diff.get("no_change"):
                # transient: quarantined lines already match the active parser -> just replay them
                replayed = await self.replay_quarantine(source)
                self.drift.mark(source, "healed")
                await self.hub.emit({"type": "drift", "payload": {"source": source, "parser": pid, "state": "cleared",
                                                                  "replayed": replayed, "job_id": job.id}})
                return
            if art is None:
                self.drift.mark(source, "drifting")
                await self.hub.emit({"type": "drift", "payload": {"source": source, "parser": pid, "state": "failed",
                                                                  "job_id": job.id}})
                return
            replayed = await self.replay_quarantine(source)
            self.drift.mark(source, "healed")
            await self.hub.emit({"type": "drift", "payload": {
                "source": source, "parser": pid, "state": "healed", "version": art.version,
                "from": job.result.get("from"), "diff": diff, "replayed": replayed, "job_id": job.id,
                "seconds": round(time.time() - (self.drift.get(source).last_alarm or time.time()), 1)}})
        finally:
            self.healing.discard(source)

    async def replay_quarantine(self, source: str) -> int:
        total = 0
        while True:
            rows = self.store.quarantined(source, settings.batch_size)
            if not rows:
                break
            await self._process([], replay_rows=[(source, line, enc, ref, h) for _, line, enc, ref, h in rows])
            self.store.mark_replayed([r[0] for r in rows])
            total += len(rows)
        self.totals["replayed"] += total
        return total

    # ---------------------------------------------------------------- stats
    def eps(self) -> float:
        now = time.time()
        n = sum(c for t, c in self._eps if now - t <= 2.0)
        return n / 2.0

    def stats(self) -> dict:
        lat = sorted(self.lat_us)
        p = (lambda q: round(lat[min(len(lat) - 1, int(q * len(lat)))], 1) if lat else 0)
        t = self.totals
        loss = 1.0 if t["verified"] + t["verify_failed"] == 0 else t["verified"] / (t["verified"] + t["verify_failed"])
        return {
            **t, "eps": round(self.eps(), 1), "queue": self.queue.qsize(), "uptime": round(time.time() - self.started),
            "lossless_score": loss, "batch_p50_ms": round(p(0.5) / 1000, 2), "batch_p99_ms": round(p(0.99) / 1000, 2),
            "parsers": len(self.registry.active), "sources": {s: h.to_dict() for s, h in self.drift.sources.items()},
            "healing": sorted(self.healing), "workers": settings.workers,
        }
