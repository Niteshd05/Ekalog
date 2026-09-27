"""Drift Sentinel: per-source rolling parse health; alarms when a vendor silently changes format."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from ..config import settings


@dataclass
class SourceHealth:
    source: str
    window: deque = field(default_factory=lambda: deque(maxlen=settings.drift_window))
    total: int = 0
    failed: int = 0
    status: str = "learning"  # learning | stable | drifting | healing | healed | unknown
    parser: str | None = None
    last_alarm: float | None = None
    timeline: deque = field(default_factory=lambda: deque(maxlen=900))
    shapes: set = field(default_factory=set)
    _sec_total: int = 0
    _sec_fail: int = 0

    @property
    def fail_rate(self) -> float:
        return sum(self.window) / len(self.window) if self.window else 0.0

    def to_dict(self) -> dict:
        return {"source": self.source, "status": self.status, "parser": self.parser, "total": self.total,
                "failed": self.failed, "fail_rate": round(self.fail_rate, 4), "last_alarm": self.last_alarm,
                "novel_shapes": len(self.shapes)}


class DriftSentinel:
    def __init__(self):
        self.sources: dict[str, SourceHealth] = {}
        self.alarms: deque = deque(maxlen=200)

    def get(self, source: str) -> SourceHealth:
        h = self.sources.get(source)
        if h is None:
            h = self.sources[source] = SourceHealth(source)
        return h

    def observe(self, source: str, parser: str | None, results: list[bool], shapes: list[tuple]) -> dict | None:
        """results: True = parse failure. Returns an alarm dict when drift is detected."""
        h = self.get(source)
        if parser:
            h.parser = parser
        for r in results:
            h.window.append(1 if r else 0)
        h.total += len(results)
        nf = sum(results)
        h.failed += nf
        h._sec_total += len(results)
        h._sec_fail += nf
        for s in shapes[:50]:
            if len(h.shapes) < 1000:
                h.shapes.add(s)
        if h.status in ("healing",):
            return None
        rate = h.fail_rate
        if h.parser is None:
            h.status = "unknown" if rate > 0.5 and len(h.window) >= 20 else h.status
            return None
        if len(h.window) >= settings.drift_min_events and rate > settings.drift_fail_rate:
            if h.status != "drifting":
                h.status = "drifting"
                h.last_alarm = time.time()
                alarm = {"source": source, "parser": h.parser, "fail_rate": round(rate, 4),
                         "novel_shapes": len(h.shapes), "ts": h.last_alarm, "state": "detected"}
                self.alarms.append(alarm)
                return alarm
        elif h.status in ("learning", "healed") and len(h.window) >= settings.drift_min_events:
            h.status = "stable"
        return None

    def tick(self):
        """Called once per second: append a timeline point per source."""
        now = time.time()
        for h in self.sources.values():
            if h._sec_total or h.timeline:
                h.timeline.append((round(now, 1), h._sec_total, h._sec_fail, h.status))
            h._sec_total = h._sec_fail = 0

    def mark(self, source: str, status: str):
        h = self.get(source)
        h.status = status
        if status == "healed":
            h.window.clear()
            h.shapes.clear()
