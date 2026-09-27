"""THE HOT PATH. Pure functions only: no LLM, no I/O, no network, no regex backtracking.

normalize_batch(items, router) -> (events, stats)
Every matched event carries enough information to rebuild its raw line byte-for-byte
(template literals + slot values + verbatim copies of non-reversible values), and the
rebuild is verified against the ingest SHA-256.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, NamedTuple

from ..core import ocsf
from ..core.lexer import tokenize
from ..core.template import ParserArtifact, Template
from ..core.timeparse import combine

_OBS_TYPE = {"ip": 2, "mac": 3}
_SEV_KIND = {"syslog_pri": "pri"}


class Item(NamedTuple):
    line: str
    source: str
    enc: str
    ingest_hash: str
    raw_ref: str
    received_ms: int


def sha256_hex(line: str, enc: str = "utf-8") -> str:
    return hashlib.sha256(line.encode(enc, "surrogateescape")).hexdigest()


class _Plan:
    __slots__ = ("steps", "class_uid", "cls", "fixed", "sev_slot", "sev_kind", "has_action")

    def __init__(self, t: Template):
        self.steps = []
        self.sev_slot = None
        self.sev_kind = "auto"
        self.has_action = False
        for p in sorted(t.slots):
            s = t.slots[p]
            path = s.ocsf
            if path == "time":
                kind = "time"
            elif path in ("severity",):
                kind = "sev"
                self.sev_slot, self.sev_kind = s.name, ("cef" if s.name == "cef_severity" else
                                                        "suricata" if s.type == "int" else "auto")
            elif path in ("action", "disposition"):
                kind = "action"
                self.has_action = True
            elif path is None:
                kind = "unmapped"
                if s.name == "syslog_pri" and self.sev_slot is None:
                    self.sev_slot, self.sev_kind = s.name, "pri"
            else:
                want = ocsf.FIELDS.get(path, "str")
                kind = "int" if want == "int" else "str"
            self.steps.append((p, s.name, path, kind))
        self.class_uid = t.class_uid
        self.cls = ocsf.CLASSES.get(t.class_uid, ocsf.CLASSES[0])
        self.fixed = t.fixed


def _plan(t: Template) -> _Plan:
    p = getattr(t, "_plan", None)
    if p is None:
        p = _Plan(t)
        t._plan = p
    return p


def normalize_matched(it: Item, words: list[str], t: Template, parser: ParserArtifact,
                      verify: bool = True) -> dict:
    plan = _plan(t)
    ev: dict = {}
    unmapped: dict = {}
    verbatim: dict = {}
    times: list[str] = []
    action_val = None
    sev_val = None
    observables = []
    for pos, name, path, kind in plan.steps:
        v = words[pos]
        if kind == "unmapped":
            unmapped[name] = v
            if name == plan.sev_slot:
                sev_val = v
        elif kind == "str":
            ocsf.set_path(ev, path, v)
            ot = _OBS_TYPE.get(ocsf.FIELDS.get(path, ""))
            if ot and v:
                observables.append({"name": path, "type_id": ot, "value": v})
        elif kind == "int":
            if v.isdigit() and (len(v) == 1 or v[0] != "0"):
                ocsf.set_path(ev, path, int(v))
            else:
                verbatim[name] = v
        elif kind == "time":
            times.append(v)
            verbatim[name] = v
        elif kind == "sev":
            unmapped[name] = v
            sev_val = v
        else:  # action
            ocsf.set_path(ev, path, v)
            action_val = v
    cls = plan.cls
    fixed = plan.fixed
    activity = fixed.get("activity_id", 0)
    disposition = fixed.get("disposition_id")
    if action_val is not None:
        a = ocsf.ACTION_MAP.get(action_val.lower())
        if a:
            activity, disposition = a
        elif activity == 0:
            activity = 99
    if plan.class_uid == 3002:
        activity = 1 if activity in (0, 6, 1) else activity
    if plan.class_uid == 2004:
        activity = 1
    sev = fixed.get("severity_id") or ocsf.severity_from(sev_val, plan.sev_kind)
    t_ms = combine(times) if times else None
    ev["class_uid"] = plan.class_uid
    ev["class_name"] = cls["name"]
    ev["category_uid"] = cls["category_uid"]
    ev["category_name"] = cls["category"]
    ev["activity_id"] = activity
    if plan.class_uid == 4001:
        ev["activity_name"] = ocsf.ACTIVITY_NAMES_4001.get(activity, "Other")
    ev["type_uid"] = plan.class_uid * 100 + activity
    ev["severity_id"] = sev
    ev["severity"] = ocsf.SEVERITIES.get(sev, "Unknown")
    if disposition is not None:
        ev["disposition_id"] = disposition
        ev.setdefault("disposition", ocsf.DISPOSITIONS.get(disposition, "Other"))
    if "status_id" in fixed:
        ev["status_id"] = fixed["status_id"]
    ev["time"] = t_ms or it.received_ms
    hint = parser.source_hint
    ev["metadata"] = {
        "version": ocsf.OCSF_VERSION,
        "product": {"vendor_name": hint.get("vendor", ""), "name": hint.get("product", "")},
        "logged_time": it.received_ms, "log_name": it.source,
        "profiles": ["security_control"] if disposition is not None else [],
    }
    if observables:
        ev["observables"] = observables
    if unmapped:
        ev["unmapped"] = unmapped
    ek = {
        "source": it.source, "raw_ref": it.raw_ref, "ingest_hash": "sha256:" + it.ingest_hash,
        "template_id": t.tid, "parser": {"id": parser.id, "version": parser.version, "sha256": parser.sha256[:16]},
        "status": "parsed",
    }
    if verbatim:
        ek["verbatim"] = verbatim
    if it.enc != "utf-8":
        ek["encoding"] = it.enc
    ev["ekalog"] = ek
    if verify:
        rebuilt = reconstruct(ev, t)
        ok = sha256_hex(rebuilt, it.enc) == it.ingest_hash
        ek["lossless"] = {"verified": ok, "method": "structural"}
    else:
        ek["lossless"] = {"verified": None, "method": "structural"}
    return ev


def normalize_unmatched(it: Item) -> dict:
    return {
        "class_uid": 0, "class_name": "Base Event", "category_uid": 0, "category_name": "Uncategorized",
        "activity_id": 0, "type_uid": 0, "severity_id": 0, "severity": "Unknown", "time": it.received_ms,
        "metadata": {"version": ocsf.OCSF_VERSION, "product": {"vendor_name": "", "name": ""},
                     "logged_time": it.received_ms, "log_name": it.source, "profiles": []},
        "raw_data": it.line,
        "ekalog": {"source": it.source, "raw_ref": it.raw_ref, "ingest_hash": "sha256:" + it.ingest_hash,
                   "status": "unmatched", "lossless": {"verified": True, "method": "raw"},
                   **({"encoding": it.enc} if it.enc != "utf-8" else {})},
    }


def reconstruct(ev: dict, t: Template) -> str:
    """Rebuild the original line from the normalized record alone."""
    ek = ev.get("ekalog", {})
    verbatim = ek.get("verbatim", {})
    unmapped = ev.get("unmapped", {})
    vals: dict[int, str] = {}
    for p, s in t.slots.items():
        if s.name in verbatim:
            vals[p] = verbatim[s.name]
        elif s.name in unmapped:
            vals[p] = unmapped[s.name]
        elif s.ocsf:
            v = ocsf.get_path(ev, s.ocsf)
            vals[p] = "" if v is None else str(v)
        else:
            vals[p] = ""
    return t.render(vals)


def normalize_batch(items: Iterable[Item], router, verify_every: int = 1) -> tuple[list[dict], dict]:
    events = []
    matched = verified = failed = 0
    for i, it in enumerate(items):
        words, delims = tokenize(it.line)
        t, parser = router.resolve(it.source, words, tuple(delims))
        if t is None:
            events.append(normalize_unmatched(it))
            continue
        matched += 1
        ev = normalize_matched(it, words, t, parser, verify=(i % verify_every == 0))
        v = ev["ekalog"]["lossless"]["verified"]
        if v is True:
            verified += 1
        elif v is False:
            failed += 1
        events.append(ev)
    return events, {"matched": matched, "unmatched": len(events) - matched, "verified": verified,
                    "verify_failed": failed}
