"""Fast timestamp parsing to epoch milliseconds (regex + calendar.timegm, no strptime)."""
from __future__ import annotations

import calendar
import re
import time
from functools import lru_cache

_MON = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
_ISO = re.compile(
    r"(\d{4})[-/](\d{2})[-/](\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2})(\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")
_BSD = re.compile(r"([A-Z][a-z]{2}) {1,2}(\d{1,2})(?: (\d{4}))? (\d{2}):(\d{2}):(\d{2})(\.\d+)?$")
_CLOCK = re.compile(r"(\d{2}):(\d{2}):(\d{2})(\.\d+)?$")


def _tz(s: str | None) -> int:
    if not s or s == "Z":
        return 0
    sign = -1 if s[0] == "-" else 1
    s = s[1:].replace(":", "")
    return sign * (int(s[:2]) * 3600 + int(s[2:4]) * 60)


@lru_cache(maxsize=65536)
def to_epoch_ms(s: str, default_year: int | None = None) -> int | None:
    s = s.strip()
    if not s:
        return None
    c = s[0]
    if c.isdigit():
        m = _ISO.match(s)
        if m:
            y, mo, d, hh, mm, ss, frac, tz = m.groups()
            secs = calendar.timegm((int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0)))
            ms = int(float(frac) * 1000) if frac else 0
            return (secs - _tz(tz)) * 1000 + ms
        try:
            v = float(s)
        except ValueError:
            return None
        if v > 1e17:  # nanoseconds
            return int(v / 1e6)
        if v > 1e11:  # milliseconds
            return int(v)
        if v > 1e8:  # seconds
            return int(v * 1000)
        return None
    m = _BSD.match(s)
    if m:
        mon, d, y, hh, mm, ss, frac = m.groups()
        year = int(y) if y else (default_year or time.gmtime().tm_year)
        secs = calendar.timegm((year, _MON.get(mon, 1), int(d), int(hh), int(mm), int(ss)))
        return secs * 1000 + (int(float(frac) * 1000) if frac else 0)
    return None


def combine(parts: list[str]) -> int | None:
    """FortiGate-style split date + time fields."""
    if len(parts) == 1:
        return to_epoch_ms(parts[0])
    date = next((p for p in parts if "-" in p or "/" in p), None)
    clock = next((p for p in parts if _CLOCK.match(p)), None)
    if date and clock:
        return to_epoch_ms(f"{date} {clock}")
    for p in parts:
        v = to_epoch_ms(p)
        if v:
            return v
    return None
