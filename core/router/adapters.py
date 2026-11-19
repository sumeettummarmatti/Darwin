"""Model provider adapters. The ONLY place in the repo that talks to a model provider.

* ``SimulatedAdapter`` — a deterministic, in-process stand-in. Each model skill
  ships a ``simulated.py`` responder that receives the *already tokenised*
  payload (so it sees exactly what a real provider would). Used for the demo,
  tests and the bench so that runs are reproducible and free of real data.
  Its rupee cost is computed from a declared rate card, and it is labelled
  ``sim`` everywhere a number is shown.
* ``OpenAICompatibleAdapter`` — any OpenAI-compatible ``/chat/completions``
  endpoint (vLLM, Together, Groq, Azure, a self-hosted open-weight model…).
  Switching to it is a change to ``config/routing.yaml``, not to any skill.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ProviderConfig:
    tier: int
    adapter: str
    model: str
    region: str
    inr_per_m_in: float
    inr_per_m_out: float
    base_url: str | None = None
    api_key_env: str | None = None
    hosting_note: str = ""

    @property
    def label(self) -> str:
        return f"{self.adapter}:{self.model}"


@dataclass
class RawCompletion:
    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


def estimate_tokens(text: str) -> int:
    """~4 characters per token. Declared approximation for the simulated provider;
    real adapters use the provider's reported usage instead."""
    return max(1, math.ceil(len(text) / 4))


class SimulatedAdapter:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, system: str, user: str, simulate: Callable[[dict[str, Any], int], dict[str, Any]] | None) -> RawCompletion:
        started = time.perf_counter()
        if simulate is None:
            raise RuntimeError("skill has no simulated responder; configure a real provider")
        payload = json.loads(user)
        output = simulate(payload, self.config.tier)
        text = json.dumps(output)
        return RawCompletion(
            text=text,
            tokens_in=estimate_tokens(system) + estimate_tokens(user),
            tokens_out=estimate_tokens(text),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


class OpenAICompatibleAdapter:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, system: str, user: str, simulate: Callable | None = None) -> RawCompletion:
        import httpx

        key = os.environ.get(self.config.api_key_env or "", "")
        if self.config.api_key_env and not key:
            raise ProviderAuthError(f"{self.config.api_key_env} is not set")
        started = time.perf_counter()
        request = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        url = f"{(self.config.base_url or '').rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        resp = httpx.post(url, headers=headers, json=request, timeout=30)
        for _ in range(3):
            # Rate limits and transient 5xx: wait as the provider asks (capped), then retry once more.
            if resp.status_code != 429 and resp.status_code < 500:
                break
            time.sleep(min(float(resp.headers.get("retry-after", 2) or 2), 6))
            resp = httpx.post(url, headers=headers, json=request, timeout=30)
        if resp.status_code == 400 and ("response_format" in resp.text or "json_validate_failed" in resp.text):
            # JSON mode unsupported, or the model's JSON failed the provider's own check:
            # ask again without JSON mode; the router still validates the schema.
            request.pop("response_format")
            resp = httpx.post(url, headers=headers, json=request, timeout=30)
        if resp.status_code == 400:
            # Still unusable: hand back an empty answer so the router's schema path
            # (retry once, escalate a tier, then a human) deals with it — never a crash.
            return RawCompletion(text="", tokens_in=estimate_tokens(system + user), tokens_out=0,
                                 latency_ms=int((time.perf_counter() - started) * 1000))
        if resp.status_code == 429 or resp.status_code >= 500:
            raise ProviderBusyError(f"provider answered {resp.status_code} after retries")
        if resp.status_code in (401, 403):
            raise ProviderAuthError(f"{self.config.api_key_env} was rejected by the provider ({resp.status_code})")
        resp.raise_for_status()
        body = resp.json()
        usage = body.get("usage") or {}
        text = body["choices"][0]["message"]["content"]
        return RawCompletion(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or estimate_tokens(system + user)),
            tokens_out=int(usage.get("completion_tokens") or estimate_tokens(text)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


ADAPTERS = {"sim": SimulatedAdapter, "openai_compatible": OpenAICompatibleAdapter}


def build_adapter(config: ProviderConfig):
    if config.adapter not in ADAPTERS:
        raise ValueError(f"unknown adapter '{config.adapter}'")
    return ADAPTERS[config.adapter](config)


class ProviderBusyError(RuntimeError):
    """Rate-limited or failing (429 / 5xx) after retries."""


class ProviderAuthError(RuntimeError):
    """The provider rejected the key (missing, expired or revoked)."""


def check_key(base_url: str, key: str) -> tuple[bool, str]:
    """Ask the provider whether a key works, without spending tokens (GET /models)."""
    import httpx

    if not key:
        return False, "No key entered."
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
    except httpx.HTTPError as exc:
        return False, f"Could not reach the provider ({type(exc).__name__}). Check the connection and try again."
    if resp.status_code in (401, 403):
        return False, "The provider rejected this key — it may be expired, revoked or mistyped. Create a new one."
    if resp.status_code >= 400:
        return False, f"The provider answered {resp.status_code}. Try again in a moment."
    return True, "Key accepted."
