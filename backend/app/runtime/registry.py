"""Parser registry: immutable versioned artifacts in SQLite, atomic hot-swap via Router snapshots."""
from __future__ import annotations

import sqlite3
import threading
import time

import orjson

from ..config import settings
from ..core import crypto
from ..core.template import ParserArtifact, Template


def bump(version: str, part: str = "minor") -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


class Router:
    """Immutable snapshot used by the data plane. Replaced atomically on hot-swap."""

    def __init__(self, active: dict[str, ParserArtifact], bindings: dict[str, str]):
        self.active = active
        self.bindings = dict(bindings)
        self.order = sorted(active.values(), key=lambda p: -len(p.templates))
        self.new_bindings: dict[str, str] = {}

    def resolve(self, source: str, words, delims) -> tuple[Template | None, ParserArtifact | None]:
        pid = self.bindings.get(source)
        if pid:
            p = self.active.get(pid)
            if p:
                t = p.lookup(words, delims)
                if t:
                    return t, p
        for p in self.order:
            if p.id == pid:
                continue
            t = p.lookup(words, delims)
            if t:
                if pid is None:
                    self.bindings[source] = p.id
                    self.new_bindings[source] = p.id
                return t, p
        return None, None


class Registry:
    def __init__(self, path=None):
        self.path = path or (settings.state_dir / "registry.db")
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS parsers(pid TEXT, version TEXT, sha256 TEXT, status TEXT, created REAL,
                body TEXT, PRIMARY KEY(pid, version));
            CREATE TABLE IF NOT EXISTS bindings(source TEXT PRIMARY KEY, pid TEXT, auto INTEGER, created REAL);
            CREATE TABLE IF NOT EXISTS llm_cache(key TEXT PRIMARY KEY, value TEXT, created REAL);
        """)
        self._versions: dict[tuple[str, str], ParserArtifact] = {}
        self.active: dict[str, ParserArtifact] = {}
        self.bindings: dict[str, str] = {}
        self._load()
        self.router = Router(self.active, self.bindings)

    def _load(self):
        for pid, version, body in self.db.execute(
                "SELECT pid, version, body FROM parsers WHERE status='active' ORDER BY created"):
            self.active[pid] = self._cache(ParserArtifact.from_dict(orjson.loads(body)))
        self.bindings = {s: p for s, p in self.db.execute("SELECT source, pid FROM bindings")}

    def _cache(self, art: ParserArtifact) -> ParserArtifact:
        self._versions[(art.id, art.version)] = art
        return art

    def _swap(self):
        self.router = Router(dict(self.active), self.bindings)

    # ---------- write ----------
    def register(self, art: ParserArtifact, activate: bool = True) -> ParserArtifact:
        with self._lock:
            art.compute_sha()
            art.signature = crypto.sign(art.sha256.encode())
            art.provenance.setdefault("signer", crypto.fingerprint())
            art.status = "active" if activate else "pending_review"
            if activate:
                self.db.execute("UPDATE parsers SET status='retired' WHERE pid=? AND status='active'", (art.id,))
            self.db.execute("INSERT OR REPLACE INTO parsers VALUES(?,?,?,?,?,?)",
                            (art.id, art.version, art.sha256, art.status, time.time(), orjson.dumps(art.to_dict())))
            self.db.commit()
            self._cache(art)
            if activate:
                self.active[art.id] = art
                self._swap()
            return art

    def activate(self, pid: str, version: str) -> ParserArtifact | None:
        art = self.get(pid, version)
        if not art:
            return None
        with self._lock:
            self.db.execute("UPDATE parsers SET status='retired' WHERE pid=? AND status='active'", (pid,))
            self.db.execute("UPDATE parsers SET status='active' WHERE pid=? AND version=?", (pid, version))
            self.db.commit()
            art.status = "active"
            self.active[pid] = art
            self._swap()
        return art

    def bind(self, source: str, pid: str, auto: bool = False):
        with self._lock:
            self.bindings[source] = pid
            self.db.execute("INSERT OR REPLACE INTO bindings VALUES(?,?,?,?)", (source, pid, int(auto), time.time()))
            self.db.commit()
            self._swap()

    def absorb_router_bindings(self, router: Router):
        if router.new_bindings:
            for s, p in list(router.new_bindings.items()):
                if s not in self.bindings:
                    self.bind(s, p, auto=True)
            router.new_bindings.clear()

    def delete_all(self):
        with self._lock:
            self.db.executescript("DELETE FROM parsers; DELETE FROM bindings;")
            self.db.commit()
            self.active.clear()
            self.bindings.clear()
            self._versions.clear()
            self._swap()

    # ---------- read ----------
    def get(self, pid: str, version: str | None = None) -> ParserArtifact | None:
        if version is None:
            return self.active.get(pid)
        art = self._versions.get((pid, version))
        if art:
            return art
        row = self.db.execute("SELECT body FROM parsers WHERE pid=? AND version=?", (pid, version)).fetchone()
        return self._cache(ParserArtifact.from_dict(orjson.loads(row[0]))) if row else None

    def versions(self, pid: str) -> list[dict]:
        rows = self.db.execute("SELECT version, sha256, status, created FROM parsers WHERE pid=? ORDER BY created",
                               (pid,)).fetchall()
        return [{"version": v, "sha256": s, "status": st, "created": c} for v, s, st, c in rows]

    def latest_version(self, pid: str) -> str | None:
        row = self.db.execute("SELECT version FROM parsers WHERE pid=? ORDER BY created DESC LIMIT 1", (pid,)).fetchone()
        return row[0] if row else None

    def list(self) -> list[dict]:
        out = []
        rows = self.db.execute("SELECT DISTINCT pid FROM parsers").fetchall()
        for (pid,) in rows:
            art = self.active.get(pid) or self.get(pid, self.latest_version(pid))
            sources = [s for s, p in self.bindings.items() if p == pid]
            out.append({"id": pid, "version": art.version, "status": art.status, "sha256": art.sha256,
                        "templates": len(art.templates), "source_hint": art.source_hint, "metrics": art.metrics,
                        "provenance": art.provenance, "sources": sources, "versions": self.versions(pid)})
        return out

    # ---------- LLM cache (by template hash; the same template is never asked twice) ----------
    def cache_get(self, key: str):
        row = self.db.execute("SELECT value FROM llm_cache WHERE key=?", (key,)).fetchone()
        return orjson.loads(row[0]) if row else None

    def cache_put(self, key: str, value):
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO llm_cache VALUES(?,?,?)", (key, orjson.dumps(value), time.time()))
            self.db.commit()
