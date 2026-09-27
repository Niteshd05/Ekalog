"""Injection Guard — detects prompt-injection and log-forgery payloads *inside log data*.

Threat model: logs are attacker-influenced. Published work (arXiv 2607.24174 "Just Testing,
Move Along"; arXiv 2607.14493 on passive prompt injection in network security logs) shows
instructions embedded in log fields flip LLM verdicts to "benign". EKALOG defends structurally
(the model never sees raw text) and additionally turns such payloads into a detection signal.
"""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field

from ..config import settings

_I = re.IGNORECASE
# (name, weight, pattern)
_RULES: list[tuple[str, float, re.Pattern]] = [
    ("instruction_override", 0.55, re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|all|earlier)\b.{0,20}\b"
        r"(instructions?|rules?|prompts?|context|guidelines)", _I)),
    ("verdict_steering", 0.5, re.compile(
        r"\b(classify|mark|label|report|treat|flag|summari[sz]e|respond)\b.{0,40}\b(as\s+)?"
        r"(benign|safe|legitimate|false[\s_-]?positive|no\s+threat|routine|harmless|normal)\b"
        r"|\b(ignore|suppress|disregard|do\s+not\s+escalate)\s+(these\s+|the\s+|all\s+|this\s+)?"
        r"(alerts?|alarms?|warnings?|detections?|events?)\b", _I)),
    ("benign_framing", 0.35, re.compile(
        r"\b(authori[sz]ed\s+(pen(etration)?\s*)?test(ing)?|just\s+testing|move\s+along|routine\s+maintenance|"
        r"approved\s+by\s+(the\s+)?(ciso|soc|it)|scheduled\s+scan|nothing\s+to\s+see|all\s+clear)\b", _I)),
    ("ai_addressing", 0.4, re.compile(
        r"\b(note\s+to\s+(the\s+)?(ai|llm|assistant|analyst)|as\s+(the|an?)\s+(soc\s+)?(ai|assistant|analyst|model)|"
        r"you\s+are\s+(a|an|the)\s+\w+|you\s+must\s+(respond|say|answer|classify))\b", _I)),
    ("role_token", 0.6, re.compile(
        r"(<\|im_(start|end)\|>|<\|(system|user|assistant|endoftext)\|>|\[/?INST\]|<<\s*SYS\s*>>|"
        r"^\s*(system|assistant)\s*:|\bsystem\s*:\s*you\b|###\s*(instruction|system|response)|```)", _I | re.M)),
    ("log_forgery", 0.6, re.compile(r"[\r\n]+\s*(<\d{1,3}>|[A-Z][a-z]{2} {1,2}\d{1,2} \d{2}:\d{2}:\d{2})")),
    ("control_chars", 0.4, re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")),
    ("zero_width", 0.35, re.compile(r"[​-‏ -‮⁠-⁤﻿]")),
    ("unicode_escapes", 0.3, re.compile(r"(\\u[0-9a-fA-F]{4}){6,}|(\\x[0-9a-fA-F]{2}){8,}")),
]
_ZW = re.compile(r"[​-‏⁠-⁤﻿]")
_B64 = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
# cheap pre-filter: any of these characters/words => run the full rule set
_PRE = re.compile(r"ignore|disregard|classif|benign|authori|testing|move along|routine|you |assistant|system|"
                  r"<\||\[INST|###|```|[\r\n\x1b​-‏⁠﻿]|\\u|[A-Za-z0-9+/]{120,}|scan|legit|"
                  r"false positive|all clear|nothing to see|ciso", _I)


@dataclass
class Verdict:
    detected: bool = False
    score: float = 0.0
    indicators: list[str] = field(default_factory=list)
    spans: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"detected": self.detected, "score": round(self.score, 3), "indicators": self.indicators,
                "spans": self.spans}


_ESC = re.compile(r"(?:\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}|[ \w.,:;'-])*(?:\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}){6,}"
                  r"(?:\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}|[ \w.,:;'-])*")


def _is_instruction(decoded: str) -> bool:
    printable = sum(ch.isprintable() for ch in decoded) / max(1, len(decoded))
    return printable > 0.9 and any(r[2].search(decoded) for r in _RULES[:4])


def _encoded_payload(text: str) -> tuple[int, int] | None:
    """Decode base64 blobs and \\u/\\x escape runs; flag them if the plaintext is an instruction."""
    for m in _B64.finditer(text):
        blob = m.group()
        try:
            dec = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False).decode("utf-8", "ignore")
        except ValueError:
            continue
        if _is_instruction(dec):
            return m.span()
    for m in _ESC.finditer(text):
        try:
            dec = m.group().encode("latin-1", "ignore").decode("unicode_escape")
        except UnicodeDecodeError:
            continue
        if _is_instruction(dec):
            return m.span()
    return None


def scan(text: str, threshold: float | None = None) -> Verdict:
    th = settings.injection_threshold if threshold is None else threshold
    if not _PRE.search(text):
        return Verdict()
    keep = 1.0
    v = Verdict()
    # De-obfuscate before matching (zero-width splitting, full-width homoglyphs); the obfuscation
    # itself is still scored by the zero_width rule on the original text.
    norm = unicodedata.normalize("NFKC", _ZW.sub("", text))
    for name, w, rx in _RULES:
        m = rx.search(text if name in ("zero_width", "control_chars") else norm)
        if m:
            keep *= (1 - w)
            v.indicators.append(name)
            v.spans.append(m.span())
    span = _encoded_payload(text)
    if span:
        keep *= 0.4
        v.indicators.append("encoded_instruction")
        v.spans.append(span)
    v.score = 1 - keep
    v.detected = v.score >= th
    return v
