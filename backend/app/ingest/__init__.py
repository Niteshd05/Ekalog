"""Ingest adapters: UDP syslog listener and a deterministic file replay driver (demo + load tests)."""
from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from ..runtime.pipeline import Pipeline


class SyslogUDP(asyncio.DatagramProtocol):
    """One datagram = one event. Embedded CR/LF are kept (log-forgery evidence), only the trailer is stripped."""

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.received = 0
        self.dropped = 0

    def datagram_received(self, data: bytes, addr):
        self.received += 1
        if not self.pipeline.submit_nowait(data.rstrip(b"\r\n"), f"udp:{addr[0]}"):
            self.dropped += 1


class ReplayManager:
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.tasks: dict[str, dict] = {}

    def start(self, path: Path, source: str, eps: float, loop: bool = False, limit: int | None = None) -> str:
        rid = uuid.uuid4().hex[:8]
        info = {"id": rid, "file": path.name, "source": source, "eps": eps, "sent": 0, "loop": loop,
                "running": True, "started": time.time()}
        info["task"] = asyncio.create_task(self._run(path, source, eps, loop, limit, info))
        self.tasks[rid] = info
        return rid

    async def _run(self, path: Path, source: str, eps: float, loop: bool, limit: int | None, info: dict):
        raw = path.read_bytes().split(b"\n")
        # CRLF files: the trailing \r is line framing, not content (embedded \r stays: forgery evidence)
        lines = [ln[:-1] if ln.endswith(b"\r") else ln for ln in raw if ln and not ln.startswith(b"#")]
        if limit:
            lines = lines[:limit]
        tick = 0.05
        per_tick = max(1, int(eps * tick))
        try:
            while True:
                i = 0
                t_next = time.monotonic()
                while i < len(lines):
                    chunk = lines[i:i + per_tick]
                    for ln in chunk:
                        await self.pipeline.submit(ln, source)
                    i += per_tick
                    info["sent"] += len(chunk)
                    t_next += tick
                    await asyncio.sleep(max(0, t_next - time.monotonic()))
                if not loop:
                    break
        finally:
            info["running"] = False

    def stop(self, rid: str | None = None):
        for k, info in list(self.tasks.items()):
            if rid in (None, k) and info["running"]:
                info["task"].cancel()
                info["running"] = False

    def list(self) -> list[dict]:
        return [{k: v for k, v in i.items() if k != "task"} for i in self.tasks.values()][-20:]
