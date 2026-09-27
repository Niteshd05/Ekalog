"""Round-trip over every sample file: 0 failures allowed, including odd encodings and whitespace."""
import random

import pytest

from app.core.lexer import render, tokenize
from app.core.template import ParserArtifact
from app.foundry.labeler import label_all
from app.foundry.miner import mine
from app.runtime.executor import Item, normalize_batch, reconstruct, sha256_hex
from app.runtime.pipeline import decode
from app.runtime.registry import Router
from conftest import DATA, read_lines

SAMPLES = sorted((DATA / "samples").glob("*"))


def _artifact(lines, name="t"):
    tpls = mine(lines)
    art = ParserArtifact(name, "1.0.0", tpls, label_all(tpls))
    art.compute_sha()
    return art


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_every_event_rebuilds_byte_exact(path):
    lines = read_lines(path)
    art = _artifact(lines)
    items = [Item(ln, "s", "utf-8", sha256_hex(ln), "r", 0) for ln in lines]
    events, st = normalize_batch(items, Router({art.id: art}, {"s": art.id}))
    assert st["unmatched"] == 0
    assert st["verify_failed"] == 0
    assert st["verified"] == len(lines)
    for ev in events[:50]:  # the rebuild uses the normalized record only (no raw_data field)
        assert "raw_data" not in ev
        t = art.template(ev["ekalog"]["template_id"])
        assert sha256_hex(reconstruct(ev, t)) == ev["ekalog"]["ingest_hash"][7:]


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_holdout_generalization(path):
    lines = read_lines(path)
    rng = random.Random(7)
    rng.shuffle(lines)
    cut = int(len(lines) * 0.8)
    art = _artifact(lines[:cut])
    hits = sum(1 for ln in lines[cut:] if art.parse_line(ln))
    assert hits / len(lines[cut:]) >= 0.95


WEIRD = [
    "", " ", "\t\t", "a", "=", '"', '""', 'k="unterminated', "x  y   z", "trailing   ",
    '{"a":"b\\"c","d":[1,2,{"e":null}]}', "fe80::1%eth0 10.0.0.1:443/tcp", "ümlaut ♥ 日本語 key=värde",
    "Sep  7 01:02:03 host prog[1]: msg", "a,,,,,,,,,,,,,b", '1,"quoted, comma",,x,,,,,,,,,,,z',
    "\x1b[31mred\x1b[0m", "zero​width", "CEF:0|V|P|1|2|N|5|k=v\\=x",
]


@pytest.mark.parametrize("line", WEIRD)
def test_lexer_is_lossless(line):
    w, d = tokenize(line)
    assert len(w) == len(d) + 1
    assert render(w, d) == line


def test_non_utf8_bytes_round_trip():
    raw = b"date=2026-09-27 msg=\"caf\xe9 \xff\xfe\" srcip=10.0.0.1"
    line, enc = decode(raw)
    assert enc == "latin-1"
    art = _artifact([line])
    it = Item(line, "s", enc, sha256_hex(line, enc), "r", 0)
    events, st = normalize_batch([it], Router({art.id: art}, {"s": art.id}))
    assert st["verified"] == 1
    assert sha256_hex(line, enc) == __import__("hashlib").sha256(raw).hexdigest()


def test_duplicate_ocsf_paths_are_resolved():
    """Two slots claiming one OCSF path would overwrite each other and break the round-trip."""
    from app.foundry.labeler import decide_semantics
    lines = [f"conn from {i}.1.1.1 to 10.0.0.{i} x" for i in range(1, 40)]
    art = _artifact(lines)
    t = art.templates[0]
    ips = [s for s in t.slots.values() if s.type == "ipv4"]
    ips[0].ocsf, ips[0].labeled_by = "dst_endpoint.ip", "llm"
    ips[1].ocsf, ips[1].labeled_by = "dst_endpoint.ip", "rule-ctx"
    decide_semantics(t)
    assert [s.ocsf for s in ips].count("dst_endpoint.ip") == 1
    items = [Item(ln, "s", "utf-8", sha256_hex(ln), "r", 0) for ln in lines]
    _, st = normalize_batch(items, Router({art.id: art}, {"s": art.id}))
    assert st["verify_failed"] == 0
