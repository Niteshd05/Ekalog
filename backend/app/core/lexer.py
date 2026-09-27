"""EkaLexer — a delimiter-preserving tokenizer.

Every line becomes a strict alternation ``w0 d0 w1 d1 ... wn`` where words may be
empty and delimiters are either a single punctuation character or a run of
whitespace. ``render(words, delims) == line`` holds for every input, which is the
foundation of EKALOG's structural losslessness (Drain-style tokenizers split on
whitespace and discard separators, so they cannot give this guarantee).

Atoms such as timestamps, clock times, IPv6 and MAC addresses contain delimiter
characters but are kept as a single word. Quoted strings become
``"`` + content-word + ``"`` so free text with spaces is one slot.
"""
from __future__ import annotations

import re

DELIM_CHARS = '=,;|:/[](){}<>"'
_DC = re.escape(DELIM_CHARS)

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_TS_ATOM = (
    r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"  # ISO-ish
    rf"|(?:{_MONTHS}) {{1,2}}\d{{1,2}}(?: \d{{4}})? \d{{2}}:\d{{2}}:\d{{2}}(?:\.\d+)?"  # RFC 3164 / ASA
    r"|\d{2}:\d{2}:\d{2}(?:\.\d+)?"  # clock time
)
_NET_ATOM = (
    r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}"  # MAC
    r"|(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"  # full IPv6
    r"|(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5})?"  # compressed IPv6
)
_ATOM = f"{_TS_ATOM}|{_NET_ATOM}"
# Order matters: quoted string, atom (only if followed by a boundary), plain word, delimiters.
_MASTER = re.compile(
    rf'(?P<q>"(?:[^"\\]|\\.)*")'
    rf"|(?P<a>(?:{_ATOM}))(?=[\s{_DC}]|$)"
    rf"|(?P<w>[^\s{_DC}]+)"
    rf"|(?P<s>\s+)"
    rf"|(?P<d>[{_DC}])"
)


_CSV_FIELD = re.compile(r'"(?:[^"]|"")*"(?=,|$)|[^,]*')


def _is_csv(line: str) -> bool:
    c = line.count(",")
    return c >= 10 and c >= 2 * line.count(" ") and line.lstrip()[:1] not in ("{", "[")


def tokenize(line: str) -> tuple[list[str], list[str]]:
    """Split ``line`` into (words, delims) with len(words) == len(delims) + 1.

    Comma-dominant lines (PAN-OS, pfSense filterlog) use *column mode* after the
    first comma: only ',' separates, so free text inside a column stays one word.
    """
    if _is_csv(line):
        i = line.index(",")
        words, delims = _tokenize(line[:i])
        pos = i
        n = len(line)
        while pos < n:  # line[pos] == ','
            delims.append(",")
            m = _CSV_FIELD.match(line, pos + 1)
            words.append(m.group())
            pos = m.end()
        return words, delims
    return _tokenize(line)


def _tokenize(line: str) -> tuple[list[str], list[str]]:
    words: list[str] = []
    delims: list[str] = []
    expect_word = True
    for m in _MASTER.finditer(line):
        kind = m.lastgroup
        text = m.group()
        if kind == "q":
            if expect_word:
                words.append("")
            delims.append('"')
            words.append(text[1:-1])
            delims.append('"')
            expect_word = True
        elif kind in ("a", "w"):
            # Two words cannot be adjacent: 'w' is maximal and atoms need a boundary.
            words.append(text)
            expect_word = False
        else:  # s or d
            if expect_word:
                words.append("")
            delims.append(text)
            expect_word = True
    if expect_word:
        words.append("")
    return words, delims


def render(words, delims) -> str:
    out = [words[0]]
    for d, w in zip(delims, words[1:]):
        out.append(d)
        out.append(w)
    return "".join(out)


# ---------- word typing (used for masking and slot typing) ----------
_IPV4 = re.compile(r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}")
_INT = re.compile(r"[+-]?\d+")
_FLOAT = re.compile(r"[+-]?\d+\.\d+")
_HEX = re.compile(r"(?:0x[0-9A-Fa-f]+|[0-9A-Fa-f]{8,})")
_MAC = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")
_TS = re.compile(rf"(?:{_TS_ATOM})|\d{{4}}-\d{{2}}-\d{{2}}")
_IPV6 = re.compile(r"[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*")
_EPOCH = re.compile(r"1[5-9]\d{8}(?:\.\d+)?|1[5-9]\d{11}")


def word_type(w: str) -> str:
    if w == "":
        return "empty"
    c = w[0]
    if c.isdigit() or c in "+-":
        if _IPV4.fullmatch(w):
            return "ipv4"
        if _EPOCH.fullmatch(w):
            return "epoch"
        if _INT.fullmatch(w):
            return "int"
        if _FLOAT.fullmatch(w):
            return "float"
    if _TS.fullmatch(w):
        return "ts"
    if _MAC.fullmatch(w):
        return "mac"
    if ":" in w and _IPV6.fullmatch(w):
        return "ipv6"
    if _HEX.fullmatch(w) and any(ch.isdigit() for ch in w):
        return "hex"
    if " " in w:
        return "text"
    return "str"


# Types that are never meaningful as a template constant.
VARIABLE_TYPES = {"ipv4", "ipv6", "int", "float", "hex", "ts", "mac", "epoch", "text"}


def mask(w: str) -> str:
    t = word_type(w)
    return f"<{t}>" if t in VARIABLE_TYPES else w
