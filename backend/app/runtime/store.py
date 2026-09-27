"""Persistence: raw vault (append-only, written before parsing), event store, quarantine, hash-chain ledger."""
from __future__ import annotations

import hashlib
import ipaddress
import sqlite3
import threading
import time
from pathlib import Path

import orjson

from ..config import settings
from ..core import crypto


class Vault:
    """Append-only raw byte store. raw_ref = vault://<segment>/<offset>/<length>."""

    SEGMENT_BYTES = 64 * 1024 * 1024

    def __init__(self, root: Path | None = None):
        self.root = root or (settings.state_dir / "vault")
        self.root.mkdir(parents=True, exist_ok=True)
        segs = sorted(self.root.glob("seg-*.log"))
        self.seg = int(segs[-1].stem[4:]) if segs else 1
        self._lock = threading.Lock()
        self._open()

    def _open(self):
        self.path = self.root / f"seg-{self.seg:06d}.log"
        self.fh = open(self.path, "ab")
        self.offset = self.fh.tell()

    def append_many(self, raws: list[bytes]) -> list[str]:
        refs = []
        with self._lock:
            if self.offset > self.SEGMENT_BYTES:
                self.fh.close()
                self.seg += 1
                self._open()
            for b in raws:
                refs.append(f"vault://{self.seg:06d}/{self.offset}/{len(b)}")
                self.fh.write(b)
                self.fh.write(b"\n")
                self.offset += len(b) + 1
            self.fh.flush()
        return refs

    def read(self, ref: str) -> bytes | None:
        try:
            _, rest = ref.split("://", 1)
            seg, off, ln = rest.split("/")
            with open(self.root / f"seg-{int(seg):06d}.log", "rb") as f:
                f.seek(int(off))
                return f.read(int(ln))
        except (ValueError, OSError):
            return None


class EventStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (settings.state_dir / "events.db")
        self._lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript("""
            PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time INTEGER, source TEXT, class_uid INTEGER,
              severity_id INTEGER, parser TEXT, template_id TEXT, injection INTEGER, status TEXT, body TEXT);
            CREATE INDEX IF NOT EXISTS ev_time ON events(time);
            CREATE INDEX IF NOT EXISTS ev_source ON events(source, id);
            CREATE TABLE IF NOT EXISTS quarantine(id INTEGER PRIMARY KEY, source TEXT, line TEXT, enc TEXT,
              raw_ref TEXT, ingest_hash TEXT, ts REAL, replayed INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS q_src ON quarantine(source, replayed);
            CREATE TABLE IF NOT EXISTS ledger(batch INTEGER PRIMARY KEY, first_id INTEGER, last_id INTEGER, n INTEGER,
              root TEXT, chain TEXT, ts REAL, signature TEXT);
        """)
        row = self.db.execute("SELECT MAX(id) FROM events").fetchone()
        self.next_id = (row[0] or 0) + 1
        row = self.db.execute("SELECT batch, chain FROM ledger ORDER BY batch DESC LIMIT 1").fetchone()
        self.batch_no, self.chain = (row[0], row[1]) if row else (0, "0" * 64)

    def assign_ids(self, n: int) -> int:
        with self._lock:
            first = self.next_id
            self.next_id += n
            return first

    def insert(self, events: list[dict]):
        if not events:
            return
        rows = []
        for e in events:
            ek = e.get("ekalog", {})
            rows.append((e["id"], e.get("time"), ek.get("source"), e.get("class_uid"), e.get("severity_id"),
                         ek.get("parser", {}).get("id"), ek.get("template_id"),
                         int(bool(ek.get("injection", {}).get("detected"))), ek.get("status"), orjson.dumps(e).decode()))
        # hash-chain ledger: root over ingest hashes of this batch, chained to the previous batch
        root = hashlib.sha256("".join(e["ekalog"]["ingest_hash"] for e in events).encode()).hexdigest()
        with self._lock:
            self.batch_no += 1
            self.chain = hashlib.sha256((self.chain + root).encode()).hexdigest()
            sig = crypto.sign(self.chain.encode()) if self.batch_no % 50 == 1 else None
            self.db.executemany("INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            self.db.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",
                            (self.batch_no, events[0]["id"], events[-1]["id"], len(events), root, self.chain,
                             time.time(), sig))
            self.db.commit()
            if self.next_id % 20000 < len(events):
                self._trim()

    def _trim(self):
        cut = self.next_id - settings.store_max_events
        if cut > 0:
            self.db.execute("DELETE FROM events WHERE id < ?", (cut,))

    def get(self, eid: int) -> dict | None:
        row = self.db.execute("SELECT body FROM events WHERE id=?", (eid,)).fetchone()
        return orjson.loads(row[0]) if row else None

    def query(self, where: str = "", params: tuple = (), limit: int = 100) -> list[dict]:
        sql = "SELECT body FROM events" + (f" WHERE {where}" if where else "") + " ORDER BY id DESC LIMIT ?"
        return [orjson.loads(r[0]) for r in self.db.execute(sql, (*params, limit))]

    def counts(self) -> dict:
        r = self.db.execute("SELECT COUNT(*), SUM(injection), SUM(status='unmatched') FROM events").fetchone()
        by_class = dict(self.db.execute("SELECT class_uid, COUNT(*) FROM events GROUP BY class_uid").fetchall())
        by_source = dict(self.db.execute("SELECT source, COUNT(*) FROM events GROUP BY source").fetchall())
        return {"events": r[0] or 0, "injection": r[1] or 0, "unmatched": r[2] or 0, "by_class": by_class,
                "by_source": by_source}

    # ---------- quarantine (never drop) ----------
    def quarantine(self, rows: list[tuple]):
        if rows:
            with self._lock:
                self.db.executemany("INSERT INTO quarantine(source,line,enc,raw_ref,ingest_hash,ts) VALUES(?,?,?,?,?,?)",
                                    rows)
                self.db.commit()

    def quarantined(self, source: str, limit: int = 5000) -> list[tuple]:
        return self.db.execute("SELECT id, line, enc, raw_ref, ingest_hash FROM quarantine WHERE source=? AND "
                               "replayed=0 ORDER BY id LIMIT ?", (source, limit)).fetchall()

    def mark_replayed(self, ids: list[int]):
        with self._lock:
            self.db.executemany("UPDATE quarantine SET replayed=1 WHERE id=?", [(i,) for i in ids])
            self.db.commit()

    def quarantine_counts(self) -> dict:
        return dict(self.db.execute("SELECT source, COUNT(*) FROM quarantine WHERE replayed=0 GROUP BY source").fetchall())

    # ---------- ledger ----------
    def verify_ledger(self, last_n: int = 500) -> dict:
        rows = self.db.execute("SELECT batch, root, chain, signature FROM ledger ORDER BY batch DESC LIMIT ?",
                               (last_n + 1,)).fetchall()[::-1]
        if len(rows) < 2:
            return {"ok": True, "batches": len(rows), "signed_checkpoints": 0}
        ok, signed, bad_at = True, 0, None
        pub = crypto.public_key_b64()
        for prev, cur in zip(rows, rows[1:]):
            if hashlib.sha256((prev[2] + cur[1]).encode()).hexdigest() != cur[2]:
                ok, bad_at = False, cur[0]
                break
            if cur[3]:
                signed += 1
                if not crypto.verify(cur[2].encode(), cur[3], pub):
                    ok, bad_at = False, cur[0]
                    break
        return {"ok": ok, "batches": len(rows) - 1, "signed_checkpoints": signed, "broken_at": bad_at,
                "head": rows[-1][2], "signer": crypto.fingerprint()}


def ip_in_cidr(ip: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
