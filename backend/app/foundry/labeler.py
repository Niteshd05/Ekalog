"""Deterministic pre-labeler: names slots and maps them to OCSF without any model.

Order of evidence (strongest first):
  1. explicit key (KV `key=`, JSON `"key":`, CEF extension) -> synonym dictionary
  2. structural position (syslog PRI / timestamp / hostname header, CEF header fields)
  3. local context (ip followed by /port, words like src/dst/from before the slot)
  4. ordering fallback (first unlabeled IPv4 -> src, second -> dst)
The LLM later fills or corrects only what these rules could not decide confidently.
"""
from __future__ import annotations

import re

from ..core import ocsf
from ..core.template import Template
from .columns import COLUMN_SYNONYMS, known_columns
from .miner import is_header_hostname, is_value_position

_SAFE_NAME = re.compile(r"[^a-z0-9_]+")
_ZEEK_CONN = re.compile(r"\d{10}\.\d{6}\tC[A-Za-z0-9]{15,18}\t")
_ASA_LEVEL = re.compile(r"%[A-Z]+-(\d)-\d+")
_CEF_HEADER = ["cef_version", "device_vendor", "device_product", "device_version", "signature_id", "event_name", "cef_severity"]
_SRC_WORDS = {"src", "source", "from", "orig", "client", "sender"}
_DST_WORDS = {"dst", "dest", "destination", "to", "resp", "server", "target"}
# interface-qualified addresses ("inside:10.1.2.3"): internal side initiates unless the message says inbound
_INTERNAL_IFACES = {"inside", "lan", "internal", "trust", "trusted", "private", "management", "mgmt"}
_IFACES = _INTERNAL_IFACES | {"outside", "wan", "external", "untrust", "untrusted", "public", "internet", "dmz"}

# vendor fingerprints: (predicate on literal text, vendor, product, format)
_FINGERPRINTS = [
    (lambda s: "%ASA-" in s, "Cisco", "ASA", "syslog-text"),
    (lambda s: "devname" in s and "logid" in s, "Fortinet", "FortiGate", "key-value"),
    (lambda s: "TRAFFIC" in s or "THREAT" in s, "Palo Alto Networks", "PAN-OS", "csv"),
    (lambda s: "filterlog" in s, "Netgate", "pfSense", "csv"),
    (lambda s: "event_type" in s and "flow_id" in s, "OISF", "Suricata", "json"),
    (lambda s: "CEF" in s, "", "", "cef"),
]


def safe_name(s: str) -> str:
    n = _SAFE_NAME.sub("_", s.lower()).strip("_")
    if not n or not n[0].isalpha():
        n = "f_" + n
    return n[:32]


def _prev_literal(t: Template, p: int, maxback: int = 6) -> tuple[str | None, int]:
    q = p - 1
    while q >= 0 and p - q <= maxback:
        w = t.words[q]
        if w is None:
            return None, q
        if w != "":
            return w, q
        q -= 1
    return None, -1


def fingerprint(t: Template) -> dict:
    lit = " ".join(w for w in t.words if w)
    for pred, vendor, product, fmt in _FINGERPRINTS:
        if pred(lit):
            if fmt == "cef":
                return {"vendor": "", "product": "", "format": "cef"}
            return {"vendor": vendor, "product": product, "format": fmt}
    if t.examples and _ZEEK_CONN.match(t.examples[0]):
        return {"vendor": "Zeek", "product": "Zeek conn.log", "format": "tsv"}
    if t.examples and t.examples[0].lstrip().startswith("{"):
        return {"vendor": "", "product": "", "format": "json"}
    if "\t" in "".join(t.delims):
        return {"vendor": "", "product": "", "format": "tsv"}
    return {"vendor": "", "product": "", "format": "syslog-text" if t.delims[:1] == ("<",) else "text"}


def column_names(t: Template, fp: dict, header: list[str] | None) -> dict[int, str]:
    """Map word positions to column names for CSV/TSV templates."""
    if header and len(header) == len(t.words):
        return dict(enumerate(header))
    first_comma = next((i for i, d in enumerate(t.delims) if d == ","), None)
    if first_comma is None:
        return {}
    cols = known_columns(fp.get("product", ""), t.words, first_comma)
    if not cols:
        return {}
    return {first_comma + k: c for k, c in enumerate(cols) if first_comma + k < len(t.words)}


def label_template(t: Template, colnames: dict[int, str] | None = None) -> None:
    """Mutates slots in place: name, ocsf, labeled_by; sets class_uid and fixed fields."""
    words, delims = t.words, t.delims
    used: set[str] = set()
    names: set[str] = set()
    cef_idx = None
    for i, w in enumerate(words):
        if w and w.endswith("CEF") and i + 1 < len(delims) and delims[i] == ":":
            cef_idx = i
            break

    def assign(s, name, path, by):
        base = safe_name(name)
        nm, k = base, 2
        while nm in names:
            nm, k = f"{base}_{k}", k + 1
        names.add(nm)
        s.name = nm
        if path and path != "time" and path in used:
            path = None
        if path and not ocsf.type_compatible(path, s.type):
            if path == "connection_info.protocol_num" and s.type in ("str", "text"):
                path = "connection_info.protocol_name" if "connection_info.protocol_name" not in used else None
            else:
                path = None
        s.ocsf = path
        if path:
            used.add(path)
        s.labeled_by = by

    ips_unlabeled = []
    for p in sorted(t.slots):
        s = t.slots[p]
        # 0. column schema (sample header or documented vendor layout)
        if colnames and p in colnames:
            col = colnames[p]
            if col.startswith("future_use"):
                assign(s, col, None, "rule-schema")
                continue
            nk = ocsf.norm_key(col)
            assign(s, col, COLUMN_SYNONYMS.get(nk) or ocsf.SYNONYMS.get(nk), "rule-schema")
            continue
        key, kq = _prev_literal(t, p)
        # 1. explicit key
        if key and is_value_position(words, delims, p):
            path = ocsf.SYNONYMS.get(ocsf.norm_key(key))
            assign(s, key, path, "rule-key")
            continue
        # 2. structural header positions
        if p == 1 and delims[0] == "<" and len(delims) > 1 and delims[1] == ">":
            assign(s, "syslog_pri", None, "rule-pos")
            continue
        if s.type == "ts" and p <= 3 and "time" not in used:
            assign(s, "event_time", "time", "rule-pos")
            continue
        if s.type == "epoch" and p == 0:
            assign(s, "event_time", "time", "rule-pos")
            continue
        prev = t.slots.get(p - 1)
        if prev and prev.type == "ts" and is_header_hostname(delims, p, p - 1):
            assign(s, "device_hostname", "device.hostname", "rule-pos")
            continue
        if cef_idx is not None and p > cef_idx:
            n_pipes = sum(1 for d in delims[cef_idx:p] if d == "|")
            if n_pipes <= 6 and (n_pipes > 0 or p == cef_idx + 1):
                nm = _CEF_HEADER[n_pipes]
                path = {"event_name": "status_detail", "signature_id": "finding_info.uid",
                        "cef_severity": "severity"}.get(nm)
                assign(s, nm, path, "rule-pos")
                continue
        # 3. local context: port directly after an ip slot
        if s.type == "int" and p >= 1 and delims[p - 1] in ("/", ":") and words[p - 1] is None \
                and t.slots.get(p - 1) and t.slots[p - 1].type in ("ipv4", "ipv6"):
            ip = t.slots[p - 1]
            side = "src" if (ip.ocsf or "").startswith("src") else "dst" if (ip.ocsf or "").startswith("dst") else None
            path = f"{side}_endpoint.port" if side else None
            by = "rule-iface" if ip.labeled_by == "rule-iface" else "rule-ctx"
            assign(s, (ip.name or "ip") + "_port", path, by)
            continue
        if s.type in ("ipv4", "ipv6") and p >= 1 and delims[p - 1] == "(":
            assign(s, "mapped_ip", None, "rule-iface")  # NAT-mapped copy, e.g. ASA "(203.0.113.5/443)"
            continue
        iface = words[p - 1] if s.type in ("ipv4", "ipv6") and p >= 1 and delims[p - 1] == ":" else None
        if iface and iface.lower() in _IFACES:
            side = None
            for w in reversed(words[max(0, p - 5):p - 1]):  # nearest explicit keyword wins
                lw = (w or "").lower()
                if lw in ("src", "source"):
                    side = "src"
                    break
                if lw in ("dst", "dest", "destination"):
                    side = "dst"
                    break
            if side is None:
                internal = iface.lower() in _INTERNAL_IFACES
                inbound = "inbound" in {w.lower() for w in words if w}
                side = "src" if internal != inbound else "dst"
            assign(s, f"{iface.lower()}_ip", f"{side}_endpoint.ip", "rule-iface")
            continue
        if s.type in ("ipv4", "ipv6"):
            ctx = []
            q = p - 1
            while q >= 0 and len(ctx) < 3:
                if words[q]:
                    ctx.append(words[q].lower())
                q -= 1
            if any(c in _SRC_WORDS for c in ctx):
                assign(s, (ctx[0] if ctx else "src") + "_ip", "src_endpoint.ip", "rule-ctx")
            elif any(c in _DST_WORDS for c in ctx):
                assign(s, (ctx[0] if ctx else "dst") + "_ip", "dst_endpoint.ip", "rule-ctx")
            else:
                ips_unlabeled.append(s)
                assign(s, ((ctx[0] + "_") if ctx else "") + "ip", None, "none")
            continue
        base = key if key and len(key) <= 24 else s.type
        assign(s, f"{base}_{s.type}" if base != s.type else f"{s.type}_{p}", None, "none")

    # 4. ordering fallback for IPs
    for s, side in zip(ips_unlabeled, ("src", "dst")):
        path = f"{side}_endpoint.ip"
        if path not in used:
            s.ocsf, s.labeled_by = path, "rule-order"
            used.add(path)
            nxt = t.slots.get(s.pos + 1)
            if nxt and nxt.type == "int" and delims[s.pos] in ("/", ":") and nxt.ocsf is None:
                nxt.ocsf, nxt.labeled_by = f"{side}_endpoint.port", "rule-order"
                used.add(nxt.ocsf)

    decide_semantics(t)


_PRIORITY = {"rule-schema": 0, "rule-key": 0, "rule-pos": 1, "rule-iface": 1, "llm": 2, "rule-ctx": 3, "rule-order": 4, "none": 5}


def enforce_unique_paths(t: Template) -> None:
    """Invariant required for losslessness: each OCSF path (except split 'time') is fed by one slot.
    On conflict the strongest evidence wins; losers keep their name and land in `unmapped`."""
    owner: dict[str, object] = {}
    for p in sorted(t.slots):
        s = t.slots[p]
        if not s.ocsf or s.ocsf == "time":
            continue
        cur = owner.get(s.ocsf)
        if cur is None:
            owner[s.ocsf] = s
        elif _PRIORITY.get(s.labeled_by, 5) < _PRIORITY.get(cur.labeled_by, 5):
            cur.ocsf = None
            owner[s.ocsf] = s
        else:
            s.ocsf = None


def decide_semantics(t: Template) -> None:
    """Class, fixed activity/disposition and severity from mapped paths + literal words."""
    enforce_unique_paths(t)
    t._plan = None
    paths = {s.ocsf for s in t.slots.values() if s.ocsf}
    lits = [w.lower() for w in t.words if w]
    litset = set(lits)
    if t.class_uid == 0 or t.fixed.get("class_by") != "llm":
        if "finding_info.title" in paths:
            cls = 2004
        elif "query.hostname" in paths:
            cls = 4003
        elif any(p.startswith("http_request") for p in paths):
            cls = 4002
        elif "user.name" in paths and litset & {"authentication", "login", "logon", "vpn", "tunnel", "ssl", "aaa", "assigned"}:
            cls = 3002
        elif "src_endpoint.ip" in paths and "dst_endpoint.ip" in paths:
            cls = 4001
        elif "user.name" in paths:
            cls = 3002
        else:
            cls = 0
        t.class_uid = cls
    fixed = {k: v for k, v in t.fixed.items() if k == "class_by"}
    for w in lits:
        if w in ocsf.ACTION_MAP and "action" not in paths and "disposition" not in paths:
            act, disp = ocsf.ACTION_MAP[w]
            fixed.setdefault("activity_id", act)
            fixed.setdefault("disposition_id", disp)
    for w in t.words:
        if w:
            m = _ASA_LEVEL.search(w)
            if m:
                fixed["severity_id"] = ocsf.severity_from(m.group(1))
    if "successful" in litset or "success" in litset:
        fixed["status_id"] = 1
    t.fixed = fixed


def label_all(templates: list[Template], header: list[str] | None = None) -> dict:
    """Label every template; returns the dominant vendor fingerprint."""
    votes: dict[tuple, int] = {}
    for t in templates:
        fp = fingerprint(t)
        label_template(t, column_names(t, fp, header))
        k = (fp["vendor"], fp["product"], fp["format"])
        votes[k] = votes.get(k, 0) + t.count
    (vendor, product, fmt) = max(votes, key=votes.get) if votes else ("", "", "text")
    if fmt == "cef" and templates and templates[0].examples:
        ex = templates[0].examples[0]
        parts = ex[ex.find("CEF:"):].split("|")
        if len(parts) > 2:
            vendor, product = parts[1][:40], parts[2][:40]
    return {"vendor": vendor, "product": product, "format": fmt}


def coverage_report(t: Template) -> dict:
    total = len(t.slots)
    mapped = sum(1 for s in t.slots.values() if s.ocsf)
    by = {}
    for s in t.slots.values():
        by[s.labeled_by] = by.get(s.labeled_by, 0) + 1
    return {"slots": total, "mapped": mapped, "by": by}
