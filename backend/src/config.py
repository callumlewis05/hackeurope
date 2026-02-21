import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv()

# ─────────────────────────────────────────────
# LLM Configuration (Crusoe Hosted Qwen3)
# ─────────────────────────────────────────────

llm = ChatOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "https://hackeurope.crusoecloud.com/v1/"),
    api_key=SecretStr(os.getenv("CRUSOE_API_KEY", "")),
    model=os.getenv("LLM_MODEL", "NVFP4/Qwen3-235B-A22B-Instruct-2507-FP4"),
    temperature=0,
    max_completion_tokens=2048,
)

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
