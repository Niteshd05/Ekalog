""".ekapack — signed, test-carrying parser bundles for sneakernet transfer into air-gapped SOCs.

Layout (zip): manifest.json, manifest.sig, parsers/<id>@<version>.json
Import refuses on: bad manifest signature, untrusted signer (unless explicitly trusted), file hash
mismatch, artifact hash/signature mismatch, or any failing embedded test vector.
"""
from __future__ import annotations

import hashlib
import io
import time
import zipfile

import orjson

from ..config import settings
from ..core import crypto, ocsf
from ..core.template import ParserArtifact
from ..runtime.executor import Item, normalize_batch, sha256_hex
from ..runtime.registry import Registry, Router

FORMAT = "ekapack/1"


def _trusted() -> set[str]:
    path = settings.state_dir / "trusted_signers.txt"
    keys = {crypto.public_key_b64()}
    if path.exists():
        keys |= {ln.strip() for ln in path.read_text().splitlines() if ln.strip()}
    return keys


def trust(pub_b64: str):
    path = settings.state_dir / "trusted_signers.txt"
    with open(path, "a") as f:
        f.write(pub_b64 + "\n")


def export_pack(registry: Registry, pids: list[str] | None = None) -> bytes:
    arts = [registry.get(p) for p in (pids or list(registry.active))]
    arts = [a for a in arts if a]
    files = {f"parsers/{a.id}@{a.version}.json": orjson.dumps(a.to_dict(), option=orjson.OPT_INDENT_2) for a in arts}
    manifest = {"format": FORMAT, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "signer": crypto.public_key_b64(), "signer_fingerprint": crypto.fingerprint(),
                "ocsf_version": ocsf.OCSF_VERSION,
                "parsers": [{"id": a.id, "version": a.version, "sha256": a.sha256, "tests": len(a.tests)} for a in arts],
                "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    mbytes = orjson.dumps(manifest, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", mbytes)
        z.writestr("manifest.sig", crypto.sign(mbytes))
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


def run_tests(art: ParserArtifact) -> tuple[int, list[dict]]:
    router = Router({art.id: art}, {"pack-test": art.id})
    failures = []
    for i, t in enumerate(art.tests):
        evs, st = normalize_batch([Item(t["input"], "pack-test", "utf-8", sha256_hex(t["input"]), "test", 0)], router)
        ev = evs[0]
        if st["verify_failed"] or ev["ekalog"]["status"] != "parsed":
            failures.append({"test": i, "reason": "did not parse losslessly"})
            continue
        for path, want in t["expect"].items():
            got = ocsf.get_path(ev, path)
            if got != want:
                failures.append({"test": i, "path": path, "want": want, "got": got})
                break
    return len(art.tests) - len(failures), failures


def import_pack(registry: Registry, data: bytes, trust_signer: bool = False, activate: bool = True) -> dict:
    report = {"ok": False, "checks": [], "parsers": []}

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        mbytes = z.read("manifest.json")
        sig = z.read("manifest.sig").decode()
        manifest = orjson.loads(mbytes)
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        check("readable", False, str(e))
        return report
    signer = manifest.get("signer", "")
    report["signer_fingerprint"] = crypto.fingerprint(signer) if signer else None
    if not check("manifest signature", crypto.verify(mbytes, sig, signer), "Ed25519"):
        return report
    trusted = signer in _trusted()
    if not trusted and trust_signer:
        trust(signer)
        trusted = True
    if not check("trusted signer", trusted, report["signer_fingerprint"]):
        report["needs_trust"] = True
        return report
    arts = []
    for name, want in manifest.get("files", {}).items():
        b = z.read(name)
        if not check(f"hash {name}", hashlib.sha256(b).hexdigest() == want):
            return report
        art = ParserArtifact.from_dict(orjson.loads(b))
        declared, dsig = art.sha256, art.signature
        art.compute_sha()
        if not check(f"artifact {art.id}@{art.version}", art.sha256 == declared, "content hash"):
            return report
        passed, failures = run_tests(art)
        if not check(f"tests {art.id}", not failures, f"{passed}/{len(art.tests)} passed"):
            report["failures"] = failures[:10]
            return report
        art.signature = dsig
        arts.append(art)
    for art in arts:
        art.provenance = {**art.provenance, "imported_from_pack": report["signer_fingerprint"]}
        registry.register(art, activate=activate)
        report["parsers"].append({"id": art.id, "version": art.version, "templates": len(art.templates)})
    report["ok"] = True
    return report
