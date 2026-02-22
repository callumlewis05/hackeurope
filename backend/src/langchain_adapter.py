"""
Thin LangChain adapter to normalise LangChain LLM outputs to the project's shape.

This adapter accepts any object that behaves like a LangChain LLM (or a similar
LLM wrapper) and exposes an async `ainvoke(prompt: str)` returning a
`SimpleNamespace(content=str, meta=dict)`.

Behavior:
 - Prefer async LangChain APIs:
    * `agenerate` -> expected to return a Generations-like object
    * `apredict` / `apredict_single`
 - Fall back to sync `predict` / `__call__` executed in a thread via
   `asyncio.to_thread`.
 - Meta contains: `model`, `estimated_tokens`, `latency_ms`, and `raw`.
 - If the provider/response exposes exact token usage, the adapter will include
   it (under `meta['provider_usage']`) and `meta['estimated_tokens']` will prefer
   that value.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LangChainAdapter:
    """
    Wraps a LangChain LLM (or similar) and exposes an async `ainvoke(prompt)`.

    Example:
        adapter = LangChainAdapter(llm_instance)
        resp = await adapter.ainvoke(\"Hello world\")
        print(resp.content)    # str
        print(resp.meta)       # dict
    """

    def __init__(self, llm: Any, model_name: Optional[str] = None) -> None:
        self.llm = llm
        # Prefer explicit model_name, fall back to an attribute on the LLM
        self.model = model_name or getattr(llm, "model", None) or "unknown"

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        """
        Invoke the underlying LLM with `prompt`.

        Returns a SimpleNamespace:
          - content: str                 # textual completion
          - meta: dict                   # diagnostic / usage info
              - model: str
              - estimated_tokens: int
              - latency_ms: int
              - raw: any                  # raw provider response (best-effort)
              - provider_usage: dict|None # if provider returned token counts
        """
        start = time.perf_counter()
        raw = None
        text = ""
        provider_usage = None

        # 1) Try async generate API (LangChain agenerate)
        if hasattr(self.llm, "agenerate"):
            try:
                # agenerate expects a list of prompts for many implementations
                out = await self.llm.agenerate([prompt])
                raw = out
                # Typical LangChain Generations shape: out.generations -> list[list[Generation]]
                gens = getattr(out, "generations", None)
                if gens and isinstance(gens, list) and len(gens) > 0:
                    first_group = gens[0]
                    if isinstance(first_group, list) and len(first_group) > 0:
                        gen0 = first_group[0]
                        # gen0 may have attribute 'text'
                        text = str(getattr(gen0, "text", gen0))
                    else:
                        # fallback stringify
                        text = str(first_group)
                else:
                    # Some adapters return stringifiable objects
                    text = str(out)
                # Try to extract provider usage if present (LangChain may populate .llm_output)
                llm_out = getattr(out, "llm_output", None) or getattr(out, "info", None)
                if isinstance(llm_out, dict):
                    # Common shapes: {'token_usage': {...}} or {'usage': {...}}
                    provider_usage = (
                        llm_out.get("token_usage") or llm_out.get("usage") or None
                    )
            except Exception:
                logger.exception("LangChainAdapter: agenerate failed; falling back")

        # 2) Try async predict-like APIs (apredict / apredict_single)
        if not text and (
            hasattr(self.llm, "apredict") or hasattr(self.llm, "apredict_single")
        ):
            fn = getattr(self.llm, "apredict", getattr(self.llm, "apredict_single"))
            try:
                out = await fn(prompt)
                raw = out
                text = str(out)
                # Some apredict implementations return a dict with 'text' or 'output'
                if isinstance(out, dict):
                    text = str(out.get("text") or out.get("output") or text)
                    provider_usage = (
                        out.get("usage") or out.get("token_usage") or provider_usage
                    )
            except Exception:
                logger.exception("LangChainAdapter: apredict failed; falling back")

        # 3) Try sync predict/generate/__call__ in a thread
        if not text:
            fn = (
                getattr(self.llm, "predict", None)
                or getattr(self.llm, "__call__", None)
                or getattr(self.llm, "generate", None)
            )
            if fn is None:
                # Nothing callable; return empty content with debug meta
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                meta = {
                    "model": self.model,
                    "estimated_tokens": 0,
                    "latency_ms": elapsed_ms,
                    "raw": None,
                    "provider_usage": None,
                    "error": "no_callable_llm",
                }
                return SimpleNamespace(content="", meta=meta)

            try:
                out = await asyncio.to_thread(fn, prompt)
                raw = out
                # Attempt to extract reasonable text
                if isinstance(out, dict):
                    text = str(out.get("text") or out.get("output") or out)
                    provider_usage = (
                        out.get("usage") or out.get("token_usage") or provider_usage
                    )
                else:
                    text = str(out)
            except Exception:
                logger.exception("LangChainAdapter: sync predict failed in thread")
                # Keep text empty and continue to meta below

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Determine token usage:
        # - Prefer explicit provider usage if available
        # - Fall back to conservative heuristic: ~4 characters per token
        estimated_tokens = 0
        if provider_usage and isinstance(provider_usage, dict):
            # Try several common keys in provider usage blobs
            for k in (
                "total_tokens",
                "tokens",
                "token_count",
                "total_token_usage",
                "completion_tokens",
            ):
                if k in provider_usage and isinstance(provider_usage[k], int):
                    estimated_tokens = int(provider_usage[k])
                    break
            # If not matched, try 'prompt' + 'completion' fields
            if not estimated_tokens:
                prompt_t = provider_usage.get("prompt_tokens") or provider_usage.get(
                    "prompt"
                )
                comp_t = provider_usage.get("completion_tokens") or provider_usage.get(
                    "completion"
                )
                try:
                    prompt_t = int(prompt_t) if prompt_t is not None else 0
                    comp_t = int(comp_t) if comp_t is not None else 0
                    estimated_tokens = prompt_t + comp_t
                except Exception:
                    estimated_tokens = 0

        if not estimated_tokens:
            # conservative heuristic
            estimated_tokens = max(1, int(len((prompt or "") + (text or "")) / 4))

        meta = {
            "model": self.model,
            "estimated_tokens": estimated_tokens,
            "latency_ms": elapsed_ms,
            "raw": raw,
            "provider_usage": provider_usage,
        }

        return SimpleNamespace(content=text or "", meta=meta)
