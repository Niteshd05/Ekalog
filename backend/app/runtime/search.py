"""Typed OCSF filter execution (used by Ask EKALOG and the visual filter builder).

Fields and operators come from closed enums, values are bound parameters: the LLM (or a user)
can never produce SQL.
"""
from __future__ import annotations

import time

from ..foundry.prompts import ASK_FIELDS, ASK_OPS
from .store import EventStore, ip_in_cidr

_NUMERIC = {"src_port", "dst_port", "severity_id", "class_uid", "bytes_out", "bytes_in"}
_COLUMN = {"class_uid": "class_uid", "severity_id": "severity_id", "source": "source"}


def run_filter(store: EventStore, spec: dict, limit: int = 200) -> dict:
    where, params, post = [], [], []
    applied = []
    for f in spec.get("filters", [])[:10]:
        field, op, value = f.get("field"), f.get("op"), f.get("value")
        if field not in ASK_FIELDS or op not in ASK_OPS:
            continue
        applied.append({"field": field, "op": op, "value": value})
        path = ASK_FIELDS[field]
        col = _COLUMN.get(field) or f"json_extract(body, '$.{path}')"
        if field == "injection":
            col, value, op = "injection", 1 if str(value).lower() in ("1", "true", "yes") else 0, "eq"
        elif field in _NUMERIC:
            try:
                value = int(float(value))
            except (TypeError, ValueError):
                continue
        if op == "in_cidr":
            post.append((path, str(value)))
            where.append(f"{col} IS NOT NULL")
            continue
        sql_op = {"eq": "=", "neq": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}.get(op)
        if sql_op:
            if isinstance(value, str) and op in ("eq", "neq"):
                where.append(f"LOWER({col}) {sql_op} LOWER(?)")
            else:
                where.append(f"{col} {sql_op} ?")
            params.append(value)
        elif op == "contains":
            where.append(f"{col} LIKE ?")
            params.append(f"%{value}%")
        elif op == "starts_with":
            where.append(f"{col} LIKE ?")
            params.append(f"{value}%")
    minutes = int(spec.get("minutes") or 0)
    if minutes > 0:
        where.append("json_extract(body, '$.metadata.logged_time') >= ?")
        params.append(int((time.time() - minutes * 60) * 1000))
    t0 = time.perf_counter()
    rows = store.query(" AND ".join(where), tuple(params), limit=limit * (5 if post else 1))
    if post:
        from ..core.ocsf import get_path
        rows = [r for r in rows if all(ip_in_cidr(str(get_path(r, p) or ""), c) for p, c in post)][:limit]
    return {"filters": applied, "minutes": minutes, "count": len(rows), "events": rows,
            "ms": round((time.perf_counter() - t0) * 1000, 1)}
