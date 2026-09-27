"""End-to-end through the real API: onboard -> ingest -> drift alarm -> auto-heal -> replay; packs."""
import io
import time
import zipfile

from fastapi.testclient import TestClient

from app.main import app


def _wait(pred, timeout=30.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def test_onboard_drift_heal_and_packs():
    with TestClient(app) as c:
        c.post("/api/reset", params={"parsers": True})
        job = c.post("/api/sources/onboard", data={"sample": "samples/fortigate.log", "source": "fortigate"}).json()
        done = _wait(lambda: (lambda j: j if j["stage"] in ("done", "error") else None)(
            c.get(f"/api/foundry/{job['job_id']}").json()))
        assert done and done["stage"] == "done", done
        assert done["result"]["gates_passed"]
        pid = done["result"]["parser_id"]
        assert pid == "fortinet.fortigate"

        c.post("/api/ingest/replay", json={"sample": "samples/fortigate.log", "source": "fortigate", "eps": 5000,
                                           "limit": 600})
        assert _wait(lambda: c.get("/api/stats").json()["events"] >= 600)
        st = c.get("/api/stats").json()
        assert st["verify_failed"] == 0 and st["unmatched"] == 0

        # reconstruct any event from its normalized record
        ev = c.get("/api/events", params={"limit": 1}).json()[0]
        rc = c.get(f"/api/events/{ev['id']}/reconstruct").json()
        assert rc["match"] and rc["vault_match"] and rc["raw"] == rc["rebuilt"]

        # firmware upgrade -> drift alarm within seconds -> healed new version -> quarantine drained
        t0 = time.time()
        c.post("/api/drift/simulate", params={"source": "fortigate", "eps": 2000})
        healed = _wait(lambda: next((j for j in c.get("/api/drift").json()["heal_jobs"] if j["stage"] == "done"), None),
                       timeout=60)
        assert healed, c.get("/api/drift").json()
        assert time.time() - t0 < 30
        assert healed["result"]["version"] == "1.1.0"
        added = {n for d in healed["result"]["diff"] for n in d["added"]}
        assert "poluuid" in added
        assert _wait(lambda: not c.get("/api/stats").json()["quarantine"].get("fortigate"), timeout=20)

        # ledger chain intact, batch proof clean
        proof = c.get("/api/vault/verify").json()
        assert proof["failed"] == 0 and proof["ledger"]["ok"]

        # exports
        assert "%{IPV4:srcip}" in c.get(f"/api/parsers/{pid}/export", params={"flavor": "grok"}).text

        # packs: export, wipe, import (tests re-run), and tampering is refused
        pack = c.post("/api/packs/export", json={}).content
        c.post("/api/reset", params={"parsers": True})
        rep = c.post("/api/packs/import", files={"file": ("p.ekapack", pack)}).json()
        assert rep["ok"], rep
        rep2 = c.post("/api/packs/import", files={"file": ("p.ekapack", _tamper(pack))}).json()
        assert not rep2["ok"]
        assert any(not ch["ok"] and ch["check"].startswith("hash") for ch in rep2["checks"])


def _tamper(pack: bytes) -> bytes:
    """Re-zip the pack with one parser field renamed (keeps the original manifest + signature)."""
    src, out = zipfile.ZipFile(io.BytesIO(pack)), io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name in src.namelist():
            b = src.read(name)
            if name.startswith("parsers/"):
                b = b.replace(b'"srcip"', b'"srcIP"', 1)
            z.writestr(name, b)
    return out.getvalue()
