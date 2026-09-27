"""Local-only LLM client (Ollama). No cloud APIs, ever.

- Talks only to EKALOG_OLLAMA_URL (default 127.0.0.1) and refuses non-local hosts.
- Refuses Ollama *cloud* models (e.g. `*-cloud`, models with a remote_host) because they proxy
  prompts to the internet.
- Uses Ollama structured outputs (`format` = JSON schema) at low temperature with a fixed seed,
  so results are constrained and reproducible.
"""
from __future__ import annotations

import asyncio
import ipaddress
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx
import orjson

from ..config import settings

TokenCB = Callable[[str], Awaitable[None] | None]


def _is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host in ("localhost", "ollama"):  # 'ollama' = docker-compose service name
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


class OllamaClient:
    def __init__(self, url: str | None = None, model: str | None = None):
        self.url = (url or settings.ollama_url).rstrip("/")
        self.model = model or settings.model
        if not _is_local(self.url):
            raise ValueError(f"EKALOG refuses non-local LLM endpoint {self.url} (air-gap policy)")
        self._resolved: str | None = None
        self.last_error: str | None = None

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{self.url}/api/tags")
                r.raise_for_status()
                models = r.json().get("models", [])
        except Exception as e:  # noqa: BLE001
            return {"up": False, "url": self.url, "model": self.model, "error": type(e).__name__}
        local = [m["name"] for m in models if not m.get("remote_host") and not m["name"].endswith("-cloud")
                 and ":cloud" not in m["name"]]
        blocked = [m["name"] for m in models if m["name"] not in local]
        chosen = next((m for m in (self.model, settings.fallback_model) if m in local), None)
        if chosen is None:
            chosen = next((m for m in local if m.startswith(("qwen", "llama", "mistral", "phi", "gemma"))), None)
        self._resolved = chosen
        return {"up": True, "url": self.url, "model": chosen, "requested": self.model, "local_models": local,
                "blocked_cloud_models": blocked}

    async def model_name(self) -> str | None:
        if self._resolved is None:
            await self.health()
        return self._resolved

    async def chat_json(self, system: str, user: str, schema: dict, on_token: TokenCB | None = None,
                        validate: Callable[[dict], dict] | None = None, num_predict: int = 4096) -> dict | None:
        """Streamed, schema-constrained chat. Returns the parsed (and validated) JSON or None."""
        if not settings.llm_enabled:
            return None
        model = await self.model_name()
        if not model:
            self.last_error = "no local model available"
            return None
        body = {
            "model": model, "stream": True, "format": schema, "keep_alive": "30m",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": settings.llm_temperature, "seed": settings.llm_seed, "num_ctx": 8192,
                        "num_predict": num_predict},
        }
        for attempt in range(settings.llm_retries + 1):
            buf: list[str] = []
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout_s, connect=5)) as c:
                    async with c.stream("POST", f"{self.url}/api/chat", json=body) as r:
                        r.raise_for_status()
                        async for line in r.aiter_lines():
                            if not line:
                                continue
                            chunk = orjson.loads(line)
                            tok = chunk.get("message", {}).get("content", "")
                            if tok:
                                buf.append(tok)
                                if on_token:
                                    res = on_token(tok)
                                    if asyncio.iscoroutine(res):
                                        await res
                            if chunk.get("done"):
                                break
                data = orjson.loads("".join(buf))
                return validate(data) if validate else data
            except Exception as e:  # noqa: BLE001 - any failure -> retry, then deterministic fallback
                self.last_error = f"{type(e).__name__}: {str(e)[:200]}"
                body["options"]["seed"] = settings.llm_seed + attempt + 1
        return None


llm = OllamaClient()
