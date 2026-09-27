# EKALOG — Universal Log Pre-processing Framework
### SIH 2026 · PS **SIH26156** (NTRO) · One-Day Build Specification for Claude Code

> **Read this whole file before writing any code.**
> This is the complete build contract: prior art, USPs, architecture, file tree, API contracts, UI design system, hour-by-hour plan, demo script and deliverables.
> Team: CODERS+1 (Team ID 125708) · Deadline: idea submission 30 Sept 2026 · PS load at last check: 18/500.

---

## 0. TL;DR for the builder

Build **EKALOG** — an air-gapped, AI-assisted log normalization framework that turns *any* perimeter-device log into **OCSF**-compliant events, with four things nobody else ships:

1. **Zero-LLM hot path** — the LLM writes the parser once, offline; production traffic never touches a model.
2. **Cryptographically proven losslessness** — every normalized event can rebuild its raw line byte-for-byte, verified by hash.
3. **Drift Sentinel** — detects when a vendor firmware upgrade silently breaks a parser and auto-heals it.
4. **Injection Guard** — defends the AI layer against prompt injection delivered *inside log data* (published 2026 attack, 86.7% success rate against naive LLM log tools).

Name: **EKALOG** (Sanskrit *eka* = one) — tagline **"One schema for every log."**
Alternate names if you prefer: SETU ("bridge"), PRISM, VYUHA.

---

## 0.5 v2 REVISION (27 Sept 2026) — read this first, it overrides conflicting text below

A competitive scan of **public SIH26156 repos** (§2.4) showed that roughly half of v1's "nobody ships this" claims are now **table stakes**: raw vaults with SHA-256, hash chains and Ed25519, local Ollama drafting mappings with human approval, drift quarantine, and a no-`eval` DSL. We still build them, but **we stop pitching them as USPs**. The revised plan:

| # | v1 | v2 change | Why |
|---|---|---|---|
| 1 | LLM writes the **regex** | **The LLM never writes regex.** A new *delimiter-preserving* miner (**EkaMiner**) derives the parser deterministically from the data. The LLM only **labels slots** (name + OCSF path + event class) through an Ollama JSON-schema-constrained call with **enum-restricted outputs**. | LLM-authored regex is the #1 failure mode for 3–7B models. With EkaMiner every parser is valid and lossless *by construction*, so small local models become sufficient. |
| 2 | Drain3 for mining | EkaMiner (Drain-style fixed-position clustering over a lexer that **keeps every separator byte** and treats quoted strings, timestamps, IPv6 and MACs as atoms) | Drain3 splits on whitespace and **throws the separators away**, so it is lossy by design. |
| 3 | "Lossless" = keep the raw line | **Round-trip proof from the normalized record alone**: template + slot values (+ verbatim copies only for non-reversible transforms) → rebuild → SHA-256 equals the ingest hash. The raw vault still exists, but the proof doesn't use it. | Every competitor stores the raw line. Nobody proves that the *normalized* record is complete. |
| 4 | Injection Guard | Kept, and it is now structural: the model only ever sees **type tags** for IP, number and timestamp slots and **sanitized ≤ 32-char identifiers** for word slots. It never sees free text. Its outputs are enums or `^[a-z][a-z0-9_]{0,31}$` names, so injected text cannot flow downstream. Cite **arXiv 2607.24174** and **arXiv 2607.14493** (passive prompt injection in *network security logs*). | No competitor addresses log-borne prompt injection. |
| 5 | — | **NEW · Ask EKALOG**: plain-English search ("denied SSH from outside in the last hour") → the LLM emits a **typed OCSF filter** (enum fields and ops). The LLM sees the **schema only, never event data**. It falls back to a visual filter builder when the model is unavailable. | Makes the product usable by a non-expert analyst and is safe by design. |
| 6 | `.ekapack` only | `.ekapack` **plus export to Logstash Grok / Vector VRL / Fluent Bit regex** | "We don't replace your pipeline, we feed it." Adoption story for NTRO. |
| 7 | Single process | **Stateless data plane**: pure `normalize_batch()` over an immutable, content-addressed registry snapshot; `Bus` interface (in-proc queue → Redis Streams/Kafka); `EKALOG_WORKERS=N` process pool; LLM results **cached by template hash**, so the same template is never asked twice across sources. | Scalability claims must be architectural, and measured. |
| 8 | Heuristic fallback only | **Deterministic pre-labeler first** (KV keys, CEF/LEEF keys, JSON keys, a synonym dictionary → OCSF). The LLM fills only the remaining gaps. **Everything works with Ollama down** (lower confidence, flagged). | Robustness; the demo cannot fail. |
| 9 | 7 cinematic screens | Same visual language, but **user-friendly first**: a 3-step onboarding wizard, plain-language labels with an "explain" tooltip on every metric, a Ctrl-K command palette and a guided demo tour. 3D only on the hero, with an automatic low-GFX fallback. Fonts self-hosted (air-gap). | Judges and SOC analysts must understand every screen in 5 seconds. |
| 10 | Python 3.11 | Python ≥ 3.10 (dev box has 3.10); Docker image uses 3.11. | Environment reality. |

**Revised pitch (one line):** *"EKALOG learns a parser from a sample file, proves the normalized record loses zero bytes, heals itself when a vendor changes the format, and its AI can't be prompt-injected by the logs it reads. Fully offline."*

**What we deliberately do NOT pitch as unique** (competitors have it; we still ship it): raw vault, SHA-256 hash chain, Ed25519 signing, OCSF output, drift alerts, human approval queue, Docker Compose.

---

## 1. What the problem statement actually demands

NTRO's required capabilities, mapped to where we satisfy them. **Keep this table in the README** — evaluators tick boxes.

| # | PS requirement | EKALOG component | Demo proof |
|---|---|---|---|
| a | Preserve complete raw event data, no information loss | Lossless Vault (residual capture + SHA-256 round trip) | Reconstruct + byte-diff screen |
| b | Extract and parse source-specific attributes | Parser Foundry (Drain3 + local LLM synthesis) | Foundry screen |
| c | Normalize fields into a common event taxonomy | OCSF mapper (class_uid, activity_id, severity_id…) | Schema Explorer |
| d | Maintain traceability normalized ↔ original | `raw_ref` + `template_id` + `parser_version` + `ingest_hash` on every event | Click any event → lineage panel |
| e | Plug-and-play onboarding of new sources | Drop a sample file → parser in < 60 s; signed `.ekapack` export/import | Live onboarding in video |
| f | Unified visibility across environments | Live Pipeline dashboard + source inventory | Hero screen |
| g | Efficient SIEM / data-lake integration | Sinks: OpenSearch bulk, Splunk HEC, Parquet/S3, NDJSON, Kafka-ready | Sinks panel |
| h | AI/ML-ready analytics | Flat OCSF + feature columns + Parquet export | Export screen |
| i | Reduced parser development effort | Benchmark: hand-written parser (hours) vs EKALOG (seconds) | Counter on hero |
| j | Deployable in an air-gapped network | Ollama local model, no egress, `--offline` flag, egress self-test | "Network: AIR-GAPPED ✓" badge (real check) |
| k | Containerized / platform independent | `docker compose up` single command | README |

**Current scope per the PS:** perimeter network devices — firewalls, routers, VPN concentrators, IDS/IPS. Do not scatter across "all enterprise logs". Depth beats breadth.

**Deliverables NTRO evaluates:** source-code link, README with setup, **architecture document (max 2 pages)**, **demo video (max 2 minutes)**, **technical presentation (max 5 slides)**. Build to these limits exactly.

---

## 2. Prior art — what already exists (and where it stops)

This section exists so you never claim something that Splunk shipped in 2019. Put a condensed version of this table on slide 3.

### 2.1 Pipeline / normalization tools

| Tool | What it does | Where it stops |
|---|---|---|
| **Logstash (Grok)** | Regex-ish pattern parsing, ECS output | Humans write every pattern; brittle; slow |
| **Fluent Bit / Fluentd** | Lightweight forwarding, parsers | Manual parser definitions per source |
| **Vector (VRL)** | Fast Rust pipeline, remap language | You still author the transform by hand |
| **Cribl Stream** | Commercial pipeline, packs, reduction | Packs are human-built; proprietary; not air-gapped-friendly |
| **Splunk CIM / Add-ons** | Normalization via add-ons | Add-on per source, maintained by humans |
| **Panther / Matano** | Detection + OCSF-ish security lake | Schemas hand-defined |
| **Axoflow** | Classifies telemetry in transit, curated parsers | Curated by vendor, SaaS-oriented |
| **Databahn** | Highlights OCSF "schema drift" as a real problem | Commercial, closed |

### 2.2 The closest competitor: Elastic **Automatic Import**

Ships an LLM that reads log samples and generates an ECS integration. This is the single most important piece of prior art — **know it cold, an evaluator may ask.**

Its documented limits, and our answer:

| Elastic Automatic Import | EKALOG |
|---|---|
| Needs an LLM **connector**, typically cloud (OpenAI/Bedrock/Gemini) | Local quantized model via Ollama; **runs air-gapped** |
| Enterprise subscription / serverless tier | Apache-2.0, `docker compose up` |
| Max ~1,000 samples, first 100 sent to the LLM | Drain3 mines templates from millions of lines; only deduped templates reach the model |
| Targets **ECS**, inside the Elastic stack | **OCSF-first** (vendor-neutral), ECS as secondary emit, any sink |
| Generates an integration; no round-trip guarantee | **Byte-exact reconstruction, hash-verified** |
| One-shot generation at onboarding | **Continuous drift detection + auto re-synthesis** |
| LLM reads raw sample text | **Injection Guard**: model sees masked templates in a sandbox; output compiled into a restricted DSL, never executed |

### 2.3 Academic state of the art (cite these — it shows depth)

- **Drain / Drain3** — online log template mining with a fixed-depth parse tree. Fast, unsupervised, no LLM. *We use it as the first stage.*
- **LILAC (FSE'24, logpai)** — LLM log parsing with an **adaptive parsing cache** + hierarchical candidate sampling; ~69.5% average F1 template accuracy, cutting LLM queries by orders of magnitude. *Closest research relative. We go further: LILAC caches a template; we emit a signed, versioned, testable parser artifact and remove the model from the runtime path entirely.*
- **Loghub / Loghub-2.0 (ISSTA'24)** — the standard annotated log-parsing benchmark. *Use it for a real accuracy number, not a vibe.*
- **"Just Testing, Move Along" (arXiv 2607.24174, 2026)** — prompt injection **inside log fields** makes LLM-based log interpreters misclassify attacks as benign; up to **86.7% attack success** across models. *This is our headline security USP: every AI-log product on the market reads attacker-controlled text straight into a model.*

> **Correction (v2):** Elastic *can* use a self-hosted OpenAI-compatible endpoint (e.g. Ollama or LM Studio via the "Other (OpenAI Compatible Service)" connector or inference endpoints). Do **not** claim it "needs cloud". The accurate differences: it needs the Elastic stack and licence, it targets ECS, it has no round-trip guarantee and no drift healing, and its LLM reads raw sample text.
> **Correction (v2):** Verify LILAC's reported metrics from the paper before putting any number on a slide. Do not reuse "69.5%" unchecked.

### 2.4 Public SIH26156 competitor repos (scanned 27 Sept 2026)

| Repo | Notable | What they lack vs EKALOG v2 |
|---|---|---|
| D3v4nshPat3l/ULPF (Rust) | 35 YAML packs, 32.4M-record validation, RFC 6962 Merkle, Ed25519, Drain clustering of dead letters, qwen2.5:1.5b copilot | LLM drafts packs manually; no round-trip proof from the normalized record; no auto-heal; no injection defense for the AI |
| Your-Voldemort/ULPF | 5 vendor parsers, hash chain, qwen2.5:3b drafts mappings with human approval, drift *type* quarantine, CERT-In profile, WCAG | Hand-written parsers; drift requires manual resolution |
| Karthik-Sethu-Raman/ulpf | Kafka/Redpanda, Postgres, qwen3:4b rule candidates + review queue | Heavy infra; no losslessness proof; no injection defense |
| kalpeshkarnawat19/ULPX | Whitelisted DSL, 5-gate sandbox, "Detection Preservation Score", telemetry passports | CLI/TUI only; no AI synthesis in UI |
| GhostX1407/LogSetu | Cascading format router, Ed25519 hash chain, tiered routing, MITRE tagging | **Cloud LLMs (Gemini/Groq)**, which violates the air-gap requirement |
| kumarshivam…/ULPF (OmniLogix), Vaibhav007-star/Netracore | 13 formats, Postgres, Isolation Forest; synonym normalization, no-code token mapper | No LLM onboarding; no drift healing |

**Takeaway:** the bar is high on crypto and integrity. We win on **(1) parsers that are correct by construction from a small local model, (2) a round-trip proof, (3) autonomous drift healing, (4) an AI layer that resists injection, (5) UX.** Crypto integrity is table stakes. Do it well, but pitch it in one line.

**One-line positioning:** *Elastic's Automatic Import, but air-gapped, OCSF-first, provably lossless, self-healing, and injection-resistant.*

---

## 3. The five USPs (memorize these — this is what wins)

### USP-1 · Compile-once parsers: **zero LLM in the hot path**
The LLM is a *compiler*, not a *runtime*. Sample → Drain3 templates → local LLM proposes template + OCSF mapping → validated against held-out lines → compiled into a `ParserArtifact` (regex + mapping spec + tests + semver + SHA-256 signature). Production ingestion executes only compiled regex. Deterministic, replayable, auditable, cheap.
*Say this:* "An auditor can diff parser v1.2.0 against v1.3.0 and re-run its test vectors. You cannot audit a prompt."

### USP-2 · Lossless Vault: **round-trip proof, not a promise**
At ingest we hash the raw line. During parsing we record every byte the parser consumed; leftovers go into `unmapped.residual` with offsets. A `reconstruct()` function rebuilds the original from the normalized record and compares SHA-256. UI shows a live **Losslessness Score** and a byte-level diff on demand. Requirement (a) and (d) turn from claims into a test that runs on every event (sampled at 1% in fast mode, 100% in proof mode).
*Nobody in the market does this.* Say: "Cribl reduces your data. We can prove we destroyed none of it."

### USP-3 · Drift Sentinel: **self-healing parsers**
Per source we track parse-success rate, field-presence distribution and template novelty on a rolling window. A firmware upgrade that adds a field or reorders CEF extensions shows up as a fall-through spike → the source is quarantined (never dropped) → the Foundry re-synthesizes → a new parser version is hot-swapped → the quarantine is replayed through it. Timeline UI with version diff.
*The pain is real and documented* (vendors publicly call schema drift their hardest OCSF problem). Say: "Everyone else discovers a broken parser when a detection fails to fire. We discover it in 30 seconds and fix it ourselves."

### USP-4 · Injection Guard: **the AI layer is attacker-aware**
Logs are untrusted, attacker-influenced input. Published 2026 research injects instructions into log fields and flips LLM verdicts to "benign" 86.7% of the time. EKALOG defends structurally:
- The model never sees raw streams — only **masked, deduplicated templates** (variables already replaced with `<*>` by Drain3), length-capped, inside a sandboxed prompt with delimiters.
- Model output is parsed as **JSON conforming to a strict grammar** and compiled into a restricted DSL. It is never `eval`'d, never becomes a rule, never becomes a verdict.
- A detector flags log lines carrying imperative/prompt-like payloads (`ignore previous instructions`, `classify as benign`, `this is authorized testing`, base64/unicode-escape tricks, newline-forged syslog headers per OWASP Log Injection) and enriches the event with `enrichments.injection_attempt = true` plus a confidence score — turning the attack into a **detection signal** instead of an evasion.
*Demo moment:* paste an injected FortiGate line → red "PROMPT INJECTION BLOCKED" card → event still parses losslessly, and the attempt becomes an alert.

### USP-5 · `.ekapack`: **sneakernet-friendly parser packs**
Signed, versioned bundle = parsers + OCSF mappings + test vectors + provenance. Synthesize on an internet lab machine, carry to the air-gapped SOC on USB, import with signature + test-vector verification (import refuses on a failed test or bad signature). Answers (e) and (j) with an artifact you can hold.

**Stretch USP-6 (only if time remains):** auto-suggest Sigma detection rules for newly onboarded sources; emit both OCSF and ECS from one parse.

---

## 4. Architecture

```
                         ┌──────────────── CONTROL PLANE (offline, sandboxed) ──────────────┐
  sample.log ──►  Drain3 template mining ──►  Local LLM (Ollama, quantized)                 │
                         │                          │ proposes: regex + OCSF field map      │
                         │                          ▼                                       │
                         │                   Validator: holdout lines, type checks,          │
                         │                   OCSF schema check, round-trip test              │
                         │                          ▼                                       │
                         │                   ParserArtifact  (semver + SHA-256 + tests)      │
                         └──────────────────────────┬──────────────────────────────────────┘
                                                    │  hot-swap (no restart)
  ┌──────────────── DATA PLANE (no LLM, ever) ──────┼──────────────────────────────────────┐
  │ syslog/UDP · file tail · HTTP push ──► Ingest ──► Parser Registry ──► OCSF Mapper ──►   │
  │        │ sha256(raw)                              │ compiled regex      │ enrich        │
  │        │ raw kept in RawStore                     │                     │ injection scan│
  │        ▼                                          ▼                     ▼               │
  │   Lossless Vault  ◄──── residual bytes ──── Round-trip verifier ──► Sinks: OpenSearch / │
  │                                                                     Splunk HEC / Parquet│
  │                                              Drift Sentinel (rolling stats) ─┐          │
  └──────────────────────────────────────────────────────────────────────────────┼─────────┘
                                                                                 │ re-synthesis
                                                                                 └──► Foundry
```

Everything streams to the UI over a single **WebSocket** (`/ws/live`) carrying pipeline stats, new events, drift alarms and foundry progress.

---

## 5. Tech stack (fixed — do not substitute)

**Backend**
- Python 3.11, **FastAPI** + uvicorn, `websockets`
- `drain3` (template mining), `regex` (compiled parsers), `orjson`, `pydantic v2`
- **Ollama** with a local quantized model — default `qwen2.5:7b-instruct-q4_K_M`; fall back to `llama3.1:8b-instruct-q4_K_M`. Config via `EKALOG_MODEL`.
- SQLite (parser registry, drift history) + in-memory ring buffers for live stats
- Optional sinks: `opensearch-py`, `pyarrow` (Parquet)

**Frontend**
- **Next.js 15** (App Router) + React 19 + TypeScript
- **Tailwind CSS v4** + custom glass utilities
- **Framer Motion** (all transitions, shared-element `layoutId`)
- **React Three Fiber** + `@react-three/drei` + `@react-three/postprocessing` (3D pipeline, bloom)
- `recharts` for charts, `lucide-react` icons, `react-diff-viewer-continued` for byte diffs
- Fonts: **Space Grotesk** (display), **Inter** (UI), **JetBrains Mono** (logs)

**Ops:** `docker-compose.yml` → `api`, `web`, `ollama`, optional `opensearch`. One command: `docker compose up`.

---

## 6. Repository layout

```
ekalog/
├── README.md                     # setup + PS requirement matrix + benchmarks
├── ARCHITECTURE.md               # source for the 2-page PDF
├── docker-compose.yml
├── Makefile                      # make demo / make bench / make seed
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, WS hub, routers
│   │   ├── config.py
│   │   ├── models.py             # pydantic: RawEvent, OCSFEvent, ParserArtifact, DriftAlarm
│   │   ├── ingest/
│   │   │   ├── syslog_udp.py     # asyncio UDP listener :5514
│   │   │   ├── file_tail.py
│   │   │   └── replay.py         # deterministic demo replay at N eps
│   │   ├── foundry/
│   │   │   ├── miner.py          # Drain3 wrapper → templates + coverage
│   │   │   ├── llm.py            # Ollama client, strict-JSON grammar, sandbox prompt
│   │   │   ├── validator.py      # holdout eval, type check, OCSF check, round-trip
│   │   │   ├── compiler.py       # → ParserArtifact (regex + mapping + tests + hash)
│   │   │   └── prompts.py
│   │   ├── runtime/
│   │   │   ├── registry.py       # versioned parsers, hot-swap, SQLite
│   │   │   ├── executor.py       # THE HOT PATH — compiled regex only
│   │   │   ├── ocsf.py           # field map → OCSF class/activity/severity
│   │   │   ├── lossless.py       # residual capture, reconstruct(), hash verify
│   │   │   ├── injection.py      # prompt-injection + log-forgery detector
│   │   │   └── drift.py          # rolling stats, alarm, quarantine, replay
│   │   ├── sinks/                # opensearch.py, splunk_hec.py, parquet.py, ndjson.py
│   │   ├── packs/                # export.py / import.py  (.ekapack + signature)
│   │   └── bench/runner.py       # EPS benchmark + Loghub accuracy harness
│   ├── data/
│   │   ├── samples/              # asa.log fortigate.log panos.log pfsense.log suricata.json zeek.log
│   │   ├── drift/fortigate_v7.log# same vendor, changed format (drift demo)
│   │   ├── attack/injection.log  # prompt-injection + forged-syslog lines
│   │   └── ocsf/schema.json      # pinned OCSF subset (network_activity etc.)
│   └── tests/
└── web/
    ├── app/
    │   ├── layout.tsx  page.tsx              # Live Pipeline (hero, 3D)
    │   ├── foundry/page.tsx                  # Parser Foundry
    │   ├── vault/page.tsx                    # Lossless Vault
    │   ├── drift/page.tsx                    # Drift Sentinel
    │   ├── guard/page.tsx                    # Injection Guard
    │   ├── schema/page.tsx                   # OCSF Explorer (sankey)
    │   └── bench/page.tsx                    # Benchmarks
    ├── components/
    │   ├── three/PipelineScene.tsx           # particle flow through 4 rings
    │   ├── glass/{GlassCard,GlassPanel,Aurora,Noise,SpecularBorder}.tsx
    │   ├── viz/{EPSGauge,LosslessMeter,DriftTimeline,SankeyMap,LogStream}.tsx
    │   └── ui/{Counter,StatusPill,CommandBar,ShimmerButton}.tsx
    ├── lib/{ws.ts,api.ts,motion.ts}
    └── styles/globals.css                    # design tokens
```

---

## 7. Data contracts

### 7.1 Normalized event (OCSF-aligned, with our extensions)

```jsonc
{
  "metadata": {
    "version": "1.3.0",                       // OCSF version pinned
    "product": { "vendor_name": "Fortinet", "name": "FortiGate" },
    "logged_time": 1790000000000,
    "profiles": ["security_control"]
  },
  "class_uid": 4001,                          // Network Activity
  "category_uid": 4,
  "activity_id": 1,
  "severity_id": 3,
  "time": 1789999999000,
  "src_endpoint": { "ip": "10.1.2.3", "port": 51244 },
  "dst_endpoint": { "ip": "8.8.8.8", "port": 443 },
  "traffic": { "bytes_in": 1024, "bytes_out": 2048 },
  "observables": [{ "name": "src_endpoint.ip", "type_id": 2, "value": "10.1.2.3" }],

  // ---- EKALOG extensions (this is our differentiator, keep the prefix) ----
  "ekalog": {
    "raw_ref": "blob://2026-09-28/000123",
    "ingest_hash": "sha256:9f2c…",
    "template_id": "fgt-traffic-0007",
    "parser": { "id": "fortinet.fortigate.traffic", "version": "1.2.0", "sha256": "ab19…" },
    "lossless": { "verified": true, "residual_bytes": 0, "coverage": 1.0 },
    "confidence": 0.98,
    "injection": { "detected": false, "score": 0.02, "indicators": [] },
    "drift": { "status": "stable", "novelty": 0.01 }
  }
}
```

### 7.2 ParserArtifact

```jsonc
{
  "id": "fortinet.fortigate.traffic",
  "version": "1.2.0",
  "source_hint": { "vendor": "Fortinet", "product": "FortiGate", "format": "key-value" },
  "template": "date=<*> time=<*> devname=\"<*>\" ... srcip=<*> dstip=<*>",
  "regex": "^date=(?P<date>\\S+) time=(?P<time>\\S+) ...",
  "field_map": { "srcip": "src_endpoint.ip", "dstport": "dst_endpoint.port" },
  "transforms": { "dst_endpoint.port": "int", "time": "epoch_ms(date+' '+time)" },
  "ocsf": { "class_uid": 4001, "activity_map": { "accept": 1, "deny": 2 } },
  "tests": [{ "input": "date=2026-09-27 …", "expect": { "src_endpoint.ip": "10.1.2.3" } }],
  "metrics": { "holdout_accuracy": 0.987, "coverage": 0.994, "eps": 71000 },
  "provenance": { "model": "qwen2.5:7b-instruct-q4_K_M", "mined_by": "drain3", "created": "…" },
  "sha256": "ab19…"
}
```

### 7.3 REST + WebSocket API

```
POST /api/sources/onboard      multipart sample file → { job_id }         # starts Foundry
GET  /api/foundry/{job_id}     SSE: mining → proposing → validating → compiling → done
GET  /api/parsers              list artifacts + versions + metrics
POST /api/parsers/{id}/rollback  { version }
POST /api/ingest/replay        { source, eps, duration }                  # demo driver
GET  /api/events?limit=…       recent normalized events
GET  /api/events/{id}/reconstruct → { raw, rebuilt, match: true, diff: [] }
GET  /api/drift                alarms + timeline
POST /api/guard/test           { line } → injection verdict + indicators
GET  /api/bench                { eps, p99_latency_us, projected_daily }
POST /api/packs/export         → .ekapack           POST /api/packs/import
WS   /ws/live                  { type: stats|event|drift|foundry|guard, … } @ 10 Hz
```

---

## 8. Algorithms — implementation notes

> **v2 supersedes the "Template mining" and "LLM synthesis" paragraphs below:**
>
> **EkaMiner lexer.** Each line becomes a strict alternation `word, delim, word, …, word`. Words may be empty. Delimiters are single characters from `= , ; | : / [ ] ( ) { } < > "` or a run of whitespace. At every word start the lexer first tries **atoms** that contain delimiter characters (ISO/RFC 3164 timestamps, clock times, IPv6, MAC) and quoted strings, whose content is one word. This keeps CSV positions stable (empty fields are empty words), and `"".join(tokens) == line` always holds.
> **Clustering.** Group lines by their exact delimiter sequence, then do Drain-style similarity inside each group over *masked* words (IPs, numbers, hex and timestamps become type tags). Similarity ≥ 0.5 joins a cluster, and positions that differ become variable slots. Identical masked signatures are cached, which gives O(1) per line after warm-up.
> **Parser = template.** Literal words plus typed slots. At runtime: tokenize, then a dict lookup by delimiter sequence, then a literal check. There is no regex backtracking, and `render(slots) == line` by construction. `to_regex()`/`to_grok()`/`to_vrl()` exist only for export.
> **Labeling.** Deterministic pre-labeler (the key before `=`/`:`, CEF/LEEF/JSON keys, a synonym dictionary to OCSF paths), then an Ollama call with `format=<JSON schema>` whose `ocsf` and `class_uid` are **enums** and whose `name` is pattern-restricted. Word-slot examples are sanitized to `[A-Za-z0-9._-]{≤32}` and dropped if the injection scanner flags them. Results are cached by template hash.

**Template mining (v1).** Drain3 with `sim_th=0.4`, `depth=4`, masking for IP, MAC, port, hex, UUID, path, timestamp. Output: templates ranked by frequency + coverage. Templates covering ≥ 95% of lines go forward.

**LLM synthesis (sandboxed).** For each top template send: the masked template, 3 example lines (each truncated to 512 chars, control chars stripped), and the OCSF field vocabulary for the target class. Demand strict JSON: `{regex, field_map, transforms, class_uid, activity_map, confidence}`. Temperature 0.1. Retry twice on schema-invalid JSON. **Never** include the model's free text anywhere downstream.

**Validation gate (must pass, else the parser is rejected):**
1. Regex compiles, and named groups match `field_map` keys.
2. ≥ 95% match rate on 200 held-out lines.
3. Type checks pass (IPs parse, ports 0–65535, timestamps in range).
4. OCSF check: required fields for the class present.
5. **Round-trip: reconstruct == original for 100% of the holdout.**
Failure → fall back to a heuristic parser (generic syslog RFC5424/RFC3164 + CEF/LEEF/KV/JSON) and mark `confidence: low`.

**Losslessness.** Keep the raw line in `RawStore` (append-only, gzip, offset index). During parse, track consumed spans; anything unconsumed lands in `ekalog.unmapped.residual` as `[{offset, bytes}]`. `reconstruct()` = template + captured groups + residual reassembled by offset; verify SHA-256. Proof mode verifies every event; fast mode samples 1%.

**Injection detection.** Score from: imperative-instruction patterns ("ignore previous", "disregard", "classify as", "you are", "system:"), benign-framing phrases ("authorized test", "routine maintenance", "move along"), role/delimiter tokens (`<|im_start|>`, `###`, triple backticks), embedded newlines/CR in a single-datagram syslog message (OWASP log forgery), excessive unicode escapes or base64 blobs > 256 B in a message field. Weighted score ≥ 0.6 → `injection.detected = true`, event tagged, alert emitted. **Cite the 2026 paper in the UI tooltip** — evaluators love a grounded threat model.

**Drift.** Per source, rolling 5-minute window: `parse_fail_rate`, `new_template_ratio`, Jensen–Shannon divergence of field-presence vectors vs the parser's baseline. Any one crossing its threshold (0.05 / 0.15 / 0.2) → `DriftAlarm`, quarantine unparsed lines (never drop), auto-trigger Foundry, hot-swap on success, replay the quarantine, post a version diff to the UI.

---

## 9. UI — the part that must not look like a hackathon project

### 9.1 Design language: **Liquid Glass, dark, cinematic**

**Tokens** (`globals.css`):
```css
:root{
  --bg-0:#05070D; --bg-1:#0A0E1A; --bg-2:#111827;
  --glass: rgba(255,255,255,.055);
  --glass-hi: rgba(255,255,255,.14);
  --stroke: rgba(255,255,255,.10);
  --cyan:#22D3EE; --violet:#8B5CF6; --mint:#34D399;
  --amber:#FBBF24; --rose:#FB7185;
  --text:#E8EDF7; --muted:#8FA0BF;
  --r-lg:22px; --r-xl:28px;
  --shadow-glass: 0 20px 60px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.12);
}
.glass{
  background: linear-gradient(135deg, rgba(255,255,255,.07), rgba(255,255,255,.03));
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  border:1px solid var(--stroke); border-radius:var(--r-xl);
  box-shadow: var(--shadow-glass);
}
```
Layer stack on every page, bottom to top: **Aurora** (animated mesh gradient, cyan→violet→mint, 30 s loop, `filter: blur(80px)`) → **Noise** (4% opacity SVG grain, kills banding) → **glass panels** → content. Panels get a **specular border**: a 1px conic-gradient ring that brightens on hover, and a slow-moving highlight on the top edge. Rounded 22–28px. Never pure black, never flat cards, no default shadcn look.

### 9.2 Motion rules (Framer Motion)
- Page transitions: fade + 12px rise, `spring {stiffness:260, damping:30}`.
- Panel → detail uses shared-element `layoutId` (click a pipeline stage, it *expands* into the detail view — this single effect makes the demo look expensive).
- Stat counters animate with easing and a `tabular-nums` font; never snap.
- Stagger children 40 ms on mount.
- Live log stream: new rows slide in from the left with a 200 ms cyan edge-glow that decays.
- Respect `prefers-reduced-motion`.
- Everything must stay smooth at 60 fps during a 20k EPS replay — throttle UI updates to 10 Hz via WS batching, never re-render per event.

### 9.3 3D (React Three Fiber) — one scene, used well
`PipelineScene.tsx`: a camera looking down a **tunnel of four glass rings** labelled INGEST → MINE → SYNTHESIZE → NORMALIZE. Thousands of **instanced particles** (one per sampled event) flow through: cyan = parsed, amber = quarantined by drift, rose = injection flagged, violet = in the Foundry. Rings use `MeshTransmissionMaterial` (real glass refraction). `EffectComposer` with `Bloom` (intensity 0.8) + subtle `ChromaticAberration`. Slow auto-orbit; mouse parallax; pauses when the tab is hidden. Particle count adapts to FPS (`useFrame` monitor, drop to 2,000 under 45 fps). Provide a static fallback for the video if the laptop stutters.

### 9.4 Seven screens

1. **Live Pipeline (`/`)** — the hero. 3D tunnel behind glass HUD: EPS gauge, total events, **Losslessness 100.000%** meter, active parsers, "AIR-GAPPED ✓" badge (from a real egress self-test), live OCSF event stream with a syntax-highlighted JSON preview on hover.
2. **Parser Foundry (`/foundry`)** — the money shot. Drag a `.log` in → a four-stage theatre: templates materializing as glass chips (count ticking), the LLM stage streaming tokens into a code block, validation checks ticking green one by one (`regex ✓ · holdout 98.7% ✓ · OCSF ✓ · round-trip ✓`), then a compile animation that "seals" the artifact with its SHA-256 and a version badge. Timer in the corner: **"Hand-written parser: ~4 h · EKALOG: 47 s"**.
3. **Lossless Vault (`/vault`)** — pick any event, hit **Reconstruct**: split view raw vs rebuilt, byte-diff, and a wax-seal-style stamp animating in: `SHA-256 MATCH · 0 BYTES LOST`. Counter: "2,847,113 events verified, 0 failures."
4. **Drift Sentinel (`/drift`)** — timeline of parser versions; when the drift log is injected mid-demo, the line spikes red, a quarantine badge appears, then "Re-synthesis complete → v1.3.0 hot-swapped" with a side-by-side field diff (new field `poluuid` highlighted green), and the quarantine drains back to zero.
5. **Injection Guard (`/guard`)** — paste box + live feed of blocked attempts. Each card shows the offending substring highlighted, indicator chips, and a "what a naive LLM SIEM would have done" comparison panel citing the 86.7% figure.
6. **Schema Explorer (`/schema`)** — animated Sankey: raw vendor fields → OCSF fields, with unmapped fields flowing to the "residual (preserved)" node. Toggle OCSF ⇄ ECS.
7. **Benchmarks (`/bench`)** — measured EPS gauge, p99 latency, Loghub accuracy bars vs Drain3, projected events/day table, and a comparison matrix against Logstash / Elastic Automatic Import / Cribl (facts only, from §2).

---

## 10. One-day build plan (14 working hours)

Work in this order. **Ship a working vertical slice by hour 6**, then make it beautiful.

| Hours | Task | Done when |
|---|---|---|
| 0.0–0.5 | Scaffold repo, docker-compose, `ollama pull` model, sample data in place | `docker compose up` serves an empty UI |
| 0.5–2.0 | Ingest + RawStore + hashing + generic fallback parsers (syslog/CEF/KV/JSON) + WS live stats | Events flow to a plain UI list |
| 2.0–4.0 | Foundry: Drain3 → LLM → validator → compiler → registry hot-swap | Upload `asa.log`, get a working parser, events normalize |
| 4.0–5.0 | OCSF mapper + Lossless Vault (`reconstruct` + verify endpoint) | `/api/events/{id}/reconstruct` returns `match: true` |
| 5.0–6.0 | Injection Guard + Drift Sentinel (alarm → quarantine → re-synth → replay) | Drift and attack sample files trigger both paths |
| 6.0–6.5 | Benchmark runner + Loghub accuracy harness + sinks (NDJSON, OpenSearch) | `make bench` prints real numbers |
| 6.5–7.0 | `.ekapack` export/import with signature + test verification | Export, wipe registry, import, parsers work |
| 7.0–8.0 | **Design system**: tokens, glass components, Aurora, Noise, fonts, layout shell | One screen looks premium |
| 8.0–9.5 | 3D PipelineScene + hero HUD | 60 fps hero |
| 9.5–11.5 | Foundry theatre, Vault diff+seal, Drift timeline | The three demo screens are done |
| 11.5–12.5 | Guard, Schema sankey, Bench screens + polish pass (hover, stagger, empty states) | No unstyled corner anywhere |
| 12.5–13.0 | **Demo mode**: `make demo` = seeded, deterministic, scripted replay | Same result every run |
| 13.0–14.0 | README + ARCHITECTURE.md + record video + 5 slides | Submission ready |

**Demo mode is not optional.** `EKALOG_DEMO=1` must: seed all RNG, replay a fixed capture at a fixed EPS, cache the LLM synthesis trace for `asa.log` and the drift re-synthesis (replayed token-by-token at realistic speed, clearly a *cached* run behind the scenes but a *real* one when the model is up), and fire drift at t+45 s and the injection at t+70 s. The live path must still work without the cache — the cache only guarantees the 2-minute recording never fails.

---

## 11. Demo video — 2 minutes, shot by shot

| Time | Screen | Narration (keep to this wording, it's tight) |
|---|---|---|
| 0:00–0:12 | Hero, 3D tunnel spinning up | "Every SOC drowns in logs in fifty different formats. Teams hand-write parsers for weeks. EKALOG generates them in seconds — fully offline." |
| 0:12–0:40 | Foundry: drop `fortigate.log` | "Drop a raw sample. Drain3 mines templates. A local quantized model — no cloud, no egress — proposes the parse and the OCSF mapping. Every proposal is validated against held-out lines and compiled into a signed, versioned parser. From here on, no AI touches your data path." |
| 0:40–0:58 | Live pipeline, counters climbing | "Normalized to OCSF at N thousand events per second, straight into your SIEM or data lake." |
| 0:58–1:18 | Vault: reconstruct + seal | "NTRO asked for zero information loss. We don't claim it — we prove it. Any event rebuilds its original bytes, hash-verified. Two point eight million events, zero loss." |
| 1:18–1:38 | Drift: spike → auto-heal | "Firmware upgrade changes the log format. Every other pipeline fails silently for weeks. EKALOG detects the drift, quarantines nothing-dropped, re-synthesizes the parser and replays the queue — in thirty seconds." |
| 1:38–1:52 | Guard: injection blocked | "And because logs are attacker-controlled, attackers now prompt-inject AI log tools — eighty-seven percent success in 2026 research. Our model never sees raw logs, and injection attempts become detections instead of evasions." |
| 1:52–2:00 | Hero + logo + pack export | "EKALOG. One schema for every log. Air-gapped, lossless, self-healing." |

Record at 1920×1080, 60 fps, hide the cursor jitter, use OBS with a clean desktop. Add subtle background audio; no stock cinematic overkill.

---

## 12. The 5 slides

1. **Problem & Scope** — parser sprawl; weeks per source; PS26156 scope (perimeter devices); the requirement matrix in miniature.
2. **Solution & Architecture** — the §4 diagram; control plane vs data plane; the words "zero LLM in the hot path".
3. **What exists today vs EKALOG** — the §2.2 comparison table (Logstash / Elastic Automatic Import / Cribl / LILAC vs us). This slide proves you did homework.
4. **The four USPs** — lossless proof, drift self-healing, injection-resistant AI, `.ekapack` air-gap portability. One measured number each.
5. **Results & Feasibility** — real benchmarks (EPS, p99, Loghub accuracy vs Drain3, onboarding time vs hand-written), deployment (`docker compose up`, air-gapped), and the 36-hour finale plan.

---

## 13. Numbers you must measure (never invent)

Run `make bench` and put the real figures in the README, slides and video:
- Throughput: events/sec, single core and 8 cores → projected events/day.
- p50 / p99 per-event latency (µs).
- Template accuracy on Loghub-2.0 vs Drain3 baseline (same datasets, state which).
- Round-trip verification: events verified, failures (must be 0).
- Onboarding time: sample → working parser (seconds), vs your own timed attempt at hand-writing the same Grok pattern.
- Model footprint and RAM, to prove it runs on a SOC workstation.

**Do not claim:** "billions of events per day" as a measured fact — say "measured X EPS on one core; Y nodes projects to Z/day". Judges at NTRO will catch an unbacked number, and honesty here reads as competence.

---

## 14. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Ollama too slow on the demo laptop | Use `qwen2.5:3b-instruct-q4`; cached synthesis trace in demo mode |
| LLM emits invalid JSON | 2 retries at temp 0.1 → heuristic parser path, flagged low-confidence (never a crash) |
| 3D drops frames while recording | FPS-adaptive particle count; `NEXT_PUBLIC_LOW_GFX=1` static hero fallback |
| Round-trip fails on odd encodings | Store residual as base64 bytes, not str; test with UTF-8, latin-1, truncated datagrams |
| Time runs out | Cut, in order: Schema Sankey → Bench screen → ECS dual-emit → `.ekapack`. Never cut Vault, Drift or Guard — they are the USPs. |

---

## 15. Instructions for Claude Code

- Build in the order of §10; commit after each row of that table.
- Backend first and fully working before any CSS beyond the design tokens.
- **Never** put an LLM call in `runtime/executor.py`. That file is the USP; keep it pure and fast.
- Every API returns pydantic-typed responses; every WS message is `{type, ts, payload}`.
- All magic numbers (thresholds, ports, model name) live in `config.py`, overridable by env.
- Write `tests/test_lossless.py` (round-trip over all sample files, 0 failures), `tests/test_injection.py` (detector catches all lines in `attack/injection.log`, ≤1 false positive on clean samples), `tests/test_drift.py` (alarm fires within 5 s of the drift file, new version compiles).
- Seed `data/samples/` with realistic lines for Cisco ASA, FortiGate (KV), Palo Alto PAN-OS (CSV), pfSense (filterlog), Suricata (`eve.json`), Zeek (`conn.log`) — 2,000+ lines each; write a generator if needed. `data/drift/fortigate_v7.log` = FortiGate lines with two added fields and one reordered.
- README must open with the PS requirement matrix from §1 and the one-command setup.
- Keep `ARCHITECTURE.md` to what fits on 2 printed pages: the diagram, the data plane / control plane split, the four USP mechanisms, and the deployment model.
