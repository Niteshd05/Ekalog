# EKALOG — Architecture (SIH26156)

## 1. Planes

```
                 ┌────────────────────── CONTROL PLANE (offline, sandboxed) ──────────────────────┐
 sample.log ──►  EkaMiner (delimiter-preserving lexer + Drain-style clustering) ──► templates        │
                 │ rule labeler: device keys · file headers · documented layouts · interface words  │
                 │ local LLM (Ollama, JSON-schema enums) names only the remaining fields            │
                 │ gates: holdout coverage · byte-exact round-trip · types · semantics · OCSF      │
                 └──► ParserArtifact (semver, SHA-256, Ed25519, test vectors) ──► Registry ────────┘
                                                                         │ atomic Router swap, no restart
 ┌──────────────────────────── DATA PLANE (no AI, ever) ─────────────────┼──────────────────────────┐
 │ syslog/UDP · HTTP push · file replay ─► Vault (raw bytes FIRST) ─► normalize_batch(Router) ─►    │
 │   sha256(raw)                          append-only, raw_ref      tokenize · dict lookup ·        │
 │                                                                  OCSF map · rebuild + verify     │
 │   ─► Event store + hash-chain ledger ─► Sinks (NDJSON · OpenSearch · Splunk HEC · Parquet)        │
 │   ─► Drift Sentinel (rolling fail-rate) ── alarm ─► quarantine ─► Foundry.heal ─► hot-swap ─►     │
 │                                                                              replay quarantine    │
 │   ─► Injection Guard (per event) ─► ekalog.injection tag + alert                                  │
 └────────────────────────────────────────────── one WebSocket (10 Hz batched frames) ─► UI ───────┘
```

**Why this split:** the LLM is a *compiler*, not a runtime. Production traffic runs a deterministic, signed,
diffable artifact. An auditor can re-run parser v1.1.0's test vectors. Nobody can audit a prompt.

## 2. Mechanisms

**EkaMiner.** Each line becomes `w0 d0 w1 d1 … wn`. Delimiters are single punctuation characters or whitespace
runs, and words may be empty (so CSV columns keep their positions). Timestamps, IPv6, MACs and quoted strings are
atoms. `render(tokenize(x)) == x` holds for every input. Lines are grouped by their exact delimiter sequence and
clustered by masked-word similarity. Generalization turns values that happened to be constant in the sample
(KV/JSON values, syslog hostnames, typed tokens, CSV columns) into slots. Runtime matching is a dict lookup plus a
literal comparison, with no regex backtracking. `to_regex / to_grok / to_vrl` exist for export only.

**Labeling (rules → model).** Evidence priority: the device's own key or header → documented column layout →
structural position → interface/direction words → context → order. The model is asked only about what is left.
Its output is constrained by an Ollama JSON schema: `class_uid ∈ {…}`, `ocsf ∈ {…45 paths, none}`. It is then
re-validated: type compatibility, one slot per OCSF path (the losslessness invariant), and the model's class is
accepted only if that class's required fields are mapped. Answers are cached by template hash, so the same template
is never asked twice.

**Losslessness proof.** Each slot value lands in an OCSF field, in `unmapped{name}`, or, if the typed form cannot
reproduce the text (for example `0443` → 443, or timestamps), in `ekalog.verbatim`. `reconstruct(event, template)`
rebuilds the line from the record alone, and `sha256(rebuilt) == ingest_hash` is checked for every event.
Unmatched lines keep `raw_data` and go to quarantine, so they are lossless too. Old events stay rebuildable,
because every parser version is immutable and referenced by the event.

**Drift Sentinel.** Per source, a rolling window of parse outcomes. A fail rate above 5 % (≥ 100 events) raises an
alarm. Unmatched lines are already quarantined. `Foundry.heal` mines only the new shapes and labels them. If the
gates pass, it registers `minor+1`, the Router swaps atomically, and the quarantine is replayed with its original
vault references and hashes. A version diff (added, removed and reordered fields) is published to the UI.

**Injection Guard.** Structural defenses: the model never receives raw text, only typed placeholders and
`[A-Za-z0-9._-]{≤32}` identifiers. Templates whose text trips the Guard are never sent. Outputs are enums or
sanitized names that are never executed and never become a verdict. The detector normalizes input first (NFKC,
zero-width removal), then scores instruction override, verdict steering, benign framing, AI addressing, role
tokens, CR/LF syslog forgery, control and zero-width characters, and base64 / `\u` payloads that decode to
instructions. A score ≥ 0.6 tags the event and raises an alert.

**Ask EKALOG.** The model sees the question plus field and operator enums, and returns `{filters[], minutes}`.
Values are coerced to types and bound as SQL parameters. The analyst sees and edits the filter as chips.

## 3. Deployment and scaling

- **One image, one port.** The UI is built at image-build time and served by FastAPI, with no Node at runtime.
  `docker compose up` runs `ekalog` and `ollama`. Air-gapped sites load images and the model volume offline, and
  move parsers as signed `.ekapack` files.
- **Air-gap enforcement.** The LLM client refuses non-local endpoints and Ollama `*-cloud` models. Fonts are
  self-hosted. The UI shows an honest egress self-test.
- **Scale-out.** `normalize_batch` is a pure function over an immutable, content-addressed Router snapshot.
  `EKALOG_WORKERS=N` runs it in a process pool, and more containers can consume the same Bus (in-process queue
  today; Redis Streams / Kafka adapters are the drop-in next step). Persistence (SQLite WAL, Postgres-ready schema)
  and the UI hub are the only stateful parts.
- **Standards.** OCSF 1.3 (pinned subset), ECS-compatible field paths via export, RFC 3164/5424 syslog,
  CEF, and key-value / CSV / TSV / JSON.
