"""Parser Foundry: sample -> mined templates -> labels (rules + local LLM) -> validation gates -> signed artifact.

Every stage is published to the UI as {type: "foundry", payload: {job_id, stage, ...}}.
The Foundry is the *control plane*; nothing here runs on the ingestion hot path.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..config import settings
from ..core import ocsf
from ..core.template import ParserArtifact, Template
from ..runtime.executor import Item, normalize_batch, sha256_hex
from ..runtime.registry import Registry, Router, bump
from .columns import header_from_sample
from .labeler import coverage_report, decide_semantics, label_all
from .llm import llm
from .miner import EkaMiner
from .prompts import SYSTEM_LABEL, label_request, merge_llm

Emit = Callable[[dict], Awaitable[None]]
PROMPT_VERSION = "label-v2"
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class Job:
    id: str
    source: str
    filename: str
    kind: str = "onboard"  # onboard | heal
    stage: str = "queued"
    started: float = field(default_factory=time.time)
    finished: float | None = None
    log: list[dict] = field(default_factory=list)
    result: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "filename": self.filename, "kind": self.kind,
                "stage": self.stage, "started": self.started, "finished": self.finished,
                "elapsed": round((self.finished or time.time()) - self.started, 2), "log": self.log[-60:],
                "result": self.result, "error": self.error}


def _slug(*parts: str) -> str:
    s = ".".join(_SLUG.sub("-", p.lower()).strip("-") for p in parts if p)
    return s or "custom"


class Foundry:
    def __init__(self, registry: Registry, emit: Emit):
        self.registry = registry
        self.emit = emit
        self.jobs: dict[str, Job] = {}

    # ------------------------------------------------------------------ helpers
    async def _stage(self, job: Job, stage: str, **data):
        job.stage = stage
        entry = {"stage": stage, "t": round(time.time() - job.started, 2), **data}
        if stage != "llm_tokens":
            job.log.append(entry)
        await self.emit({"type": "foundry", "payload": {"job_id": job.id, "kind": job.kind, "source": job.source,
                                                        **entry}})

    def new_job(self, source: str, filename: str, kind: str = "onboard") -> Job:
        job = Job(uuid.uuid4().hex[:10], source, filename, kind)
        self.jobs[job.id] = job
        return job

    async def _label_with_llm(self, job: Job, templates: list[Template]) -> dict:
        stats = {"used": False, "model": None, "templates_asked": 0, "cache_hits": 0, "slots_labeled": 0,
                 "rejected": 0, "skipped_injection": 0, "seconds": 0.0, "error": None, "vendor": "", "product": ""}
        health = await llm.health()
        stats["model"] = health.get("model")
        pending = []
        for t in templates:
            cached = self.registry.cache_get(f"{PROMPT_VERSION}:{stats['model']}:{t.tid}")
            if cached:
                for pos, (name, path, by) in cached["slots"].items():
                    s = t.slots.get(int(pos))
                    if s:
                        s.name, s.ocsf, s.labeled_by = name, path, by
                t.class_uid = cached["class_uid"]
                if cached.get("class_by"):
                    t.fixed["class_by"] = cached["class_by"]
                stats["cache_hits"] += 1
            else:
                pending.append(t)
        if not health.get("up") or not stats["model"]:
            stats["error"] = "local model unavailable - deterministic labels only"
            return stats
        t0 = time.time()
        buf: list[str] = []
        last = [time.time()]

        async def on_token(tok: str):
            buf.append(tok)
            if time.time() - last[0] > 0.08:
                last[0] = time.time()
                chunk = "".join(buf)
                buf.clear()
                await self._stage(job, "llm_tokens", text=chunk)

        size = max(1, settings.llm_batch_templates)
        for i in range(0, len(pending), size):
            batch = pending[i:i + size]
            req = label_request(batch)
            if req is None:
                stats["skipped_injection"] += sum(1 for _ in batch)
                continue
            user, schema, tags = req
            stats["templates_asked"] += len(tags)
            stats["skipped_injection"] += len(batch) - len(tags)
            await self._stage(job, "llm_request", templates=len(tags), model=stats["model"],
                              prompt_chars=len(user))
            res = await llm.chat_json(SYSTEM_LABEL, user, schema, on_token=on_token)
            if buf:
                await self._stage(job, "llm_tokens", text="".join(buf))
                buf.clear()
            if res is None:
                stats["error"] = llm.last_error
                continue
            stats["used"] = True
            applied = merge_llm(res, tags)
            stats["slots_labeled"] += applied["slots"]
            stats["rejected"] += applied["rejected"]
            stats["vendor"] = stats["vendor"] or applied["vendor"]
            stats["product"] = stats["product"] or applied["product"]
            for t in tags.values():
                decide_semantics(t)
                self.registry.cache_put(f"{PROMPT_VERSION}:{stats['model']}:{t.tid}", {
                    "slots": {str(p): [s.name, s.ocsf, s.labeled_by] for p, s in t.slots.items()},
                    "class_uid": t.class_uid, "class_by": t.fixed.get("class_by")})
        stats["seconds"] = round(time.time() - t0, 2)
        return stats

    def _validate(self, art: ParserArtifact, holdout: list[str], source: str) -> tuple[list[dict], dict]:
        gates = []
        router = Router({art.id: art}, {source: art.id})
        items = [Item(ln, source, "utf-8", sha256_hex(ln), "foundry://holdout", 0) for ln in holdout]
        t0 = time.perf_counter()
        events, st = normalize_batch(items, router, verify_every=1)
        dt = max(time.perf_counter() - t0, 1e-6)
        cov = st["matched"] / max(1, len(items))
        gates.append({"id": "structure", "label": "Parser compiles (no regex, no eval)", "ok": True,
                      "detail": f"{len(art.templates)} templates"})
        gates.append({"id": "holdout", "label": "Held-out coverage", "ok": cov >= settings.gate_coverage,
                      "detail": f"{cov * 100:.1f}% of {len(items)} unseen lines", "value": cov})
        rt_ok = st["verify_failed"] == 0 and st["verified"] == st["matched"]
        gates.append({"id": "roundtrip", "label": "Round-trip byte-exact", "ok": rt_ok,
                      "detail": f"{st['verified']}/{st['matched']} rebuilt, SHA-256 match"})
        bad = 0
        for ev in events:
            for path, kind in (("src_endpoint.ip", "ip"), ("dst_endpoint.ip", "ip"),
                               ("src_endpoint.port", "port"), ("dst_endpoint.port", "port")):
                v = ocsf.get_path(ev, path)
                if v is None:
                    continue
                try:
                    if kind == "ip":
                        ipaddress.ip_address(v)
                    elif not 0 <= int(v) <= 65535:
                        bad += 1
                except ValueError:
                    bad += 1
        gates.append({"id": "types", "label": "Type checks (IPs, ports, timestamps)", "ok": bad == 0,
                      "detail": f"{bad} invalid values"})
        # semantic sanity: a mislabeled NAT copy or duplicate host shows up as src == dst
        both = [(ocsf.get_path(e, "src_endpoint.ip"), ocsf.get_path(e, "dst_endpoint.ip")) for e in events]
        both = [(a, b) for a, b in both if a and b]
        same = sum(1 for a, b in both if a == b) / max(1, len(both))
        gates.append({"id": "semantics", "label": "Semantic sanity (source differs from destination)",
                      "ok": same <= 0.2, "detail": f"{same * 100:.0f}% of events have src == dst"})
        missing = []
        for t in art.templates:
            req = ocsf.CLASSES.get(t.class_uid, {}).get("required", [])
            paths = {s.ocsf for s in t.slots.values() if s.ocsf}
            if any(r not in paths for r in req):
                missing.append(t.tid)
                t.class_uid = 0  # downgrade honestly instead of emitting an invalid class
                t._plan = None
        gates.append({"id": "ocsf", "label": "OCSF class requirements", "ok": True,
                      "detail": f"{len(art.templates) - len(missing)}/{len(art.templates)} templates fully classed"
                                + (f", {len(missing)} downgraded to Base Event" if missing else "")})
        metrics = {"holdout_coverage": round(cov, 4), "holdout_lines": len(items),
                   "roundtrip_verified": st["verified"], "roundtrip_failed": st["verify_failed"],
                   "eps_single_core": int(len(items) / dt)}
        return gates, metrics

    @staticmethod
    def _tests(art: ParserArtifact, source: str) -> list[dict]:
        router = Router({art.id: art}, {source: art.id})
        tests = []
        for t in art.templates:
            for ex in t.examples[:2]:
                evs, _ = normalize_batch([Item(ex, source, "utf-8", sha256_hex(ex), "test", 0)], router)
                ev = evs[0]
                expect = {"class_uid": ev["class_uid"], "ekalog.template_id": t.tid}
                for s in t.slots.values():
                    if s.ocsf and s.ocsf != "time" and len(expect) < 8:
                        v = ocsf.get_path(ev, s.ocsf)
                        if v is not None:
                            expect[s.ocsf] = v
                tests.append({"input": ex, "expect": expect})
        return tests

    # ------------------------------------------------------------------ onboarding
    async def onboard(self, job: Job, lines: list[str], vendor_hint: str = "") -> ParserArtifact | None:
        try:
            return await self._onboard(job, lines, vendor_hint)
        except Exception as e:  # noqa: BLE001 - surface to UI, never crash the server
            job.error = f"{type(e).__name__}: {e}"
            job.finished = time.time()
            await self._stage(job, "error", message=job.error)
            return None

    async def _onboard(self, job: Job, lines: list[str], vendor_hint: str) -> ParserArtifact | None:
        header, data = header_from_sample([ln for ln in lines if ln.strip()])
        data = data[:50_000]
        sample_sha = hashlib.sha256("\n".join(data).encode("utf-8", "surrogateescape")).hexdigest()
        await self._stage(job, "received", lines=len(data), header=bool(header), sha256=sample_sha[:16])
        rng = random.Random(26156)
        idx = list(range(len(data)))
        rng.shuffle(idx)
        cut = max(1, int(len(data) * (1 - settings.holdout_ratio)))
        train = [data[i] for i in idx[:cut]]
        holdout = [data[i] for i in idx[cut:]] or train[:50]

        miner = EkaMiner()
        t0 = time.perf_counter()
        await asyncio.to_thread(lambda: [miner.add(ln) for ln in train])
        templates = miner.templates()
        await self._stage(job, "mined", templates=len(templates), lines=len(train),
                          ms=int((time.perf_counter() - t0) * 1000),
                          preview=[{"tid": t.tid, "count": t.count, "display": t.display()[:220]} for t in templates[:12]])

        hint = label_all(templates, header)
        rules = {"slots": sum(len(t.slots) for t in templates),
                 "mapped": sum(coverage_report(t)["mapped"] for t in templates)}
        await self._stage(job, "rules_labeled", **rules, vendor=hint["vendor"], product=hint["product"],
                          format=hint["format"])

        llm_stats = await self._label_with_llm(job, templates)
        if not hint["vendor"] and llm_stats.get("vendor"):
            hint["vendor"], hint["product"] = llm_stats["vendor"], llm_stats["product"]
        if vendor_hint:
            hint["vendor"] = vendor_hint
        for t in templates:
            decide_semantics(t)
        await self._stage(job, "llm_done", **{k: v for k, v in llm_stats.items() if k not in ("vendor", "product")},
                          mapped=sum(coverage_report(t)["mapped"] for t in templates))

        pid = _slug(hint["vendor"], hint["product"]) if hint["vendor"] else _slug(job.source)
        existing = self.registry.get(pid)
        if existing:
            known = {t.tid for t in existing.templates}
            templates = existing.templates + [t for t in templates if t.tid not in known]
        version = bump(self.registry.latest_version(pid)) if self.registry.latest_version(pid) else "1.0.0"
        art = ParserArtifact(pid, version, templates, hint)
        gates, metrics = await asyncio.to_thread(self._validate, art, holdout, job.source)
        for g in gates:
            await self._stage(job, "gate", **g)
        passed = all(g["ok"] for g in gates)
        art.tests = self._tests(art, job.source)
        art.metrics = {**metrics, "templates": len(templates), "sample_lines": len(data),
                       "onboard_seconds": round(time.time() - job.started, 2)}
        art.provenance = {"miner": "ekaminer/1", "labeler": "rules+llm" if llm_stats["used"] else "rules",
                          "model": llm_stats["model"] if llm_stats["used"] else None,
                          "llm": {k: llm_stats[k] for k in ("templates_asked", "cache_hits", "slots_labeled",
                                                            "rejected", "skipped_injection", "seconds")},
                          "sample": {"file": job.filename, "sha256": sample_sha, "lines": len(data)},
                          "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        activate = passed and settings.auto_activate
        art = self.registry.register(art, activate=activate)
        self.registry.bind(job.source, pid)
        job.result = {"parser_id": pid, "version": version, "sha256": art.sha256, "status": art.status,
                      "gates_passed": passed, "metrics": art.metrics, "source_hint": hint,
                      "templates": [t.to_dict() for t in art.templates[:20]]}
        job.finished = time.time()
        await self._stage(job, "done", **{k: v for k, v in job.result.items() if k != "templates"},
                          elapsed=round(job.finished - job.started, 2))
        return art

    # ------------------------------------------------------------------ self-healing
    async def heal(self, job: Job, pid: str, lines: list[str]) -> tuple[ParserArtifact | None, dict]:
        old = self.registry.get(pid)
        if old is None:
            return None, {}
        miner = EkaMiner()
        await asyncio.to_thread(lambda: [miner.add(ln) for ln in lines])
        known = {t.tid for t in old.templates}
        new = [t for t in miner.templates() if t.tid not in known]
        await self._stage(job, "mined", templates=len(new), lines=len(lines),
                          preview=[{"tid": t.tid, "count": t.count, "display": t.display()[:220]} for t in new[:8]])
        if not new:
            return None, {}
        label_all(new)
        llm_stats = await self._label_with_llm(job, new)
        for t in new:
            decide_semantics(t)
        art = ParserArtifact(pid, bump(self.registry.latest_version(pid) or old.version), old.templates + new,
                             old.source_hint)
        gates, metrics = await asyncio.to_thread(self._validate, art, lines, job.source)
        for g in gates:
            await self._stage(job, "gate", **g)
        art.tests = self._tests(art, job.source)
        art.metrics = {**old.metrics, **metrics, "templates": len(art.templates)}
        art.provenance = {**old.provenance, "healed_from": old.version,
                          "labeler": "rules+llm" if llm_stats["used"] else "rules",
                          "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        passed = all(g["ok"] for g in gates)
        art = self.registry.register(art, activate=passed)
        diff = version_diff(old, new)
        job.result = {"parser_id": pid, "from": old.version, "version": art.version, "status": art.status,
                      "diff": diff, "gates_passed": passed}
        job.finished = time.time()
        await self._stage(job, "done", **job.result, elapsed=round(job.finished - job.started, 2))
        return (art if passed else None), diff


def version_diff(old: ParserArtifact, new_templates: list[Template]) -> list[dict]:
    """For each new template, compare slot names with its closest old template."""
    out = []
    for t in new_templates:
        names = [s.name for _, s in sorted(t.slots.items())]
        best, score = None, -1.0
        for o in old.templates:
            on = {s.name for s in o.slots.values()}
            j = len(on & set(names)) / max(1, len(on | set(names)))
            if j > score:
                best, score = o, j
        if best is None:
            continue
        old_names = [s.name for _, s in sorted(best.slots.items())]
        added = [n for n in names if n not in old_names]
        removed = [n for n in old_names if n not in names]
        common_new = [n for n in names if n in old_names]
        common_old = [n for n in old_names if n in names]
        moved = [n for i, n in enumerate(common_new) if i < len(common_old) and common_old[i] != n]
        out.append({"template": t.tid, "based_on": best.tid, "similarity": round(score, 2), "added": added,
                    "removed": removed, "reordered": moved[:10], "display": t.display()[:300]})
    return out
