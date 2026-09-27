"""All tunables live here. Every value is overridable with an EKALOG_* environment variable."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default, cast=None):
    raw = os.environ.get(f"EKALOG_{name.upper()}")
    if raw is None:
        return default
    cast = cast or type(default)
    if cast is bool:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return cast(raw)


@dataclass
class Settings:
    # --- paths ---
    data_dir: Path = BASE_DIR / "data"
    state_dir: Path = BASE_DIR / "state"

    # --- local LLM (Ollama only; never a cloud API) ---
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:7b-instruct-q4_K_M"
    fallback_model: str = "qwen2.5:3b-instruct-q4_K_M"
    llm_temperature: float = 0.1
    llm_seed: int = 42
    llm_timeout_s: float = 180.0
    llm_retries: int = 2
    llm_batch_templates: int = 6
    llm_enabled: bool = True

    # --- miner ---
    miner_sim_threshold: float = 0.5
    miner_max_examples: int = 5
    miner_min_support: int = 1

    # --- foundry validation gates ---
    holdout_ratio: float = 0.2
    gate_coverage: float = 0.90
    auto_activate: bool = True

    # --- runtime ---
    batch_size: int = 1000
    batch_linger_ms: int = 50
    workers: int = 0  # 0 = in-process; N>0 = process pool
    verify_every: int = 1  # verify round-trip on every Nth event (1 = all)
    emit_raw_data: bool = False
    recent_events: int = 2000
    store_max_events: int = 500_000

    # --- drift sentinel ---
    drift_window: int = 400
    drift_min_events: int = 100
    drift_fail_rate: float = 0.05
    drift_auto_heal: bool = True
    drift_heal_min_lines: int = 40

    # --- injection guard ---
    injection_threshold: float = 0.6

    # --- ingest ---
    syslog_udp_port: int = 5514
    syslog_enabled: bool = True
    http_port: int = 8000

    # --- demo ---
    demo: bool = False
    ui_hz: int = 10

    def __post_init__(self):
        for f in fields(self):
            cur = getattr(self, f.name)
            cast = Path if isinstance(cur, Path) else None
            setattr(self, f.name, _env(f.name, cur, cast))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "vault").mkdir(exist_ok=True)
        (self.state_dir / "sinks").mkdir(exist_ok=True)


settings = Settings()
