"""EKALOG API: FastAPI + one WebSocket (/ws/live). Run: uvicorn app.main:app --port 8000"""
from __future__ import annotations

import asyncio
import hashlib
import os
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

import orjson
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, Response
from pydantic import BaseModel, Field

from .config import settings
from .core import crypto
from .foundry.llm import llm
from .foundry.prompts import ASK_FIELDS, ASK_OPS, SYSTEM_ASK, ask_schema, sandbox_view
from .foundry.service import Foundry
from .ingest import ReplayManager, SyslogUDP
from .packs import export_pack, import_pack
from .runtime.drift import DriftSentinel
from .runtime.executor import Item, normalize_batch, reconstruct, sha256_hex
from .runtime.hub import Hub
from .runtime.injection import scan
from .runtime.pipeline import Pipeline
from .runtime.registry import Registry
from .runtime.search import run_filter
from .runtime.store import EventStore, Vault
from .sinks import build_sinks, export_parquet

SAMPLES = settings.data_dir


class State:
    registry: Registry
    store: EventStore
    vault: Vault
    hub: Hub
    drift: DriftSentinel
    pipeline: Pipeline
    foundry: Foundry
    replay: ReplayManager
    udp: SyslogUDP | None = None
    egress: dict = {}


S = State()


async def egress_selftest() -> dict:
    """Honest air-gap check: try to open TCP connections to well-known public endpoints (no data sent)."""
    targets = [("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443)]
    reachable = []

    async def probe(host, port):
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)
            w.close()
            reachable.append(f"{host}:{port}")
        except (OSError, asyncio.TimeoutError):
            pass

    await asyncio.gather(*(probe(h, p) for h, p in targets))
    return {"air_gapped": not reachable, "reachable": reachable, "checked_at": time.time(),
            "llm_endpoint_local": True, "llm_url": llm.url}


@asynccontextmanager
async def lifespan(app: FastAPI):
    S.registry = Registry()
    S.store = EventStore()
    S.vault = Vault()
    S.hub = Hub()
    S.drift = DriftSentinel()
    S.pipeline = Pipeline(S.registry, S.store, S.vault, S.hub, S.drift, build_sinks())
    S.foundry = Foundry(S.registry, S.hub.emit)
    S.pipeline.foundry = S.foundry
    S.replay = ReplayManager(S.pipeline)
    S.hub.stats_fn = S.pipeline.stats
    tasks = [asyncio.create_task(S.pipeline.run()), asyncio.create_task(S.hub.run()),
             asyncio.create_task(_ticker())]
    transport = None
    if settings.syslog_enabled:
        try:
            S.udp = SyslogUDP(S.pipeline)
            transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: S.udp, local_addr=("0.0.0.0", settings.syslog_udp_port))
        except OSError:
            S.udp = None
    S.egress = await egress_selftest()
    yield
    for t in tasks:
        t.cancel()
    if transport:
        transport.close()


async def _ticker():
    while True:
        await asyncio.sleep(1)
        S.drift.tick()


app = FastAPI(title="EKALOG", version="1.0.0", default_response_class=ORJSONResponse, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ system
@app.get("/api/health")
async def health():
    return {"ok": True, "version": app.version, "llm": await llm.health(), "egress": S.egress,
            "signer": crypto.fingerprint(), "syslog_udp": settings.syslog_udp_port if S.udp else None,
            "demo": settings.demo, "workers": settings.workers}


@app.post("/api/health/egress")
async def recheck_egress():
    S.egress = await egress_selftest()
    return S.egress


@app.get("/api/stats")
async def stats():
    return {**S.pipeline.stats(), "store": S.store.counts(), "quarantine": S.store.quarantine_counts(),
            "sinks": [{"name": s.name, "sent": s.sent, "error": getattr(s, "error", None)} for s in S.pipeline.sinks]}


@app.post("/api/reset")
async def reset(parsers: bool = False):
    """Demo helper: clear events (and optionally parsers)."""
    S.replay.stop()
    S.store.db.executescript("DELETE FROM events; DELETE FROM quarantine; DELETE FROM ledger;")
    S.store.db.commit()
    S.store.batch_no, S.store.chain = 0, "0" * 64
    S.pipeline.recent.clear()
    S.pipeline.alerts.clear()
    for k in S.pipeline.totals:
        S.pipeline.totals[k] = 0
    S.drift.sources.clear()
    if parsers:
        S.registry.delete_all()
    return {"ok": True}


# ------------------------------------------------------------------ samples + onboarding
@app.get("/api/samples")
async def samples():
    out = []
    for sub in ("samples", "drift", "attack"):
        for p in sorted((SAMPLES / sub).glob("*")):
            with open(p, "rb") as f:
                head = f.read(4096).decode("utf-8", "replace").split("\n")
            out.append({"name": p.name, "kind": sub, "path": f"{sub}/{p.name}", "bytes": p.stat().st_size,
                        "preview": [h for h in head if h and not h.startswith("#")][:3]})
    return out


def _sample_path(rel: str) -> Path:
    p = (SAMPLES / rel).resolve()
    if SAMPLES.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, "sample not found")
    return p


def _lines(data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n") if ln.strip()]


@app.post("/api/sources/onboard")
async def onboard(file: UploadFile | None = File(None), source: str = Form(""), sample: str = Form(""),
                  vendor: str = Form("")):
    if file is not None:
        data, name = await file.read(), file.filename or "upload.log"
    elif sample:
        p = _sample_path(sample)
        data, name = p.read_bytes(), p.name
    else:
        raise HTTPException(400, "provide a file or a sample path")
    src = source or Path(name).stem
    job = S.foundry.new_job(src, name)
    asyncio.create_task(S.foundry.onboard(job, _lines(data), vendor))
    return {"job_id": job.id, "source": src}


@app.get("/api/foundry/jobs")
async def jobs():
    return [j.to_dict() for j in list(S.foundry.jobs.values())[-30:]][::-1]


@app.get("/api/foundry/{job_id}")
async def job(job_id: str):
    j = S.foundry.jobs.get(job_id)
    if not j:
        raise HTTPException(404)
    return j.to_dict()


# ------------------------------------------------------------------ parsers
@app.get("/api/parsers")
async def parsers():
    return S.registry.list()


@app.get("/api/parsers/{pid}")
async def parser(pid: str, version: str | None = None):
    a = S.registry.get(pid, version) or S.registry.get(pid, S.registry.latest_version(pid) or "")
    if not a:
        raise HTTPException(404)
    return {**a.to_dict(), "versions": S.registry.versions(pid),
            "sources": [s for s, p in S.registry.bindings.items() if p == pid]}


class VersionReq(BaseModel):
    version: str


@app.post("/api/parsers/{pid}/activate")
async def activate(pid: str, req: VersionReq):
    a = S.registry.activate(pid, req.version)
    if not a:
        raise HTTPException(404)
    return {"ok": True, "active": a.version}


@app.get("/api/parsers/{pid}/export")
async def export_parser(pid: str, flavor: str = "grok"):
    a = S.registry.get(pid)
    if not a:
        raise HTTPException(404)
    if flavor not in ("grok", "vrl", "regex"):
        raise HTTPException(400, "flavor must be grok|vrl|regex")
    return Response(a.export(flavor), media_type="text/plain")


# ------------------------------------------------------------------ ingest
class ReplayReq(BaseModel):
    sample: str
    source: str = ""
    eps: float = Field(500, gt=0, le=200_000)
    loop: bool = False
    limit: int | None = None


@app.post("/api/ingest/replay")
async def replay(req: ReplayReq):
    p = _sample_path(req.sample)
    rid = S.replay.start(p, req.source or p.stem, req.eps, req.loop, req.limit)
    return {"replay_id": rid}


@app.post("/api/ingest/stop")
async def stop(replay_id: str | None = None):
    S.replay.stop(replay_id)
    return {"ok": True}


@app.get("/api/ingest/replays")
async def replays():
    return S.replay.list()


class PushReq(BaseModel):
    source: str
    lines: list[str] = Field(max_length=100_000)


@app.post("/api/ingest/push")
async def push(req: PushReq):
    for ln in req.lines:
        await S.pipeline.submit(ln, req.source)
    return {"accepted": len(req.lines)}


# ------------------------------------------------------------------ events + lossless vault
@app.get("/api/events")
async def events(limit: int = 100, source: str | None = None, class_uid: int | None = None,
                 injection: bool | None = None, status: str | None = None):
    where, params = [], []
    if source:
        where.append("source=?"); params.append(source)
    if class_uid is not None:
        where.append("class_uid=?"); params.append(class_uid)
    if injection is not None:
        where.append("injection=?"); params.append(int(injection))
    if status:
        where.append("status=?"); params.append(status)
    return S.store.query(" AND ".join(where), tuple(params), min(limit, 1000))


@app.get("/api/events/{eid}")
async def event(eid: int):
    e = S.store.get(eid)
    if not e:
        raise HTTPException(404)
    return e


@app.get("/api/events/{eid}/reconstruct")
async def reconstruct_event(eid: int):
    """Rebuild the raw line from the normalized record ALONE, then compare with the vault copy."""
    e = S.store.get(eid)
    if not e:
        raise HTTPException(404)
    ek = e["ekalog"]
    enc = ek.get("encoding", "utf-8")
    raw_bytes = S.vault.read(ek["raw_ref"]) or b""
    raw = raw_bytes.decode(enc, "surrogateescape")
    t0 = time.perf_counter()
    if ek.get("status") == "parsed":
        p = ek["parser"]
        art = S.registry.get(p["id"], p["version"])
        t = art.template(ek["template_id"]) if art else None
        rebuilt = reconstruct(e, t) if t else ""
        method = "structural (template + slot values + verbatim)"
        template = t.display() if t else None
    else:
        rebuilt, method, template = e.get("raw_data", ""), "raw_data (unmatched line kept verbatim)", None
    us = (time.perf_counter() - t0) * 1e6
    h_rebuilt = sha256_hex(rebuilt, enc)
    h_ingest = ek["ingest_hash"].removeprefix("sha256:")
    h_vault = hashlib.sha256(raw_bytes).hexdigest()
    diff = []
    if rebuilt != raw:
        for i, (a, b) in enumerate(zip(rebuilt, raw)):
            if a != b:
                diff.append({"offset": i, "rebuilt": rebuilt[i:i + 20], "raw": raw[i:i + 20]})
                break
    used_fields = sorted(k for k in e if k not in ("ekalog", "metadata", "unmapped", "raw_data", "id"))
    return {"id": eid, "raw": raw, "rebuilt": rebuilt, "match": h_rebuilt == h_ingest,
            "vault_match": h_vault == h_ingest, "sha256_ingest": h_ingest, "sha256_rebuilt": h_rebuilt,
            "sha256_vault": h_vault, "method": method, "template": template, "bytes": len(raw_bytes),
            "rebuild_us": round(us, 1), "diff": diff, "normalized_fields": used_fields,
            "verbatim_fields": list(ek.get("verbatim", {})), "unmapped_fields": list(e.get("unmapped", {}))}


@app.get("/api/vault/verify")
async def vault_verify(n: int = 2000):
    """Batch proof: rebuild the last N events from their normalized records and compare hashes."""
    rows = S.store.query("status='parsed'", (), min(n, 20000))
    ok = fail = 0
    t0 = time.perf_counter()
    for e in rows:
        ek = e["ekalog"]
        art = S.registry.get(ek["parser"]["id"], ek["parser"]["version"])
        t = art.template(ek["template_id"]) if art else None
        if t and sha256_hex(reconstruct(e, t), ek.get("encoding", "utf-8")) == ek["ingest_hash"][7:]:
            ok += 1
        else:
            fail += 1
    return {"checked": len(rows), "verified": ok, "failed": fail, "ms": round((time.perf_counter() - t0) * 1000, 1),
            "ledger": S.store.verify_ledger()}


@app.get("/api/ledger/verify")
async def ledger_verify():
    return S.store.verify_ledger()


# ------------------------------------------------------------------ drift
@app.get("/api/drift")
async def drift():
    return {"sources": [{**h.to_dict(), "timeline": list(h.timeline)[-300:]} for h in S.drift.sources.values()],
            "alarms": list(S.drift.alarms)[-50:],
            "heal_jobs": [j.to_dict() for j in S.foundry.jobs.values() if j.kind == "heal"][-10:]}


@app.post("/api/drift/simulate")
async def drift_simulate(source: str = "fortigate", eps: float = 300):
    """Demo: stream FortiOS 7.x lines (new fields + reordering) into an existing FortiGate source."""
    rid = S.replay.start(_sample_path("drift/fortigate_v7.log"), source, eps)
    return {"replay_id": rid}


# ------------------------------------------------------------------ injection guard
class GuardReq(BaseModel):
    line: str = Field(max_length=20000)


@app.post("/api/guard/test")
async def guard_test(req: GuardReq):
    v = scan(req.line)
    return {**v.to_dict(), "line": req.line, "llm_view": sandbox_view(req.line),
            "llm_withheld": v.detected, "threshold": settings.injection_threshold,
            "reference": "arXiv:2607.24174 (Just Testing, Move Along, 2026); arXiv:2607.14493"}


@app.get("/api/guard/alerts")
async def guard_alerts():
    return list(S.pipeline.alerts)[-100:][::-1]


# ------------------------------------------------------------------ ask ekalog (NL -> typed filter)
class AskReq(BaseModel):
    question: str = Field(max_length=500)
    limit: int = 100


@app.post("/api/ask")
async def ask(req: AskReq):
    t0 = time.time()

    def validate(d: dict) -> dict:
        d["filters"] = [f for f in d.get("filters", []) if f.get("field") in ASK_FIELDS and f.get("op") in ASK_OPS]
        d["summary"] = str(d.get("summary", ""))[:200]
        return d

    spec = await llm.chat_json(SYSTEM_ASK, f"Question: {req.question}", ask_schema(), validate=validate,
                               num_predict=400)
    if spec is None:
        return {"ok": False, "error": "local model unavailable - use the filter builder", "fields": list(ASK_FIELDS),
                "ops": ASK_OPS}
    res = await asyncio.to_thread(run_filter, S.store, spec, req.limit)
    return {"ok": True, "summary": spec.get("summary"), **res, "llm_seconds": round(time.time() - t0, 2)}


class SearchReq(BaseModel):
    filters: list[dict] = []
    minutes: int = 0
    limit: int = 100


@app.post("/api/search")
async def search(req: SearchReq):
    return await asyncio.to_thread(run_filter, S.store, req.model_dump(), req.limit)


@app.get("/api/search/fields")
async def search_fields():
    return {"fields": ASK_FIELDS, "ops": ASK_OPS}


# ------------------------------------------------------------------ benchmark
@app.get("/api/bench")
async def bench(lines_per_source: int = 2000):
    return await asyncio.to_thread(_bench, lines_per_source)


def _bench(n: int) -> dict:
    router = S.registry.router
    results = []
    all_lat = []
    total_ev, total_s = 0, 0.0
    for p in sorted((SAMPLES / "samples").glob("*")):
        lines = [ln for ln in p.read_text(encoding="utf-8").split("\n") if ln and not ln.startswith("#")][:n]
        items = [Item(ln, p.stem, "utf-8", sha256_hex(ln), "bench", 0) for ln in lines]
        t0 = time.perf_counter()
        evs, st = normalize_batch(items, router, 1)
        dt = time.perf_counter() - t0
        for it in items[:300]:
            a = time.perf_counter()
            normalize_batch([it], router, 1)
            all_lat.append((time.perf_counter() - a) * 1e6)
        total_ev += len(items)
        total_s += dt
        results.append({"source": p.stem, "events": len(items), "eps": int(len(items) / dt), **st})
    all_lat.sort()
    eps = int(total_ev / total_s) if total_s else 0
    cores = os.cpu_count() or 1
    return {"single_core_eps": eps, "p50_us": round(all_lat[len(all_lat) // 2], 1) if all_lat else 0,
            "p99_us": round(all_lat[int(len(all_lat) * 0.99)], 1) if all_lat else 0,
            "per_source": results, "cpu_cores": cores,
            "projected_per_day_single_core": eps * 86400,
            "projected_per_day_all_cores": eps * 86400 * cores,
            "note": "Measured in-process, parse + OCSF map + full round-trip verification, no I/O. "
                    "Projection assumes linear scaling of the stateless workers."}


# ------------------------------------------------------------------ packs + exports
class PackReq(BaseModel):
    parsers: list[str] | None = None


@app.post("/api/packs/export")
async def pack_export(req: PackReq):
    data = export_pack(S.registry, req.parsers)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename=ekalog-{int(time.time())}.ekapack"})


@app.post("/api/packs/import")
async def pack_import(file: UploadFile = File(...), trust: bool = Form(False)):
    return import_pack(S.registry, await file.read(), trust_signer=trust)


@app.get("/api/export/parquet")
async def parquet(limit: int = 50000):
    evs = S.store.query("", (), min(limit, 200000))
    path = settings.state_dir / "sinks" / f"ocsf-{int(time.time())}.parquet"
    await asyncio.to_thread(export_parquet, evs, path)
    return Response(path.read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={path.name}"})


# ------------------------------------------------------------------ websocket
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await S.hub.connect(ws)
    try:
        await ws.send_bytes(orjson.dumps({"type": "hello", "ts": time.time(), "payload": {"version": app.version}}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        S.hub.disconnect(ws)
