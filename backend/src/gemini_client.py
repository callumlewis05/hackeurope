"""
Deterministic async Gemini (Generative Language) adapter.

This rewritten client is:
- Deterministic: initialization is straightforward (no lazy imports).
- Resilient: built-in retries with exponential backoff for transient errors.
- Informative: returns a SimpleNamespace with `.content` (string) and a
  `.meta` dict containing model, estimated tokens, latency_ms, status, and raw
  response for diagnostics.
- Safe: when the API key is missing we log an error and return an empty content
  (keeps backwards compatibility with callers that expect a `.content` attribute).

Usage:
    from src.gemini_client import GeminiClient
    client = GeminiClient()
    resp = await client.ainvoke("Hello world")
    text = resp.content
    # optional meta
    tokens = resp.meta.get("estimated_completion_tokens")

Configuration via environment variables:
- GEMINI_API_KEY            : API key for Google Generative Language (Gemini) adapter
- GEMINI_MODEL              : default model (e.g. "models/text-bison-001")
- GEMINI_BASE_URL           : base URL for REST API
- GEMINI_TEMP               : float temperature
- GEMINI_MAX_TOKENS         : max output tokens
- GEMINI_TIMEOUT            : per-request timeout (seconds)
- GEMINI_RETRIES            : number of retries for transient errors
- GEMINI_BACKOFF_FACTOR     : multiplier for exponential backoff (seconds)
- GEMINI_RETRY_STATUS_CODES : comma-separated HTTP codes treated as retryable (e.g. "429,500,502,503")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Defaults and env-driven configuration
_GEMINI_BASE = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta2"
)
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/text-bison-001")
_GEMINI_TEMP = float(os.getenv("GEMINI_TEMP", "0.0"))
_GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))
_GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "30.0"))
_GEMINI_RETRIES = int(os.getenv("GEMINI_RETRIES", "2"))
_GEMINI_BACKOFF = float(os.getenv("GEMINI_BACKOFF_FACTOR", "0.8"))
_GEMINI_RETRY_STATUS = os.getenv("GEMINI_RETRY_STATUS_CODES", "429,500,502,503")
_GEMINI_RETRY_STATUS_CODES = {
    int(s.strip()) for s in _GEMINI_RETRY_STATUS.split(",") if s.strip().isdigit()
}


def _estimate_tokens_from_text(text: str) -> int:
    """
    Simple heuristic to estimate tokens from text length.
    This is intentionally conservative and only used for usage-logging purposes.
    Common heuristics: ~4 characters per token for English text.
    """
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def _build_payload(prompt: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    """
    Build request payload compatible with typical Generative Language REST endpoints.
    Keep shape conservative to work with multiple API shapes.
    """
    return {
        "prompt": {"text": prompt},
        "temperature": float(temperature),
        "maxOutputTokens": int(max_tokens),
    }


def _extract_text_from_response(data: Any) -> Tuple[str, Dict[str, Any]]:
    """
    Extract a textual completion from a variety of possible Gemini response shapes.
    Returns (extracted_text, diagnostics_dict).
    diagnostics_dict contains the original data (or a truncated version) and any
    helper fields used for meta reporting.
    """
    diagnostics: Dict[str, Any] = {"raw": data}
    try:
        if isinstance(data, dict):
            # Common candidate containers
            candidates = (
                data.get("candidates") or data.get("outputs") or data.get("results")
            )
            if isinstance(candidates, list) and len(candidates) > 0:
                first = candidates[0]
                if isinstance(first, dict):
                    # Common text keys
                    for k in ("content", "output", "text", "response"):
                        v = first.get(k)
                        if isinstance(v, str) and v.strip():
                            return v, diagnostics
                    # Some responses have 'content' as a list of segments
                    cont = first.get("content")
                    if isinstance(cont, list):
                        parts = []
                        for seg in cont:
                            if isinstance(seg, dict) and "text" in seg:
                                parts.append(str(seg["text"]))
                            elif isinstance(seg, str):
                                parts.append(seg)
                        if parts:
                            return "\n".join(parts), diagnostics
            # Top-level fallback keys
            for k in ("output", "text"):
                if k in data and isinstance(data[k], str):
                    return data[k], diagnostics

        # Fallback: try to stringify reasonably
        raw = json.dumps(data, ensure_ascii=False)
        if len(raw) > 2000:
            raw = raw[:2000] + "\n... (truncated)"
        return raw, diagnostics
    except Exception:
        # Last resort
        try:
            s = str(data)
            if len(s) > 2000:
                s = s[:2000] + "\n... (truncated)"
            return s, diagnostics
        except Exception:
            return "", diagnostics


class GeminiClient:
    """
    Async Gemini client with retries and usage estimation.

    The public API is:
      client = GeminiClient(...)
      resp = await client.ainvoke(prompt)
      # resp is a SimpleNamespace with:
      #   - content: str  (the extracted text; empty string on error)
      #   - meta: dict    (model, tokens estimates, latency_ms, status_code, success, raw)
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ) -> None:
        self.model = model or _GEMINI_MODEL
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.temperature = float(temperature or _GEMINI_TEMP)
        self.max_tokens = int(max_tokens or _GEMINI_MAX_TOKENS)
        self.timeout = float(timeout or _GEMINI_TIMEOUT)
        self.retries = int(retries if retries is not None else _GEMINI_RETRIES)
        self.backoff = float(
            backoff_factor if backoff_factor is not None else _GEMINI_BACKOFF
        )
        self.base_url = _GEMINI_BASE

        # Precompute endpoint (deterministic)
        # REST path: {base}/{model}:generateText
        self._endpoint = f"{self.base_url}/{self.model}:generateText"

        # Keep the client creation per-call to avoid lifecycle/cleanup complexity.
        # httpx.AsyncClient is lightweight for short-lived use-cases and we set a timeout.

    async def _call_once(self, prompt: str) -> Tuple[int, Any]:
        """
        Make a single HTTP call to the Gemini REST endpoint.
        Returns a tuple (status_code, parsed_json_or_text).
        May raise httpx.RequestError on network issues (handled by callers).
        """
        payload = _build_payload(prompt, self.temperature, self.max_tokens)
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key} if self.api_key else {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._endpoint, json=payload, headers=headers, params=params
            )
            # Raise for 4xx/5xx to get HTTPStatusError which includes .response
            resp.raise_for_status()
            # Try to parse JSON; if parsing fails fall back to text
            try:
                return resp.status_code, resp.json()
            except ValueError:
                return resp.status_code, resp.text

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        """
        Invoke the model with `prompt`. Retries on transient errors.

        Returns a SimpleNamespace:
          - content: str
          - meta: dict with keys:
              - model
              - estimated_prompt_tokens
              - estimated_completion_tokens
              - estimated_total_tokens
              - latency_ms
              - status_code
              - success (bool)
              - error (str | None)
              - raw (original parsed response)
        """
        if not self.api_key:
            logger.error(
                "GeminiClient: GEMINI_API_KEY not configured; returning empty response"
            )
            meta = {
                "model": self.model,
                "estimated_prompt_tokens": _estimate_tokens_from_text(prompt),
                "estimated_completion_tokens": 0,
                "estimated_total_tokens": _estimate_tokens_from_text(prompt),
                "latency_ms": 0,
                "status_code": None,
                "success": False,
                "error": "missing_api_key",
                "raw": None,
            }
            return SimpleNamespace(content="", meta=meta)

        attempt = 0
        start_time = time.perf_counter()
        last_error: Optional[str] = None
        status_code: Optional[int] = None
        raw_response: Any = None

        while True:
            try:
                attempt += 1
                status_code, raw_response = await self._call_once(prompt)
                # Success path: extract text and exit loop
                extracted_text, diagnostics = _extract_text_from_response(raw_response)
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                prompt_tokens = _estimate_tokens_from_text(prompt)
                completion_tokens = _estimate_tokens_from_text(extracted_text)
                meta = {
                    "model": self.model,
                    "estimated_prompt_tokens": prompt_tokens,
                    "estimated_completion_tokens": completion_tokens,
                    "estimated_total_tokens": prompt_tokens + completion_tokens,
                    "latency_ms": elapsed_ms,
                    "status_code": status_code,
                    "success": True,
                    "error": None,
                    "raw": diagnostics.get("raw"),
                    }
                    return SimpleNamespace(content=extracted_text, meta=meta)
            except httpx.HTTPStatusError as exc:
                # Server returned a 4xx/5xx. Ensure we only access `.status_code`
                # when a real Response object is present on the exception.
                resp_obj = getattr(exc, "response", None)
                last_error = f"http_status_error:{resp_obj}"
                if resp_obj is not None and hasattr(resp_obj, "status_code"):
                    status_code = resp_obj.status_code
                logger.warning(
                    "GeminiClient attempt %d/%d: HTTP error (status=%s) while calling Gemini: %s",
                    attempt,
                    self.retries + 1,
                    status_code,
                    exc,
                )
            except httpx.RequestError as exc:
                last_error = f"request_error:{type(exc).__name__}:{str(exc)}"
                logger.warning(
                    "GeminiClient attempt %d/%d: network/request error while calling Gemini: %s",
                    attempt,
                    self.retries + 1,
                    exc,
                )
            except Exception as exc:
                # Catch-all: parsing, unexpected shapes, etc.
                last_error = f"unexpected_error:{type(exc).__name__}:{str(exc)}"
                logger.exception(
                    "GeminiClient attempt %d/%d: unexpected error",
                    attempt,
                    self.retries + 1,
                )
            # Decide whether to retry
            if attempt > self.retries:
                break
            # Exponential backoff with jitter
            backoff = self.backoff * (2 ** (attempt - 1))
            jitter = backoff * 0.1
            sleep_time = backoff + (jitter * (2 * (os.urandom(1)[0] / 255.0) - 1))
            # Ensure sleep_time is non-negative and not excessively tiny
            sleep_time = max(0.05, min(sleep_time, 30.0))
            await asyncio.sleep(sleep_time)

        # If we reach here, all retries exhausted
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        # Attempt to extract anything parsable from raw_response; otherwise return empty content
        content = ""
        try:
            if raw_response is not None:
                content, diagnostics = _extract_text_from_response(raw_response)
        except Exception:
            content = ""

        meta = {
            "model": self.model,
            "estimated_prompt_tokens": _estimate_tokens_from_text(prompt),
            "estimated_completion_tokens": _estimate_tokens_from_text(content),
            "estimated_total_tokens": _estimate_tokens_from_text(prompt)
            + _estimate_tokens_from_text(content),
            "latency_ms": elapsed_ms,
            "status_code": status_code,
            "success": False,
            "error": last_error,
            "raw": raw_response,
        }

        logger.error(
            "GeminiClient: all %d attempts failed; last_error=%s status=%s elapsed_ms=%d",
            attempt,
            last_error,
            status_code,
            elapsed_ms,
        )

        return SimpleNamespace(content=content or "", meta=meta)
