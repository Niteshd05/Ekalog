"""EkaMiner — Drain-style online template mining over the delimiter-preserving lexer.

1. Lines are grouped by their *exact* delimiter sequence (structure).
2. Inside a group, lines join the most similar cluster (masked-word similarity, wildcards
   count half) if similarity >= threshold; differing positions become slots.
3. Identical masked signatures hit a cache, so steady-state cost is O(1) per line.
4. Generalization rules turn values that happened to be constant in the sample
   (KV/JSON values, syslog hostnames, typed tokens, CSV columns) into slots, so a
   parser learned on one device works on its siblings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import settings
from ..core.lexer import VARIABLE_TYPES, mask, tokenize, word_type
from ..core.template import Slot, Template, template_hash

_RECORD_TYPE = re.compile(r"[A-Z][A-Z_]{2,}")


@dataclass
class _Cluster:
    delims: tuple[str, ...]
    tmpl: list[str | None]
    count: int = 0
    examples: list[str] = field(default_factory=list)
    values: dict[int, list[str]] = field(default_factory=dict)
    types: dict[int, set] = field(default_factory=dict)
    words0: list[str] | None = None

    def add(self, words: list[str], masked: tuple, line: str, max_ex: int):
        self.count += 1
        if self.words0 is None:
            self.words0 = list(words)
        if len(self.examples) < 3:
            self.examples.append(line)
        for p, m in enumerate(masked):
            t = self.tmpl[p]
            if t is not None and t != m:
                self.tmpl[p] = None
            vals = self.values.setdefault(p, [])
            w = words[p]
            if len(vals) < max_ex and w not in vals:
                vals.append(w)
            if w != "":
                self.types.setdefault(p, set()).add(word_type(w))


def _similarity(tmpl: list[str | None], masked: tuple) -> float:
    eq = wild = n = 0
    for t, m in zip(tmpl, masked):
        if m == "" and (t == "" or t is None):
            continue
        n += 1
        if t is None:
            wild += 1
        elif t == m:
            eq += 1
    return 1.0 if n == 0 else (eq + 0.5 * wild) / n


def _slot_type(types: set) -> str:
    types = set(types or ())
    if not types:
        return "str"
    if len(types) == 1:
        return next(iter(types))
    if types <= {"int", "float"}:
        return "float"
    if types <= {"int", "epoch"}:
        return "int"
    if "text" in types:
        return "text"
    return "str"


def _context_before(words, delims, p: int) -> str:
    """Delimiter characters between the previous non-empty word and position p."""
    ctx = []
    q = p - 1
    while q >= 0:
        ctx.append(delims[q])
        if words[q] not in ("", None):
            break
        q -= 1
    return "".join(reversed(ctx))


def is_value_position(words, delims, p: int) -> bool:
    if p == 0:
        return False
    ctx = _context_before(words, delims, p).replace(" ", "")
    return ctx.endswith("=") or ctx.endswith('="') or ctx.endswith(':"') or ctx == '":' or ctx.endswith('":')


def is_header_hostname(delims, p: int, ts_pos: int | None) -> bool:
    """Word right after a leading syslog timestamp, unless it is actually a key (`time=`)."""
    return (ts_pos is not None and p == ts_pos + 1 and p <= 6 and delims[p - 1].isspace()
            and (p >= len(delims) or delims[p] not in ("=", ":", '"')))


def _finalize(c: _Cluster) -> Template:
    words = list(c.tmpl)
    delims = c.delims
    n = len(words)
    comma_ratio = sum(1 for d in delims if d == ",") / max(1, len(delims))
    csv_like = comma_ratio >= 0.6 and len(delims) >= 8
    first_ts = next((p for p in range(min(n, 6)) if word_type(c.words0[p]) == "ts"), None)
    first_comma = next((i for i, d in enumerate(delims) if d == ","), len(delims))
    for p in range(n):
        w = words[p]
        if w is None:
            continue
        if w.startswith("<") and w.endswith(">") and w[1:-1] in VARIABLE_TYPES:
            words[p] = None
            continue
        if w == "":
            continue
        concrete = c.words0[p]
        if is_value_position(c.words0, delims, p):
            words[p] = None
        elif csv_like and p > first_comma and not _RECORD_TYPE.fullmatch(concrete):
            words[p] = None
        elif is_header_hostname(delims, p, first_ts):
            words[p] = None  # syslog header hostname right after the timestamp
    slots = {}
    for p, w in enumerate(words):
        if w is None:
            quoted = p > 0 and delims[p - 1] == '"' and p < len(delims) and delims[p] == '"'
            st = _slot_type(c.types.get(p))
            if quoted and st == "str" and any(" " in v for v in c.values.get(p, [])):
                st = "text"
            slots[p] = Slot(pos=p, type=st, quoted=quoted, examples=list(c.values.get(p, [])))
    tid = template_hash(delims, words)
    return Template(tid, delims, tuple(words), slots, count=c.count, examples=list(c.examples))


class EkaMiner:
    def __init__(self, sim_threshold: float | None = None):
        self.th = settings.miner_sim_threshold if sim_threshold is None else sim_threshold
        self.groups: dict[tuple, list[_Cluster]] = {}
        self.cache: dict[tuple, _Cluster] = {}
        self.lines = 0

    def add(self, line: str) -> None:
        words, delims = tokenize(line)
        dk = tuple(delims)
        masked = tuple(mask(w) for w in words)
        key = (dk, masked)
        c = self.cache.get(key)
        if c is None:
            best, best_sim = None, -1.0
            for cand in self.groups.get(dk, ()):
                s = _similarity(cand.tmpl, masked)
                if s > best_sim:
                    best, best_sim = cand, s
            if best is not None and best_sim >= self.th:
                c = best
            else:
                c = _Cluster(dk, list(masked))
                self.groups.setdefault(dk, []).append(c)
            self.cache[key] = c
        c.add(words, masked, line, settings.miner_max_examples)
        self.lines += 1

    def templates(self) -> list[Template]:
        out: dict[str, Template] = {}
        for clusters in self.groups.values():
            for c in clusters:
                t = _finalize(c)
                if t.tid in out:  # two clusters generalized to the same template
                    out[t.tid].count += t.count
                else:
                    out[t.tid] = t
        return sorted(out.values(), key=lambda t: -t.count)


def mine(lines) -> list[Template]:
    m = EkaMiner()
    for ln in lines:
        m.add(ln)
    return m.templates()
