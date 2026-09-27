"""Templates and parser artifacts.

A Template is literal words + typed slots over a fixed delimiter sequence. Matching is
a dict lookup plus literal comparison (no regex backtracking), and
``render(slot_values) == original_line`` by construction.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

import orjson

from .lexer import tokenize

_TYPE_REGEX = {
    "ipv4": r"\d{1,3}(?:\.\d{1,3}){3}",
    "int": r"[+-]?\d+",
    "float": r"[+-]?\d+\.\d+",
    "epoch": r"\d+(?:\.\d+)?",
}
_GROK = {"ipv4": "IPV4", "ipv6": "IPV6", "int": "INT", "float": "NUMBER", "mac": "MAC"}


@dataclass
class Slot:
    pos: int
    type: str
    name: str = ""
    ocsf: str | None = None
    labeled_by: str = "none"  # rule | llm | none
    quoted: bool = False
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"pos": self.pos, "type": self.type, "name": self.name, "ocsf": self.ocsf,
                "labeled_by": self.labeled_by, "quoted": self.quoted, "examples": self.examples[:3]}

    @classmethod
    def from_dict(cls, d: dict) -> "Slot":
        return cls(d["pos"], d["type"], d.get("name", ""), d.get("ocsf"), d.get("labeled_by", "none"),
                   d.get("quoted", False), list(d.get("examples", [])))


@dataclass
class Template:
    tid: str
    delims: tuple[str, ...]
    words: tuple[str | None, ...]  # None marks a slot
    slots: dict[int, Slot]
    class_uid: int = 0
    count: int = 0
    fixed: dict[str, Any] = field(default_factory=dict)  # e.g. {"activity_id": 1, "severity_id": 1}
    examples: list[str] = field(default_factory=list)

    def __post_init__(self):
        self._literals = [(i, w) for i, w in enumerate(self.words) if w is not None]
        self._slot_pos = sorted(self.slots)

    # ---------- runtime ----------
    def match(self, words: list[str]) -> bool:
        for i, w in self._literals:
            if words[i] != w:
                return False
        return True

    def render(self, values: dict[int, str]) -> str:
        out = []
        ws = self.words
        for i, d in enumerate(self.delims):
            w = ws[i]
            out.append(values[i] if w is None else w)
            out.append(d)
        last = len(self.delims)
        out.append(values[last] if ws[last] is None else ws[last])
        return "".join(out)

    @property
    def specificity(self) -> int:
        return len(self._literals)

    def display(self) -> str:
        """Human/LLM-facing form: literals and ⟨name:type⟩ markers."""
        vals = {p: f"<{s.name or 's' + str(p)}:{s.type}>" for p, s in self.slots.items()}
        return self.render(vals)

    # ---------- export (interop with Logstash / Vector / Fluent Bit) ----------
    def _slot_regex(self, s: Slot, next_delim: str | None) -> str:
        if s.quoted:
            body = r'(?:[^"\\]|\\.)*'
        elif s.type in _TYPE_REGEX:
            body = _TYPE_REGEX[s.type]
        else:
            stop = re.escape(next_delim[0]) if next_delim else ""
            body = rf"[^\s=,;|:/\[\](){{}}<>\"{stop}]*" if s.type not in ("ts", "ipv6", "mac") else r".+?"
        return body

    def to_regex(self, flavor: str = "python") -> str:
        parts = ["^"]
        for i, w in enumerate(self.words):
            if w is None:
                s = self.slots[i]
                nd = self.delims[i] if i < len(self.delims) else None
                name = s.name or f"s{i}"
                g = f"(?P<{name}>" if flavor == "python" else f"(?<{name}>"
                parts.append(g + self._slot_regex(s, nd) + ")")
            else:
                parts.append(re.escape(w))
            if i < len(self.delims):
                parts.append(re.escape(self.delims[i]))
        parts.append("$")
        return "".join(parts)

    def to_grok(self) -> str:
        parts = []
        for i, w in enumerate(self.words):
            if w is None:
                s = self.slots[i]
                name = s.name or f"s{i}"
                if s.type in _GROK and not s.quoted:
                    parts.append(f"%{{{_GROK[s.type]}:{name}}}")
                else:
                    nd = self.delims[i] if i < len(self.delims) else None
                    parts.append(f"(?<{name}>{self._slot_regex(s, nd)})")
            else:
                parts.append(re.escape(w))
            if i < len(self.delims):
                parts.append(re.escape(self.delims[i]))
        return "".join(parts)

    # ---------- serialization ----------
    def to_dict(self) -> dict:
        return {
            "tid": self.tid, "delims": list(self.delims), "words": list(self.words),
            "slots": [self.slots[p].to_dict() for p in self._slot_pos],
            "class_uid": self.class_uid, "count": self.count, "fixed": self.fixed,
            "examples": self.examples[:2], "display": self.display(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Template":
        slots = {s["pos"]: Slot.from_dict(s) for s in d["slots"]}
        return cls(d["tid"], tuple(d["delims"]), tuple(d["words"]), slots, d.get("class_uid", 0),
                   d.get("count", 0), dict(d.get("fixed", {})), list(d.get("examples", [])))


def template_hash(delims, words) -> str:
    h = hashlib.sha256(orjson.dumps([list(delims), list(words)])).hexdigest()
    return h[:12]


@dataclass
class ParserArtifact:
    id: str
    version: str
    templates: list[Template]
    source_hint: dict = field(default_factory=dict)
    tests: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    status: str = "active"  # active | pending_review | retired
    sha256: str = ""
    signature: str = ""

    def __post_init__(self):
        self.reindex()

    def reindex(self):
        idx: dict[tuple, list[Template]] = {}
        for t in self.templates:
            idx.setdefault(t.delims, []).append(t)
        for lst in idx.values():
            lst.sort(key=lambda t: -t.specificity)
        self._index = idx
        self._by_tid = {t.tid: t for t in self.templates}

    def lookup(self, words: list[str], delims: tuple) -> Template | None:
        cands = self._index.get(delims)
        if cands:
            for t in cands:
                if t.match(words):
                    return t
        return None

    def parse_line(self, line: str) -> Template | None:
        words, delims = tokenize(line)
        return self.lookup(words, tuple(delims))

    def template(self, tid: str) -> Template | None:
        return self._by_tid.get(tid)

    def body(self) -> dict:
        return {
            "id": self.id, "version": self.version, "source_hint": self.source_hint,
            "templates": [t.to_dict() for t in self.templates], "tests": self.tests,
            "metrics": self.metrics, "provenance": self.provenance,
        }

    def compute_sha(self) -> str:
        self.sha256 = hashlib.sha256(orjson.dumps(self.body(), option=orjson.OPT_SORT_KEYS)).hexdigest()
        return self.sha256

    def to_dict(self) -> dict:
        d = self.body()
        d.update(status=self.status, sha256=self.sha256, signature=self.signature)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ParserArtifact":
        return cls(d["id"], d["version"], [Template.from_dict(t) for t in d["templates"]],
                   d.get("source_hint", {}), d.get("tests", []), d.get("metrics", {}),
                   d.get("provenance", {}), d.get("status", "active"), d.get("sha256", ""),
                   d.get("signature", ""))

    def export(self, flavor: str) -> str:
        lines = [f"# EKALOG parser {self.id} v{self.version} sha256:{self.sha256[:16]}"]
        if flavor == "grok":
            lines.append("filter {\n  grok {\n    match => { \"message\" => [")
            lines += [f'      "{t.to_grok()}",'.replace("\\", "\\\\") for t in self.templates]
            lines.append("    ] }\n  }\n}")
        elif flavor == "vrl":
            for t in self.templates:
                rx = t.to_regex("python").replace("'", "\\'")
                lines.append(f"parsed, err = parse_regex(.message, r'{rx}')\nif err == null {{ . = merge(., parsed) }}")
        else:
            lines += [t.to_regex("python") for t in self.templates]
        return "\n".join(lines) + "\n"
