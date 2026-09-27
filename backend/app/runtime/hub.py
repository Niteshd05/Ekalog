"""WebSocket hub: batches everything into one frame per tick (10 Hz) so the UI never renders per event."""
from __future__ import annotations

import asyncio
import time
from collections import deque

import orjson
from fastapi import WebSocket

from ..config import settings


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.notices: deque = deque(maxlen=2000)
        self.events: deque = deque(maxlen=60)
        self.stats_fn = None

    async def emit(self, msg: dict):
        msg.setdefault("ts", time.time())
        self.notices.append(msg)

    def push_events(self, evs: list[dict]):
        self.events.extend(evs[-60:])

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def run(self):
        period = 1 / max(1, settings.ui_hz)
        while True:
            await asyncio.sleep(period)
            if not self.clients:
                self.notices.clear()
                self.events.clear()
                continue
            payload = []
            if self.stats_fn:
                payload.append({"type": "stats", "payload": self.stats_fn()})
            if self.events:
                evs = list(self.events)[-25:]
                self.events.clear()
                payload.append({"type": "events", "payload": [_slim(e) for e in evs]})
            while self.notices:
                payload.append(self.notices.popleft())
            frame = orjson.dumps({"type": "batch", "ts": time.time(), "payload": payload})
            dead = []
            for ws in list(self.clients):
                try:
                    await ws.send_bytes(frame)
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)


def _slim(e: dict) -> dict:
    ek = e.get("ekalog", {})
    return {
        "id": e.get("id"), "time": e.get("time"), "class_uid": e.get("class_uid"), "class_name": e.get("class_name"),
        "severity_id": e.get("severity_id"), "activity_id": e.get("activity_id"),
        "src": (e.get("src_endpoint") or {}).get("ip"), "dst": (e.get("dst_endpoint") or {}).get("ip"),
        "dst_port": (e.get("dst_endpoint") or {}).get("port"), "action": e.get("action") or e.get("disposition"),
        "vendor": e.get("metadata", {}).get("product", {}).get("name"), "source": ek.get("source"),
        "status": ek.get("status"), "verified": ek.get("lossless", {}).get("verified"),
        "injection": ek.get("injection", {}).get("detected", False),
        "title": (e.get("finding_info") or {}).get("title"),
        "user": (e.get("user") or {}).get("name"),
    }
