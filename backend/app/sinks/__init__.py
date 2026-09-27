"""Output sinks. NDJSON is always on; OpenSearch / Splunk HEC / Parquet are enabled by config."""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import orjson

from ..config import settings


class NdjsonSink:
    name = "ndjson"

    def __init__(self, root: Path | None = None):
        self.root = root or (settings.state_dir / "sinks")
        self.sent = 0

    def write(self, events: list[dict]):
        path = self.root / f"ocsf-{time.strftime('%Y%m%d')}.ndjson"
        with open(path, "ab") as f:
            f.write(b"".join(orjson.dumps(e) + b"\n" for e in events))
        self.sent += len(events)


class OpenSearchSink:
    name = "opensearch"

    def __init__(self, url: str, index: str = "ekalog-ocsf"):
        self.url, self.index, self.sent, self.error = url.rstrip("/"), index, 0, None
        self.client = httpx.Client(timeout=10)

    def write(self, events: list[dict]):
        body = b"".join(b'{"index":{"_index":"' + self.index.encode() + b'"}}\n' + orjson.dumps(e) + b"\n"
                        for e in events)
        try:
            self.client.post(f"{self.url}/_bulk", content=body,
                             headers={"Content-Type": "application/x-ndjson"}).raise_for_status()
            self.sent += len(events)
        except httpx.HTTPError as e:
            self.error = str(e)[:200]


class SplunkHecSink:
    name = "splunk_hec"

    def __init__(self, url: str, token: str):
        self.url, self.sent, self.error = url.rstrip("/"), 0, None
        self.client = httpx.Client(timeout=10, headers={"Authorization": f"Splunk {token}"}, verify=False)

    def write(self, events: list[dict]):
        body = b"".join(orjson.dumps({"time": e.get("time", 0) / 1000, "sourcetype": "ocsf", "event": e})
                        for e in events)
        try:
            self.client.post(f"{self.url}/services/collector/event", content=body).raise_for_status()
            self.sent += len(events)
        except httpx.HTTPError as e:
            self.error = str(e)[:200]


def build_sinks() -> list:
    sinks: list = [NdjsonSink()]
    if os.environ.get("EKALOG_SINK_OPENSEARCH_URL"):
        sinks.append(OpenSearchSink(os.environ["EKALOG_SINK_OPENSEARCH_URL"]))
    if os.environ.get("EKALOG_SINK_SPLUNK_URL"):
        sinks.append(SplunkHecSink(os.environ["EKALOG_SINK_SPLUNK_URL"], os.environ.get("EKALOG_SINK_SPLUNK_TOKEN", "")))
    return sinks


def export_parquet(events: list[dict], path: Path) -> Path:
    """AI/ML-ready flat export: one row per event, OCSF paths flattened to columns."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    def flat(d, prefix="", out=None):
        out = {} if out is None else out
        for k, v in d.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                flat(v, key + ".", out)
            elif isinstance(v, list):
                out[key] = orjson.dumps(v).decode()
            else:
                out[key] = v
        return out

    rows = [flat(e) for e in events]
    cols = sorted({k for r in rows for k in r})
    data = {}
    for c in cols:
        vals = [r.get(c) for r in rows]
        kinds = {type(v) for v in vals if v is not None}
        if kinds and kinds <= {int} or kinds == {bool} or kinds <= {int, float} and float in kinds:
            data[c] = vals  # homogeneous numeric/bool column keeps its type
        else:
            data[c] = [None if v is None else str(v) for v in vals]
    table = pa.table(data)
    pq.write_table(table, path)
    return path
