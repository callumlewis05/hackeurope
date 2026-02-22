"""LangGraph pipeline — all node functions and graph builder in one module.

Nodes delegate domain-specific logic to handlers via the registry,
keeping this file fully domain-agnostic.

Pipeline:
    context_router → (calendar_fetcher, bank_fetcher, purchase_history_fetcher)
        → audit → [drafting if risks] → economics → storage → END
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src import db, gmail
from src.config import (
    COST_PER_MILLION_TOKENS,
    ESTIMATED_TOKENS_PER_RUN,
    PLATFORM_FEE_MULTIPLIER,
    llm,
)
from src.domains import get_domain_handler
from src.schemas import AgentState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _extract_text(content: str | list[Any]) -> str:
    """Normalise LLM response content to a plain string."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and "text" in block:
            parts.append(str(block["text"]))
    return "\n".join(parts)


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Best-effort parse of LLM output that should be JSON."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse LLM JSON — %s | raw=%s", exc, raw[:200])
        return {}


def _inject_user_id(state: AgentState) -> dict[str, Any]:
    """Return intent dict with _user_id injected for DB queries."""
    intent = dict(state["intent"])
    intent["_user_id"] = state.get("user_id", "")
    return intent


def _strip_html(val: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = re.sub(r"<[^>]+>", " ", val)
    return re.sub(r"\s+", " ", clean).strip()


def _generate_title(domain: str, intent: dict[str, Any]) -> str:
    """Build a short human-readable title from domain + intent data."""
    intent_type = intent.get("type", "")

    # Flights
    if intent_type == "flight_booking":
        outbound = intent.get("outbound", {})
        dep = _strip_html(str(outbound.get("departure_airport", "")))
        arr = _strip_html(str(outbound.get("arrival_airport", "")))
        dep_date = _strip_html(str(outbound.get("departure_date", "")))
        route = f"{dep} → {arr}" if dep and arr else "flight"
        return f"Flight {route} on {dep_date}" if dep_date else f"Flight {route}"

    # Shopping
    if intent_type == "purchase":
        items = intent.get("items", [])
        if items:
            first = items[0].get("name", "Unknown item")
            if len(items) > 1:
                return f"{first} + {len(items) - 1} more"
            return first
        return "Purchase"

    # Fallback
    if intent_type:
        return f"{intent_type} on {domain}"
    return f"Action on {domain}"


# ─────────────────────────────────────────────
# 1. CONTEXT ROUTER
# ─────────────────────────────────────────────


async def context_router_node(state: AgentState) -> dict:
    """Determine which data sources are needed (rule-based, no LLM)."""
    handler = get_domain_handler(state["domain"])
    intent_with_uid = _inject_user_id(state)
    reqs = handler.context_requirements(intent_with_uid)

    logger.info("context_router | domain=%s | reqs=%s", state["domain"], reqs)

    return {
        "intent": intent_with_uid,
        "requires_calendar": reqs.get("requires_calendar", False),
        "requires_bank": reqs.get("requires_bank", True),
        "requires_purchase_history": reqs.get("requires_purchase_history", False),
    }


# ─────────────────────────────────────────────
# 2. FETCHER NODES
# ─────────────────────────────────────────────


def _is_flight_domain(domain: str) -> bool:
    """Check if the domain is a flight-booking site."""
    d = domain.strip().lower()
    return any(k in d for k in ("skyscanner", "google.com/flights", "kayak", "kiwi"))


def _is_shopping_domain(domain: str) -> bool:
    """Check if the domain is a shopping site."""
    d = domain.strip().lower()
    return any(k in d for k in ("amazon", "ebay", "etsy", "walmart", "target", "asos"))


async def calendar_fetcher_node(state: AgentState) -> dict:
    handler = get_domain_handler(state["domain"])
    # Handler.fetch_calendar may be blocking (sync). Run in a thread to avoid blocking the event loop.
    try:
        events = await asyncio.to_thread(handler.fetch_calendar, state["intent"])
    except Exception:
        logger.exception(
            "calendar_fetcher | handler.fetch_calendar failed domain=%s user=%s",
            state.get("domain"),
            state.get("user_id"),
        )
        events = []
    # Normalise to list
    events = events or []
    logger.info("calendar_fetcher | events=%d", len(events))

    # Provide a small context_meta that downstream nodes (and the audit prompt)
    # can use to understand whether calendar data was available.
    context_meta = {"calendar": {"present": bool(events), "count": len(events)}}
    return {"calendar_events": events, "context_meta": context_meta}


async def bank_fetcher_node(state: AgentState) -> dict:
    """Fetch bank/transaction data from DB + merge Gmail email data.

    For flight domains: merges flight booking confirmations AND purchase
    receipts (hotel bookings, car hire, etc.) so the audit can detect
    clashes between flights and accommodation.
    For shopping domains: merges purchase receipts from Gmail.
    For all domains: the handler's own DB-based fetch_bank runs first.

    This node now:
      - Runs handler.fetch_bank in a thread to avoid blocking the event loop.
      - Tags gmail-extracted records with provenance (`source`, `source_id`).
      - Deduplicates merged records by (source, source_id) when available,
        and falls back to simple (merchant/airline, amount, date) heuristics.
      - Emits a small `context_meta` object describing counts.
    """
    handler = get_domain_handler(state["domain"])

    # Run potentially blocking DB fetch in thread
    try:
        txns = await asyncio.to_thread(handler.fetch_bank, state["intent"])
    except Exception:
        logger.exception(
            "bank_fetcher | handler.fetch_bank failed domain=%s user=%s",
            state.get("domain"),
            state.get("user_id"),
        )
        txns = []

    txns = txns or []
    original_db_count = len(txns)

    # Merge Gmail data with provenance tagging
    user_id = state.get("user_id", "")
    merged_gmail_flights = []
    merged_gmail_receipts = []
    try:
        if user_id:
            if _is_flight_domain(state["domain"]):
                email_flights = await gmail.fetch_email_flights(
                    user_id, lookback_days=180
                )
                email_flights = email_flights or []
                if email_flights:
                    logger.info("bank_fetcher | gmail flights=%d", len(email_flights))
                # Tag provenance
                for idx, item in enumerate(email_flights):
                    if not isinstance(item, dict):
                        continue
                    item.setdefault("source", "gmail")
                    # Prefer any explicit gmail id / booking_reference; fallback to derived id
                    sid = (
                        item.get("gmail_id")
                        or item.get("booking_reference")
                        or item.get("id")
                        or f"gmail_flight_{idx}"
                    )
                    item["source_id"] = sid
                    merged_gmail_flights.append(item)

                email_receipts = await gmail.fetch_email_receipts(
                    user_id, lookback_days=90
                )
                email_receipts = email_receipts or []
                if email_receipts:
                    logger.info(
                        "bank_fetcher | gmail receipts (hotel/other)=%d",
                        len(email_receipts),
                    )
                for idx, item in enumerate(email_receipts):
                    if not isinstance(item, dict):
                        continue
                    item.setdefault("source", "gmail")
                    sid = (
                        item.get("gmail_id") or item.get("id") or f"gmail_receipt_{idx}"
                    )
                    item["source_id"] = sid
                    merged_gmail_receipts.append(item)
            else:
                email_receipts = await gmail.fetch_email_receipts(
                    user_id, lookback_days=90
                )
                email_receipts = email_receipts or []
                if email_receipts:
                    logger.info("bank_fetcher | gmail receipts=%d", len(email_receipts))
                for idx, item in enumerate(email_receipts):
                    if not isinstance(item, dict):
                        continue
                    item.setdefault("source", "gmail")
                    sid = (
                        item.get("gmail_id") or item.get("id") or f"gmail_receipt_{idx}"
                    )
                    item["source_id"] = sid
                    merged_gmail_receipts.append(item)
    except Exception:
        logger.exception("bank_fetcher | gmail merge failed user=%s", user_id)

    # Extend txns with Gmail items (but we'll dedupe below)
    txns.extend(merged_gmail_flights)
    txns.extend(merged_gmail_receipts)

    # Deduplicate: prefer explicit (source, source_id). Fallback to (merchant/airline, amount, date).
    seen_keys: set = set()
    deduped: list[dict] = []
    for item in txns:
        if not isinstance(item, dict):
            continue
        src = item.get("source")
        sid = item.get("source_id")
        if src and sid:
            key = (src, str(sid))
        else:
            # Fallback heuristic keys
            merchant = (
                str(item.get("merchant") or item.get("airline") or "").strip().lower()
            )
            amount = str(
                item.get("amount")
                or item.get("price_amount")
                or item.get("price")
                or ""
            )
            date = str(item.get("date") or item.get("departure_date") or "")
            key = (merchant, amount, date)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)

    logger.info(
        "bank_fetcher | db=%d gmail_flights=%d gmail_receipts=%d total_after_merge=%d",
        original_db_count,
        len(merged_gmail_flights),
        len(merged_gmail_receipts),
        len(deduped),
    )

    context_meta = {
        "bank": {
            "db_count": original_db_count,
            "gmail_merged": {
                "flights": len(merged_gmail_flights),
                "receipts": len(merged_gmail_receipts),
            },
            "total_after_merge": len(deduped),
        }
    }

    return {"bank_transactions": deduped, "context_meta": context_meta}


async def purchase_history_fetcher_node(state: AgentState) -> dict:
    """Fetch purchase history from DB.

    Gmail receipts are already merged in bank_fetcher_node, so we don't
    duplicate the Gmail API + LLM calls here. The audit prompt receives
    both bank_transactions and purchase_history, so the LLM sees all data.
    """
    handler = get_domain_handler(state["domain"])
    purchases = handler.fetch_purchase_history(state["intent"])
    logger.info("purchase_history_fetcher | records=%d", len(purchases))
    return {"purchase_history": purchases}


# ─────────────────────────────────────────────
# 3. AUDIT NODE
# ─────────────────────────────────────────────


async def audit_node(state: AgentState) -> dict:
    """Cross-reference intent vs context via LLM.

    We also include a small, explicit context metadata block at the top of the
    prompt so the LLM knows when data sources were unavailable vs simply empty.
    """
    handler = get_domain_handler(state["domain"])

    # Build a lightweight context_meta summary from available state fields.
    # Keep it simple and ensure variables are always bound.
    calendar_events = state.get("calendar_events", []) or []
    bank_transactions = state.get("bank_transactions", []) or []
    purchase_history = state.get("purchase_history", []) or []

    # Merge context meta from multiple possible sources:
    #  - a top-level `context_meta` returned by fetchers (preferred)
    #  - legacy per-node meta keys like `purchase_history_meta`, `calendar_meta`, `bank_meta`
    context_meta: dict[str, Any] = {}

    top_cm = state.get("context_meta")
    if isinstance(top_cm, dict):
        # top-level context_meta may contain nested keys like 'calendar' or 'bank'
        context_meta.update(top_cm)

    # Merge purchase_history_meta if present (backwards compatibility)
    phm = state.get("purchase_history_meta")
    if isinstance(phm, dict):
        # ensure nested shape
        context_meta.setdefault("purchase_history", {})
        if "count" in phm:
            context_meta["purchase_history"]["count"] = phm.get("count", 0)
            context_meta["purchase_history"]["present"] = phm.get("count", 0) > 0

    # Merge calendar_meta if present
    cmeta = state.get("calendar_meta")
    if isinstance(cmeta, dict):
        context_meta.setdefault("calendar", {})
        if "count" in cmeta:
            context_meta["calendar"]["count"] = cmeta.get("count", 0)
            context_meta["calendar"]["present"] = cmeta.get("count", 0) > 0

    # Merge bank_meta if present
    bmeta = state.get("bank_meta")
    if isinstance(bmeta, dict):
        context_meta.setdefault("bank", {})
        # bank_meta may use different keys (db_count / total_count)
        if "total_count" in bmeta:
            context_meta["bank"]["count"] = bmeta.get("total_count", 0)
            context_meta["bank"]["present"] = bmeta.get("total_count", 0) > 0
        elif "db_count" in bmeta:
            context_meta["bank"]["count"] = bmeta.get("db_count", 0)
            context_meta["bank"]["present"] = bmeta.get("db_count", 0) > 0
        else:
            # fallback to presence of bank_transactions
            context_meta["bank"]["count"] = len(bank_transactions)
            context_meta["bank"]["present"] = bool(bank_transactions)

    # Ensure defaults if nothing provided by fetchers
    context_meta.setdefault(
        "calendar", {"present": bool(calendar_events), "count": len(calendar_events)}
    )
    context_meta.setdefault(
        "bank", {"present": bool(bank_transactions), "count": len(bank_transactions)}
    )
    context_meta.setdefault(
        "purchase_history",
        {"present": bool(purchase_history), "count": len(purchase_history)},
    )

    # Prepend context metadata to the prompt so the model can reason about missing data.
    base_prompt = handler.build_audit_prompt(
        intent=state["intent"],
        calendar_events=calendar_events,
        bank_transactions=bank_transactions,
        purchase_history=purchase_history,
    )

    meta_header = "Context metadata: " + json.dumps(context_meta) + "\n\n"
    prompt = meta_header + base_prompt

    # Guard: llm may be None in some environments (unconfigured). If it's not
    # available surface an empty risk list so the pipeline can continue safely.
    if llm is None:
        logger.error(
            "audit | no LLM configured; skipping audit for domain=%s", state["domain"]
        )
        return {"risk_factors": []}

    try:
        response = await llm.ainvoke(prompt)
        text = _extract_text(response.content)
    except Exception:
        logger.exception("audit | LLM invocation failed for domain=%s", state["domain"])
        # On LLM failure treat as no risks so we don't accidentally block the user flow.
        return {"risk_factors": []}

    data = _parse_json_response(text)
    risks: list[str] = data.get("risks", [])

    logger.info("audit | domain=%s | risks=%d", state["domain"], len(risks))
    return {"risk_factors": risks}


async def classification_node(state: AgentState) -> dict:
    """Classify the interaction into categories and mistake types."""
    risks = state.get("risk_factors", [])
    if not risks:
        return {"categories": [], "mistake_types": []}

    prompt = f"""You are an AI classifier for a neurodivergent support agent.

Interaction Context:
Domain: {state.get("domain")}
Intent: {state.get("intent")}

Identified Risks:
{risks}

Task:
1. Classify the interaction into one or more of these CATEGORIES:
   [electronics, travel, groceries, clothing, other]

2. Classify the risks into one or more of these MISTAKE TYPES:
   [double booking, impulse spending, date mixup, conflicting event, other]

Output JSON ONLY:
{{
  "categories": ["string"],
  "mistake_types": ["string"]
}}
"""

    if llm is None:
        return {"categories": ["other"], "mistake_types": ["other"]}

    try:
        response = await llm.ainvoke(prompt)
        text = _extract_text(response.content)
        data = _parse_json_response(text)
        return {
            "categories": data.get("categories", []),
            "mistake_types": data.get("mistake_types", []),
        }
    except Exception:
        logger.exception("classification | failed")
        return {"categories": ["other"], "mistake_types": ["other"]}


# ─────────────────────────────────────────────
# 4. DRAFTING NODE
# ─────────────────────────────────────────────


async def classification_node(state: AgentState) -> dict:
    """Classify the interaction into categories and mistake types."""
    risks = state.get("risk_factors", [])
    if not risks:
        return {"categories": [], "mistake_types": []}

    prompt = f"""You are an AI classifier for a neurodivergent support agent.

Interaction Context:
Domain: {state.get("domain")}
Intent: {state.get("intent")}

Identified Risks:
{risks}

Task:
1. Classify the interaction into one or more of these CATEGORIES:
   [electronics, travel, groceries, clothing, other]

2. Classify the risks into one or more of these MISTAKE TYPES:
   [double booking, impulse spending, date mixup, conflicting event, other]

Output JSON ONLY:
{{
  "categories": ["string"],
  "mistake_types": ["string"]
}}
"""

    if llm is None:
        return {"categories": ["other"], "mistake_types": ["other"]}

    try:
        response = await llm.ainvoke(prompt)
        text = _extract_text(response.content)
        data = _parse_json_response(text)
        return {
            "categories": data.get("categories", []),
            "mistake_types": data.get("mistake_types", []),
        }
    except Exception:
        logger.exception("classification | failed")
        return {"categories": ["other"], "mistake_types": ["other"]}


async def drafting_node(state: AgentState) -> dict:
    """Draft an empathetic intervention message (skipped if no risks).

    Behavior:
    - Attempt Gemini-first (if the adapter is importable and configured).
    - If Gemini returns an empty/failed response, fall back to the configured
      global LLM (from src.config.llm).
    - Collect best-effort LLM usage metadata (model, provider, response time,
      estimated tokens) and attach it to `state['llm_usage']` so downstream
      nodes (economics/storage) can include it in persisted economics.
    - Use a small retry/backoff for transient Gemini failures before falling
      back.
    """
    risk_factors = state.get("risk_factors", [])
    if not risk_factors:
        return {"intervention_message": None}

    handler = get_domain_handler(state["domain"])
    prompt = handler.build_drafting_prompt(risk_factors, state["intent"])

    # Local imports to avoid changing module-level imports and to keep this
    # function self-contained.
    import asyncio
    import time
    from types import SimpleNamespace

    gemini_client = None
    gemini_available = False
    try:
        # Prefer a LangChain-backed Gemini client exposed on config (gemini_llm)
        # when available. This lets us use the LangChainAdapter instance returned
        # by the config factory. If config.gemini_llm is not present, fall back
        # to the legacy local Gemini HTTP client implementation.
        from src import config

        if getattr(config, "gemini_llm", None) is not None:
            gemini_client = config.gemini_llm
            gemini_available = True
        else:
            # Fallback to legacy client if present on the filesystem / env.
            from src.gemini_client import GeminiClient

            # Create with defaults; the adapter reads its config from env vars.
            gemini_client = GeminiClient()
            gemini_available = True
    except Exception:
        gemini_client = None
        gemini_available = False

    response = None
    used_provider = None
    start_ts = time.monotonic()

    # 1) Gemini-first with retry/backoff (best-effort)
    if gemini_available and gemini_client is not None:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = await gemini_client.ainvoke(prompt)
                # Consider a non-empty textual content a success.
                content = getattr(resp, "content", None)
                if content:
                    response = resp
                    used_provider = "gemini"
                    break
                # Empty content: treat as transient and retry a couple times
                logger.warning(
                    "drafting | gemini returned empty content on attempt %d",
                    attempt + 1,
                )
            except Exception:
                # Log and retry with exponential backoff
                logger.exception("drafting | gemini attempt %d failed", attempt + 1)
            # backoff before next attempt
            await asyncio.sleep(0.2 * (2**attempt))

    # 2) Fallback to configured global LLM (config.llm) if Gemini absent/failed
    if response is None:
        try:
            from src import config

            fallback_llm = getattr(config, "llm", None)
            if fallback_llm is None:
                # No fallback available — return an empty message but ensure
                # llm_usage is recorded so economics/storage can handle it.
                response = SimpleNamespace(content="")
                used_provider = "none"
            else:
                resp = await fallback_llm.ainvoke(prompt)
                response = resp
                # If we fell back but the global provider is the Gemini adapter
                # (unlikely here), record appropriately. Otherwise mark as fallback.
                used_provider = "fallback"
        except Exception:
            logger.exception("drafting | fallback LLM invocation failed")
            response = SimpleNamespace(content="")
            used_provider = "fallback"

    elapsed_ms = (time.monotonic() - start_ts) * 1000.0
    message = _extract_text(response.content).strip()

    # Prefer token estimate from the LLM adapter's response.meta when available,
    # otherwise fall back to a simple whitespace-based heuristic.
    estimated_tokens = None
    meta = None
    try:
        meta = getattr(response, "meta", None) or {}
        if isinstance(meta, dict):
            estimated_tokens = (
                meta.get("estimated_tokens")
                or meta.get("estimated_total_tokens")
                or meta.get("estimated_completion_tokens")
                or (meta.get("provider_usage") or {}).get("total_tokens")
            )
        else:
            # Some adapters expose meta as a SimpleNamespace-like object
            estimated_tokens = getattr(meta, "estimated_tokens", None)
    except Exception:
        estimated_tokens = None

    if not estimated_tokens:
        # Fallback: conservative heuristic based on message length/words.
        estimated_tokens = max(1, int(len(message.split())))

    # Best-effort model detection: prefer meta.model, then adapter/client attributes,
    # then response attributes and finally the configured fallback.
    model_name = "unknown"
    try:
        if isinstance(meta, dict) and meta.get("model"):
            model_name = meta.get("model")
        elif used_provider == "gemini" and gemini_client is not None:
            model_name = getattr(gemini_client, "model", model_name)
        else:
            # Try fallback llm from config if present
            from src import config

            fallback_llm = getattr(config, "llm", None)
            model_name = getattr(
                fallback_llm, "model", getattr(response, "model", model_name)
            )
    except Exception:
        # Swallow model discovery errors — we don't want failures here to bubble up.
        logger.debug("drafting | model discovery failed", exc_info=True)

    llm_usage = {
        "provider": used_provider,
        "model": model_name,
        "response_time_ms": round(elapsed_ms, 2),
        "estimated_tokens": int(estimated_tokens),
    }
    # Attach raw meta if present for auditing and deeper inspection.
    if meta:
        llm_usage["meta"] = meta

    # Attach llm usage to the shared state for downstream nodes (economics/storage)
    state["llm_usage"] = llm_usage

    logger.info(
        "drafting | message_len=%d | provider=%s | model=%s | tokens=%d | rt_ms=%.1f",
        len(message),
        llm_usage.get("provider"),
        llm_usage.get("model"),
        llm_usage.get("estimated_tokens"),
        llm_usage.get("response_time_ms"),
    )

    return {"intervention_message": message}


# ─────────────────────────────────────────────
# 5. ECONOMICS NODE
# ─────────────────────────────────────────────


def economics_node(state: AgentState) -> dict:
    """Calculate compute cost, money saved, and platform fee.

    This node now prefers actual LLM token usage metadata when available:
    - If `state['llm_usage']['estimated_tokens']` is present we use that to
      compute a more accurate `compute_cost`.
    - We also attach the full `llm_usage` dict to the returned economics so it
      is persisted with the interaction audit record.
    """
    handler = get_domain_handler(state["domain"])

    # Prefer measured/estimated tokens from the LLM usage metadata when present.
    llm_usage = state.get("llm_usage") or {}
    tokens_used = llm_usage.get("estimated_tokens", ESTIMATED_TOKENS_PER_RUN)

    compute_cost = (tokens_used / 1_000_000) * COST_PER_MILLION_TOKENS
    is_intervening = bool(state.get("intervention_message"))
    item_price = handler.extract_item_price(state["intent"])
    hour = handler.extract_hour_of_day(state["intent"])

    logger.info(
        "economics | intervening=%s | price=%.2f | hour=%d | tokens=%s",
        is_intervening,
        item_price,
        hour,
        tokens_used,
    )

    platform_fee = round(compute_cost * PLATFORM_FEE_MULTIPLIER, 6)

    return {
        "compute_cost": round(compute_cost, 6),
        "money_saved": item_price if is_intervening else 0.0,
        "platform_fee": platform_fee if is_intervening else 0.0,
        "hour_of_day": hour,
        "llm_usage": llm_usage,
    }


# ─────────────────────────────────────────────
# 6. STORAGE NODE
# ─────────────────────────────────────────────


async def storage_node(state: AgentState) -> dict:
    """Persist domain-specific record + interaction audit trail.

    NOTE: domain-specific record storage (flights/purchases) is opt-in.
    By default the agent will persist the interaction audit trail but it will
    NOT write domain rows unless the calling context sets
    `state['store_domain_records'] = True`. This keeps tentative LLM detections
    out of the user's permanent records unless explicitly allowed (e.g. the
    frontend chooses to persist them or they are confirmed via email receipts).
    """
    user_id = state.get("user_id", "")
    domain = state.get("domain", "")
    intent = state.get("intent", {})

    handler = get_domain_handler(domain)

    # 1. Interaction audit trail — persist this first so we can provide an
    # interaction_id as provenance to any domain rows if the caller opts in.
    economics = {
        "compute_cost": state.get("compute_cost"),
        "money_saved": state.get("money_saved"),
        "platform_fee": state.get("platform_fee"),
        "hour_of_day": state.get("hour_of_day"),
    }

    interaction_id: str | None = None
    persisted = False

    if user_id:
        try:
            # Persist the interaction and capture the DB-generated id. The DB
            # helper returns {"id": "<uuid>"} on success or None on failure.
            result = db.store_interaction(
                user_id=user_id,
                domain=domain,
                intent=intent,
                risk_factors=state.get("risk_factors", []),
                categories=state.get("categories"),
                mistake_types=state.get("mistake_types"),
                intervention_message=state.get("intervention_message"),
                economics=economics,
                title=_generate_title(domain, intent),
            )
            if result and isinstance(result, dict):
                interaction_id = result.get("id")
            persisted = bool(interaction_id)
            logger.info(
                "storage | interaction store result id=%s user=%s stored=%s",
                interaction_id,
                user_id,
                persisted,
            )
            if not interaction_id:
                # Surface a clear failure so the agent pipeline can detect it
                # and the API can return an error to the client rather than
                # returning an inaccurate or randomly-generated id.
                raise RuntimeError(
                    f"storage_node: store_interaction returned no id for user={user_id} domain={domain}"
                )
        except Exception:
            logger.exception("storage | interaction store failed user=%s", user_id)
            # Raise to ensure upstream pipeline and the API surface a clear error
            # instead of silently continuing without a canonical DB id.
            raise
    else:
        logger.warning("storage | skipped — no user_id")

    # 2. Domain-specific (flights → flight_bookings, shopping → purchases)
    # Only write domain rows if explicitly allowed by the caller (opt-in).
    domain_stored = False
    if user_id:
        store_flag = bool(state.get("store_domain_records", False))
        if store_flag:
            try:
                # Call handler.store to persist domain records. Handlers may
                # choose to accept an interaction_id for provenance; if not,
                # they should still store tentative rows as the frontend prefers.
                try:
                    # Prefer positional interaction_id for handlers that accept it.
                    # Some handler.store implementations expect (user_id, intent, domain, interaction_id)
                    # while older ones accept only (user_id, intent, domain).
                    rows = handler.store(user_id, intent, domain, interaction_id)  # type: ignore[arg-type]
                except TypeError:
                    # Backwards-compatible: some handlers expect only (user_id, intent, domain)
                    rows = handler.store(user_id, intent, domain)
                logger.info("storage | domain rows=%d | user=%s", len(rows), user_id)
                domain_stored = True
            except Exception:
                logger.exception("storage | domain store failed user=%s", user_id)
        else:
            logger.info(
                "storage | domain store skipped for user=%s domain=%s (opt-in disabled)",
                user_id,
                domain,
            )

    # Return the stored flag(s) and, when available, the DB-generated interaction id
    # so upstream callers (e.g. the API route) can surface the canonical server id.
    return {
        "stored": persisted,
        "interaction_id": interaction_id,
        "domain_stored": domain_stored,
    }


# ─────────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────────


def _route_after_audit(state: AgentState) -> str:
    return "classification" if state.get("risk_factors") else "economics"


def build_agent(*, checkpointer=None):
    """Build and compile the LangGraph agent.

    Returns a compiled graph ready for ``await graph.ainvoke(state, config=...)``.
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()

    # Ensure initial state includes empty lists for categories and mistake_types
    def initial_state(state):
        state.setdefault("categories", [])
        state.setdefault("mistake_types", [])
        return state

    g = StateGraph(AgentState, initial_state=initial_state)

    # Register nodes
    g.add_node("context_router", context_router_node)
    g.add_node("calendar_fetcher", calendar_fetcher_node)
    g.add_node("bank_fetcher", bank_fetcher_node)
    g.add_node("purchase_history_fetcher", purchase_history_fetcher_node)
    g.add_node("audit", audit_node)

    g.add_node("classification", classification_node)
    g.add_node("drafting", drafting_node)
    g.add_node("economics", economics_node)
    g.add_node("storage", storage_node)

    # Edges
    g.add_edge(START, "context_router")

    # Fan-out to parallel fetchers
    g.add_edge("context_router", "calendar_fetcher")
    g.add_edge("context_router", "bank_fetcher")
    g.add_edge("context_router", "purchase_history_fetcher")

    # Fan-in to audit
    g.add_edge("calendar_fetcher", "audit")
    g.add_edge("bank_fetcher", "audit")
    g.add_edge("purchase_history_fetcher", "audit")

    # Conditional: audit → classification (if risks) or economics (if safe)
    g.add_conditional_edges(
        "audit",
        _route_after_audit,
        {"classification": "classification", "economics": "economics"},
    )

    # Linear tail
    g.add_edge("classification", "drafting")
    g.add_edge("drafting", "economics")
    g.add_edge("economics", "storage")
    g.add_edge("storage", END)

    return g.compile(checkpointer=checkpointer)
