# EKALOG — One schema for every log

**SIH 2026 · Problem Statement SIH26156 (NTRO) · Universal Log Pre-processing Framework · Team CODERS+1**

EKALOG learns a parser from a sample log file, proves that the normalized OCSF record loses **zero bytes**,
heals itself when a vendor firmware update changes the log format, and its AI **cannot be prompt-injected by
the logs it reads**. Everything runs air-gapped: the only AI is a local model served by Ollama.

```bash
docker compose up          # UI + API → http://localhost:8000   ·   syslog → udp/5514
```

---

## PS requirement matrix

| # | NTRO requirement | How EKALOG satisfies it | Where to see it |
|---|---|---|---|
| a | Preserve complete raw event data, no information loss | Raw bytes written to an append-only vault **before** parsing; every normalized event is rebuilt byte-for-byte from the normalized record alone and its SHA-256 checked against the ingest hash | **Lossless Vault** → Reconstruct |
| b | Extract and parse source-specific attributes | EkaMiner learns templates; every variable becomes a named field (device keys, file headers, documented layouts, local AI for the rest) | **Onboard** → "What EKALOG learned" |
| c | Normalize into a common taxonomy | OCSF 1.3 classes 4001/4002/4003/2004/3002 with activity, disposition and severity mapping | **Parsers** → Schema explorer |
| d | Traceability normalized ↔ original | `ekalog.raw_ref`, `ingest_hash`, `template_id`, `parser{id,version,sha256}` on every event; SHA-256 hash-chain ledger with Ed25519-signed checkpoints | Any event → "Prove it's lossless" |
| e | Plug-and-play onboarding | Drop a sample → signed parser in **5.8–23 s** (measured); `.ekapack` bundles for transfer | **Onboard**, **Parsers** |
| f | Unified visibility | Live pipeline, per-source health, one OCSF stream for all vendors | **Overview** |
| g | SIEM / data-lake integration | NDJSON sink (always on), OpenSearch bulk, Splunk HEC, Parquet export; parser export to Logstash Grok / Vector VRL | **Parsers** → Export |
| h | AI/ML-ready analytics | Flat, typed OCSF + Parquet export; plain-English search | **Ask EKALOG**, Parquet button |
| i | Reduced parser development effort | No regex is written by anyone; the PS cites 1–2 weeks per format | **Benchmarks** → onboarding times |
| j | Air-gapped deployment | Ollama only; non-local LLM endpoints **and Ollama cloud models are refused**; honest egress self-test in the UI | Status bar badges |
| k | Containerized / platform-independent | One image (UI built at image-build time), `docker compose up` | `Dockerfile`, `docker-compose.yml` |

Scope follows the PS: **perimeter devices**. Samples included: Cisco ASA, FortiGate, Palo Alto PAN-OS, pfSense,
Suricata EVE, Zeek conn.log, Check Point (CEF).

## What is different (and what is not)

Public SIH26156 repositories already ship raw vaults, hash chains, Ed25519 signing, local-LLM parser drafting and
drift alerts. EKALOG has those too, but we **don't** claim them as novel. Our differentiators:

1. **Parsers correct by construction.** The LLM never writes a regex. EkaMiner is a Drain-style miner over a
   *delimiter-preserving* lexer (Drain discards separators, so it is lossy by design). The local model only names
   fields, through Ollama structured outputs whose class IDs and OCSF paths are **enums**. Every answer is re-checked:
   a type gate (IP fields only on IP slots), a unique-path invariant and a semantic gate (src ≠ dst).
2. **A proof of losslessness, not a promise.** Reconstruction uses the normalized record only (template +
   field values + verbatim copies of values a type conversion could alter). It is verified on **every** event.
3. **Self-healing drift.** A FortiOS 6 → 7 format change is detected, quarantined (nothing dropped), re-learned,
   hot-swapped as a new signed version and replayed. Measured end to end: **11.3 s**, 600/600 events replayed.
4. **Injection-resistant AI.** Log fields are attacker-controlled. Published work reached **86.7 % attack success**
   against Llama-3.3 and Qwen-3 with injected log content (arXiv:2607.24174). EKALOG's model sees only typed tags and
   sanitized identifiers, never free text. Poisoned templates are withheld, and payloads become detections.
5. **Ask EKALOG.** Plain-English questions become a typed, editable OCSF filter. The model sees the schema only,
   never an event, and values are bound SQL parameters.
6. **Feeds your existing pipeline.** Export any parser as Logstash Grok, Vector VRL or regex.

## Measured results (this repo, dev laptop: 20 logical cores, RTX 4060 8 GB, qwen2.5:7b q4_K_M)

| Metric | Result |
|---|---|
| Round-trip verification | 134,738 events verified, **0 failures** (live run); 14,000/14,000 in tests |
| Held-out coverage | 100 % on all 7 vendors (20 % of each sample never used for learning) |
| Throughput, single core, with verification | **8,214 events/s**; p50 89 µs, p99 296 µs per event |
| Onboarding, sample → signed parser | 5.8 s (Zeek) – 23.0 s (Cisco ASA), including local-LLM labeling |
| Drift self-heal (FortiOS 7) | detected → v1.1.0 hot-swapped → queue replayed in **11.3 s** |
| Injection Guard | 11/11 attack lines detected, 0 false positives on 14,000 clean lines |
| Ask EKALOG | 5/6 example questions produce the exact intended filter (the 6th adds removable extra chips) |
| Test suite | 40 tests (`pytest`) |

Projection, not a measurement: 8.2 k ev/s × 86,400 s ≈ 710 M events/day per core. The data plane is a pure function
over an immutable parser snapshot, so it scales out with `EKALOG_WORKERS` or more containers.

## Run it

### Docker (recommended)
```bash
docker compose up --build        # first run also pulls the model via the one-shot ollama-pull service
open http://localhost:8000       # press "Run the full demo"
```

### Local development (Windows / Linux / macOS)
```bash
# 1. local model
ollama pull qwen2.5:7b-instruct-q4_K_M        # or qwen2.5:3b-instruct-q4_K_M on small machines
# 2. backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m scripts.generate_samples               # deterministic sample data (already committed)
python -m pytest -q tests
python -m uvicorn app.main:app --port 8000
# 3. UI (dev server with hot reload on :3000; or `EKALOG_EXPORT=1 npx next build` to serve it from :8000)
cd ../web && npm install && npm run dev
```

### Air-gapped install
1. On a connected lab machine: `docker compose build && docker compose run --rm ollama-pull`.
2. Export: `docker save ekalog:1.0 ollama/ollama:latest -o ekalog.tar` and copy the `ollama-models` volume
   (or `~/.ollama/models`).
3. At the SOC: `docker load -i ekalog.tar`, restore the model volume, `docker compose up ekalog ollama`.
4. Move parsers between sites as signed `.ekapack` files (**Parsers → Export / Import**). Import re-runs every
   embedded test vector and refuses tampered or failing packs.

Without Ollama, EKALOG still works: the deterministic labeler handles keyed formats (KV, JSON, CEF, headers,
documented CSV layouts), and parsers are marked `labeler: rules`.

## Configuration
All tunables live in `backend/app/config.py` and can be overridden as `EKALOG_<NAME>`. Examples:
`EKALOG_MODEL`, `EKALOG_OLLAMA_URL`, `EKALOG_WORKERS`, `EKALOG_DRIFT_FAIL_RATE`, `EKALOG_INJECTION_THRESHOLD`,
`EKALOG_SINK_OPENSEARCH_URL`, `EKALOG_SINK_SPLUNK_URL` / `EKALOG_SINK_SPLUNK_TOKEN`.

## Repository layout
```
backend/app/core      lexer (delimiter-preserving), templates, OCSF vocabulary, time parsing, Ed25519
backend/app/foundry   EkaMiner, rule labeler, column schemas, sandboxed prompts, Ollama client, Foundry service
backend/app/runtime   executor (hot path, no AI), registry + hot-swap, pipeline, drift, injection, store, search
backend/app/packs     .ekapack export/import       backend/app/sinks   NDJSON / OpenSearch / Splunk HEC / Parquet
web/                  Next.js 15 UI (static export), React Three Fiber hero, Framer Motion
docs/                 build spec (v2 revision in §0.5)
```

## Honest limitations
- Free text with a variable number of *unquoted* words in non-CSV logs produces one template per word count;
  quoted fields, CSV columns and JSON strings are handled as single slots.
- The 7B model occasionally mislabels a rarely used field (e.g. FortiGate `trandisp`). Those labels are visible
  as "Local AI" in the UI and can be corrected by re-onboarding. Byte-level losslessness is never affected.
- The throughput numbers are single-process Python; the Rust reimplementation of the hot path is future work.

Planned license: Apache-2.0 (add a `LICENSE` file before publishing the repository).
