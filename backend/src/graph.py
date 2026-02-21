"""LangGraph pipeline — all node functions and graph builder in one module.

Nodes delegate domain-specific logic to handlers via the registry,
keeping this file fully domain-agnostic.

Pipeline:
    context_router → (calendar_fetcher, bank_fetcher, purchase_history_fetcher)
        → audit → [drafting if risks] → economics → storage → END
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src import db
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


async def calendar_fetcher_node(state: AgentState) -> dict:
    handler = get_domain_handler(state["domain"])
    events = handler.fetch_calendar(state["intent"])
    logger.info("calendar_fetcher | events=%d", len(events))
    return {"calendar_events": events}


async def bank_fetcher_node(state: AgentState) -> dict:
    handler = get_domain_handler(state["domain"])
    txns = handler.fetch_bank(state["intent"])
    logger.info("bank_fetcher | transactions=%d", len(txns))
    return {"bank_transactions": txns}


async def purchase_history_fetcher_node(state: AgentState) -> dict:
    handler = get_domain_handler(state["domain"])
    purchases = handler.fetch_purchase_history(state["intent"])
    logger.info("purchase_history_fetcher | records=%d", len(purchases))
    return {"purchase_history": purchases}


# ─────────────────────────────────────────────
# 3. AUDIT NODE
# ─────────────────────────────────────────────


async def audit_node(state: AgentState) -> dict:
    """Cross-reference intent vs context via LLM."""
    handler = get_domain_handler(state["domain"])

    prompt = handler.build_audit_prompt(
        intent=state["intent"],
        calendar_events=state.get("calendar_events", []),
        bank_transactions=state.get("bank_transactions", []),
        purchase_history=state.get("purchase_history", []),
    )

    response = await llm.ainvoke(prompt)
    text = _extract_text(response.content)
    data = _parse_json_response(text)
    risks: list[str] = data.get("risks", [])

    logger.info("audit | domain=%s | risks=%d", state["domain"], len(risks))
    return {"risk_factors": risks}


# ─────────────────────────────────────────────
# 4. DRAFTING NODE
# ─────────────────────────────────────────────


async def drafting_node(state: AgentState) -> dict:
    """Draft an empathetic intervention message (skipped if no risks)."""
    risk_factors = state.get("risk_factors", [])
    if not risk_factors:
        return {"intervention_message": None}

    handler = get_domain_handler(state["domain"])
    prompt = handler.build_drafting_prompt(risk_factors, state["intent"])

    response = await llm.ainvoke(prompt)
    message = _extract_text(response.content).strip()

    logger.info("drafting | message_len=%d", len(message))
    return {"intervention_message": message}


# ─────────────────────────────────────────────
# 5. ECONOMICS NODE
# ─────────────────────────────────────────────


def economics_node(state: AgentState) -> dict:
    """Calculate compute cost, money saved, and platform fee."""
    handler = get_domain_handler(state["domain"])

    compute_cost = (ESTIMATED_TOKENS_PER_RUN / 1_000_000) * COST_PER_MILLION_TOKENS
    is_intervening = bool(state.get("intervention_message"))
    item_price = handler.extract_item_price(state["intent"])
    hour = handler.extract_hour_of_day(state["intent"])

    logger.info(
        "economics | intervening=%s | price=%.2f | hour=%d",
        is_intervening,
        item_price,
        hour,
    )

    platform_fee = round(compute_cost * PLATFORM_FEE_MULTIPLIER, 6)

    return {
        "compute_cost": round(compute_cost, 6),
        "money_saved": item_price if is_intervening else 0.0,
        "platform_fee": platform_fee if is_intervening else 0.0,
        "hour_of_day": hour,
    }


# ─────────────────────────────────────────────
# 6. STORAGE NODE
# ─────────────────────────────────────────────


async def storage_node(state: AgentState) -> dict:
    """Persist domain-specific record + interaction audit trail."""
    user_id = state.get("user_id", "")
    domain = state.get("domain", "")
    intent = state.get("intent", {})

    handler = get_domain_handler(domain)

    # 1. Domain-specific (flights → flight_bookings, shopping → purchases)
    if user_id:
        try:
            rows = handler.store(user_id, intent, domain)
            logger.info("storage | domain rows=%d | user=%s", len(rows), user_id)
        except Exception:
            logger.exception("storage | domain store failed user=%s", user_id)

    # 2. Interaction audit trail
    economics = {
        "compute_cost": state.get("compute_cost"),
        "money_saved": state.get("money_saved"),
        "platform_fee": state.get("platform_fee"),
        "hour_of_day": state.get("hour_of_day"),
    }

    if user_id:
        try:
            db.store_interaction(
                user_id=user_id,
                domain=domain,
                intent=intent,
                risk_factors=state.get("risk_factors", []),
                intervention_message=state.get("intervention_message"),
                economics=economics,
                title=_generate_title(domain, intent),
            )
        except Exception:
            logger.exception("storage | interaction store failed user=%s", user_id)
    else:
        logger.warning("storage | skipped — no user_id")

    return {"stored": True}


# ─────────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────────


def _route_after_audit(state: AgentState) -> str:
    return "drafting" if state.get("risk_factors") else "economics"


def build_agent(*, checkpointer=None):
    """Build and compile the LangGraph agent.

    Returns a compiled graph ready for ``await graph.ainvoke(state, config=...)``.
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()

    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("context_router", context_router_node)
    g.add_node("calendar_fetcher", calendar_fetcher_node)
    g.add_node("bank_fetcher", bank_fetcher_node)
    g.add_node("purchase_history_fetcher", purchase_history_fetcher_node)
    g.add_node("audit", audit_node)
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

    # Conditional: audit → drafting (if risks) or economics (if safe)
    g.add_conditional_edges(
        "audit",
        _route_after_audit,
        {"drafting": "drafting", "economics": "economics"},
    )

    # Linear tail
    g.add_edge("drafting", "economics")
    g.add_edge("economics", "storage")
    g.add_edge("storage", END)

    return g.compile(checkpointer=checkpointer)
