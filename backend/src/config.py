import os

from dotenv import load_dotenv
from pydantic import SecretStr

load_dotenv()

# ─────────────────────────────────────────────
# LLM Provider selection (openai | gemini) + explicit fallback exposure
# ─────────────────────────────────────────────
#
# Backwards-compatible behavior:
# - `llm` continues to be the primary LLM used across the codebase (so other
#   modules can continue to import `llm` and call `await llm.ainvoke(prompt)`).
# - We also expose `fallback_llm` (may be None) and `gemini_llm` (may be None)
#   so callers or higher-level plumbing can explicitly use a fallback or
#   collect usage metrics per-provider.
#
# Configuration:
# - Set LLM_PROVIDER to "openai" (default) or "gemini" to prefer Gemini as the
#   primary model.
# - Optionally enable Gemini as a secondary provider even when the primary is
#   OpenAI by setting GEMINI_ENABLED=true (useful for testing/fallback).
#
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
GEMINI_ENABLED = os.getenv("GEMINI_ENABLED", "false").lower() in ("1", "true", "yes")


# Factory helpers that try to instantiate providers but never crash import time.
def _make_chatopenai():
    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    try:
        return ChatOpenAI(
            base_url=os.getenv(
                "LLM_BASE_URL", "https://hackeurope.crusoecloud.com/v1/"
            ),
            api_key=SecretStr(os.getenv("CRUSOE_API_KEY", "")),
            model=os.getenv("LLM_MODEL", "NVFP4/Qwen3-235B-A22B-Instruct-2507-FP4"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            max_completion_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        )
    except Exception:
        # Fail softly — return None so the rest of the app can decide what to do.
        return None


def _make_gemini():
    """
    Best-effort factory for a Gemini-capable LLM.

    Strategy:
    1. Prefer a LangChain-backed Google/Gemini model wrapped by our
       `LangChainAdapter` (if LangChain + a Google chat model are available).
       Try the explicit `GooglePalm` class first for clarity.
    2. Fall back to a few common LangChain chat model class names if the
       explicit import is not present.
    3. If LangChain is unavailable or instantiation fails, fall back to the
       legacy `src.gemini_client.GeminiClient` if present.
    4. Return None if no provider can be constructed.

    This function is intentionally defensive and uses best-effort imports so
    it won't crash import-time in environments where the optional packages are
    not installed.
    """
    # Try LangChain + our adapter first (non-fatal)
    try:
        from src.langchain_adapter import LangChainAdapter

        # Try direct import of the recommended LangChain Google/Gemini class.
        try:
            # Newer LangChain versions often expose a direct GooglePalm/ChatGooglePalm
            # class under langchain.chat_models; prefer explicit import if available.
            from langchain.chat_models import GooglePalm as _GooglePalm  # type: ignore

            LClass = _GooglePalm
        except Exception:
            # Fall back to dynamic import & candidate lookup for broader compatibility.
            import importlib

            try:
                chat_models_mod = importlib.import_module("langchain.chat_models")
            except Exception:
                chat_models_mod = None

            LClass = None
            if chat_models_mod is not None:
                # Try a few plausible class names in order (best-effort)
                for candidate in ("GooglePalm", "ChatGooglePalm", "ChatGoogle"):
                    LClass = getattr(chat_models_mod, candidate, None)
                    if LClass is not None:
                        break

        if LClass is not None:
            # Try constructing the LangChain LLM instance. Many LangChain
            # LLM constructors accept no args and read env/config; if they need
            # an API key we attempt to pass GEMINI_API_KEY as a best-effort.
            llm_instance = None
            try:
                # First attempt no-arg construction (preferred)
                llm_instance = LClass()
            except Exception:
                try:
                    # Try passing the API key as a common named parameter
                    llm_instance = LClass(api_key=os.getenv("GEMINI_API_KEY"))
                except Exception:
                    try:
                        # Some constructors accept `credentials` or `api_key` under different names
                        llm_instance = LClass(credentials=os.getenv("GEMINI_API_KEY"))
                    except Exception:
                        llm_instance = None

            if llm_instance is not None:
                return LangChainAdapter(
                    llm_instance,
                    model_name=os.getenv("GEMINI_MODEL", "models/text-bison-001"),
                )
    except Exception:
        # Swallow any adapter/import errors and fall back below
        pass

    # Fallback: use the existing minimal Gemini client if it exists.
    try:
        from src.gemini_client import GeminiClient
    except Exception:
        return None

    try:
        return GeminiClient(
            model=os.getenv("GEMINI_MODEL", "models/text-bison-001"),
            api_key=os.getenv("GEMINI_API_KEY", None),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
        )
    except Exception:
        return None


# Instantiate candidates (best-effort). Use GEMINI_ENABLED to optionally
# prepare Gemini as a secondary provider even when LLM_PROVIDER is openai.
gemini_llm = _make_gemini() if (LLM_PROVIDER == "gemini" or GEMINI_ENABLED) else None
chat_llm = _make_chatopenai()

# Determine primary `llm` and explicit `fallback_llm` while keeping the
# previous default behavior (ChatOpenAI when provider is "openai").
fallback_llm = None

if LLM_PROVIDER == "gemini":
    # Prefer Gemini; if not available, fall back to ChatOpenAI if present.
    llm = gemini_llm or chat_llm
    fallback_llm = chat_llm if (llm is gemini_llm) else None
else:
    # Default to ChatOpenAI primary; if absent and Gemini is available use it.
    llm = chat_llm or gemini_llm
    fallback_llm = gemini_llm if (llm is chat_llm) else None

# If for some reason no provider could be instantiated, llm will be None.
# Calling code should handle that case (this mirrors the original behavior of
# allowing environments without a configured provider to run limited logic).

# ─────────────────────────────────────────────
# App Settings
# ─────────────────────────────────────────────

CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

# Cost per 1M tokens (USD) – used by the economics node
COST_PER_MILLION_TOKENS: float = float(os.getenv("COST_PER_MILLION_TOKENS", "0.15"))

# Estimated tokens consumed per run (rough average across all nodes)
ESTIMATED_TOKENS_PER_RUN: int = int(os.getenv("ESTIMATED_TOKENS_PER_RUN", "1500"))

# Platform fee = compute cost × this multiplier
PLATFORM_FEE_MULTIPLIER: float = float(os.getenv("PLATFORM_FEE_MULTIPLIER", "10"))

# ─────────────────────────────────────────────
# Supabase Auth
# ─────────────────────────────────────────────

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ─────────────────────────────────────────────
# Google OAuth (for Gmail integration)
# ─────────────────────────────────────────────

GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
