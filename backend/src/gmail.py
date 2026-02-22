"""Gmail API client — fetch and parse purchase receipts & flight booking confirmations.

Uses httpx to talk directly to the Gmail REST API (no heavy SDK).
Tokens are stored in the `email_connections` table and refreshed automatically.

Instead of fragile regex parsing, we feed raw email content to the LLM
and ask it to extract structured purchase / flight data.

Public API:
    fetch_email_receipts(user_id, lookback_days)   → list[dict]
    fetch_email_flights(user_id, lookback_days)     → list[dict]
    resolve_email_address(access_token)             → str | None
    refresh_access_token(refresh_token)             → dict | None
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any

import httpx

from src import db
from src.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, llm

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

_RECEIPT_QUERY = (
    "subject:(receipt OR order OR confirmation OR invoice OR purchase OR payment) "
    "-label:spam"
)
_FLIGHT_QUERY = (
    "subject:(flight OR booking OR itinerary OR boarding OR e-ticket OR airline "
    "OR reservation) "
    "-label:spam"
)

# Max emails to pull per category to keep LLM costs reasonable
_MAX_MESSAGES = 15
# Max emails to feed into a single LLM extraction call
_BATCH_SIZE = 5


# ─────────────────────────────────────────────
# Token Management
# ─────────────────────────────────────────────


async def refresh_access_token(refresh_token: str) -> dict[str, Any] | None:
    """Exchange a refresh token for a new access token via Google OAuth.

    Returns {"access_token": ..., "expires_in": ...} on success, None on failure.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.error("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_ENDPOINT,
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Token refresh failed: %d — %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return None
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 3600),
            }
    except Exception:
        logger.exception("Token refresh request failed")
        return None


async def resolve_email_address(access_token: str) -> str | None:
    """Use the Google userinfo endpoint to get the email for a token."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                return resp.json().get("email")
            logger.warning(
                "Userinfo failed: %d — %s", resp.status_code, resp.text[:200]
            )
            return None
    except Exception:
        logger.exception("resolve_email_address failed")
        return None


# ─────────────────────────────────────────────
# Internal: get a working access token for a user
# ─────────────────────────────────────────────


async def _get_valid_token(user_id: str) -> dict[str, Any] | None:
    """Retrieve the access token for a user, refreshing if expired.

    Returns a dict with metadata:
      {
        "access_token": str | None,
        "has_refresh_token": bool,
        "token_refreshed": bool,
        "refresh_failed": bool
      }
    Returns None when there is no email connection.
    """
    uid = _uuid.UUID(user_id)
    conn = db.get_email_connection_raw(uid)
    if not conn:
        return None

    access_token = conn.get("access_token")
    expires_at = conn.get("token_expires_at")
    has_refresh = bool(conn.get("refresh_token"))

    # If we have an expiry and it's still valid, return current token
    if (
        expires_at
        and isinstance(expires_at, datetime)
        and expires_at > datetime.utcnow()
    ):
        return {
            "access_token": access_token,
            "has_refresh_token": has_refresh,
            "token_refreshed": False,
            "refresh_failed": False,
        }

    # Otherwise try to refresh
    refresh_tok = conn.get("refresh_token")
    if not refresh_tok:
        # No refresh token — return existing token (may be expired) and flag absence
        return {
            "access_token": access_token,
            "has_refresh_token": False,
            "token_refreshed": False,
            "refresh_failed": False,
        }

    result = await refresh_access_token(refresh_tok)
    if not result:
        # Refresh failed — return existing token and mark failure for observability
        logger.warning("Token refresh failed for user=%s", user_id)
        return {
            "access_token": access_token,
            "has_refresh_token": True,
            "token_refreshed": False,
            "refresh_failed": True,
        }

    new_token = result["access_token"]
    new_expires = datetime.utcnow() + timedelta(seconds=result.get("expires_in", 3600))
    db.update_email_token(uid, new_token, new_expires)

    return {
        "access_token": new_token,
        "has_refresh_token": True,
        "token_refreshed": True,
        "refresh_failed": False,
    }


# ─────────────────────────────────────────────
# Gmail API helpers
# ─────────────────────────────────────────────


async def _search_messages(
    access_token: str,
    query: str,
    max_results: int = _MAX_MESSAGES,
) -> list[str]:
    """Search Gmail and return a list of message IDs."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_GMAIL_API}/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "maxResults": max_results},
            )
            if resp.status_code != 200:
                logger.warning(
                    "Gmail search failed: %d — %s", resp.status_code, resp.text[:300]
                )
                return []
            data = resp.json()
            messages = data.get("messages", [])
            return [m["id"] for m in messages]
    except Exception:
        logger.exception("Gmail search request failed")
        return []


async def _get_message(access_token: str, msg_id: str) -> dict[str, Any] | None:
    """Fetch a single message with metadata + snippet."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_GMAIL_API}/messages/{msg_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "Date"],
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Gmail get message %s failed: %d", msg_id, resp.status_code
                )
                return None
            return resp.json()
    except Exception:
        logger.exception("Gmail get message %s failed", msg_id)
        return None


def _extract_headers(msg: dict[str, Any]) -> dict[str, str]:
    """Pull Subject, From, Date from message metadata headers."""
    headers: dict[str, str] = {}
    for h in msg.get("payload", {}).get("headers", []):
        name = h.get("name", "").lower()
        if name in ("subject", "from", "date"):
            headers[name] = h.get("value", "")
    return headers


async def _fetch_message_summaries(
    access_token: str,
    query: str,
    max_results: int = _MAX_MESSAGES,
) -> list[dict[str, str]]:
    """Search Gmail and return a list of {subject, from, date, snippet} dicts."""
    msg_ids = await _search_messages(access_token, query, max_results)
    if not msg_ids:
        return []

    summaries: list[dict[str, str]] = []
    for mid in msg_ids:
        msg = await _get_message(access_token, mid)
        if not msg:
            continue
        headers = _extract_headers(msg)
        summaries.append(
            {
                "gmail_id": mid,
                "subject": headers.get("subject", ""),
                "from": headers.get("from", ""),
                "date": headers.get("date", ""),
                "snippet": msg.get("snippet", ""),
            }
        )

    logger.info("Fetched %d email summaries for query: %s", len(summaries), query[:60])
    return summaries


# ─────────────────────────────────────────────
# LLM-based extraction
# ─────────────────────────────────────────────

_RECEIPT_EXTRACTION_PROMPT = """You are a data-extraction assistant. Below are email summaries (subject, from, date, snippet) from a user's Gmail inbox. Each one is likely a purchase receipt or order confirmation.

For EACH email that represents a real product purchase or payment, extract:
- merchant: the store / seller name
- item: what was bought (brief description, or "Order" if unclear)
- amount: the total price as a number (no currency symbol)
- currency: 3-letter currency code (GBP, USD, EUR, etc.) — infer from context if not explicit
- date: purchase date in YYYY-MM-DD format (use the email date if no other date is clear)
- source: always "gmail"

Skip emails that are NOT actual purchase receipts (e.g. newsletters, marketing, shipping updates without price info, password resets).

**Emails:**
{emails}

**Output:**
Return ONLY a raw JSON array of objects. If no valid receipts are found, return: []
Do NOT wrap in markdown code fences. Return ONLY the JSON array.
Example: [{{"merchant": "Amazon", "item": "Wireless Mouse", "amount": 29.99, "currency": "GBP", "date": "2025-01-15", "source": "gmail"}}]"""

_FLIGHT_EXTRACTION_PROMPT = """You are a data-extraction assistant. Below are email summaries (subject, from, date, snippet) from a user's Gmail inbox. Each one is likely related to a flight booking or travel itinerary.

For EACH email that represents a real flight booking or confirmation, extract:
- airline: the airline name
- flight_number: flight number if available (e.g. "BA 245"), or null
- departure_airport: departure airport name or IATA code if available, or null
- arrival_airport: arrival/destination airport name or IATA code if available, or null
- departure_date: flight date in YYYY-MM-DD format if available, or null
- price_amount: ticket price as a number if available, or null
- price_currency: 3-letter currency code if available, or "GBP"
- booking_reference: booking/confirmation reference if available, or null
- source: always "gmail"

Skip emails that are NOT actual flight bookings (e.g. flight deal newsletters, loyalty program updates, car rental confirmations).

**Emails:**
{emails}

**Output:**
Return ONLY a raw JSON array of objects. If no valid flight bookings are found, return: []
Do NOT wrap in markdown code fences. Return ONLY the JSON array.
Example: [{{"airline": "Ryanair", "flight_number": "FR 123", "departure_airport": "STN", "arrival_airport": "BCN", "departure_date": "2025-03-20", "price_amount": 45.99, "price_currency": "GBP", "booking_reference": "ABC123", "source": "gmail"}}]"""


def _parse_llm_json(raw: str) -> list[dict[str, Any]]:
    """Best-effort parse of LLM output that should be a JSON array."""
    cleaned = raw.strip()
    # Strip markdown fences if present
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    # Sometimes the model wraps in {"results": [...]} — handle that
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("results", "receipts", "flights", "data", "items"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            return [parsed]
        return []
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "Failed to parse LLM extraction JSON: %s | raw=%s", exc, raw[:200]
        )
        return []


async def _extract_with_llm(
    prompt_template: str,
    summaries: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Feed email summaries to the LLM in batches and collect structured results."""
    all_results: list[dict[str, Any]] = []

    for i in range(0, len(summaries), _BATCH_SIZE):
        batch = summaries[i : i + _BATCH_SIZE]
        emails_text = "\n\n".join(
            f"--- Email {j + 1} ---\n"
            f"Subject: {e['subject']}\n"
            f"From: {e['from']}\n"
            f"Date: {e['date']}\n"
            f"Snippet: {e['snippet']}"
            for j, e in enumerate(batch)
        )

        prompt = prompt_template.format(emails=emails_text)

        try:
            response = await llm.ainvoke(prompt)
            content = response.content
            if isinstance(content, list):
                # Handle list-of-blocks response format
                text_parts = []
                for block in content:
                    if isinstance(block, str):
                        text_parts.append(block)
                    elif isinstance(block, dict) and "text" in block:
                        text_parts.append(str(block["text"]))
                text = "\n".join(text_parts)
            else:
                text = str(content)

            parsed = _parse_llm_json(text)
            all_results.extend(parsed)
            logger.info(
                "LLM extraction batch %d-%d: extracted %d items",
                i,
                i + len(batch),
                len(parsed),
            )
        except Exception:
            logger.exception("LLM extraction failed for batch %d-%d", i, i + len(batch))
            continue

    return all_results


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────


async def fetch_email_receipts(
    user_id: str,
    lookback_days: int = 90,
) -> list[dict[str, Any]]:
    """Fetch purchase receipts from the user's Gmail using LLM extraction.

    Returns a list of dicts with keys: merchant, item, amount, currency, date, source.
    Returns an empty list if the user has no email connection or on any error.
    """
    token_info = await _get_valid_token(user_id)
    access_token = token_info.get("access_token") if token_info else None

    if not access_token:
        if token_info is None:
            logger.info("fetch_email_receipts | user=%s | no email connection", user_id)
        else:
            logger.warning(
                "fetch_email_receipts | user=%s | no valid access token (refresh_failed=%s, has_refresh_token=%s)",
                user_id,
                token_info.get("refresh_failed"),
                token_info.get("has_refresh_token"),
            )
        return []

    # Build date-bounded query
    after_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime(
        "%Y/%m/%d"
    )
    query = f"{_RECEIPT_QUERY} after:{after_date}"

    summaries = await _fetch_message_summaries(access_token, query)
    if not summaries:
        logger.info("fetch_email_receipts | user=%s | no emails found", user_id)
        return []

    results = await _extract_with_llm(_RECEIPT_EXTRACTION_PROMPT, summaries)
    logger.info(
        "fetch_email_receipts | user=%s | emails=%d | receipts=%d",
        user_id,
        len(summaries),
        len(results),
    )
    return results


async def fetch_email_flights(
    user_id: str,
    lookback_days: int = 180,
) -> list[dict[str, Any]]:
    """Fetch flight booking confirmations from the user's Gmail using LLM extraction.

    Returns a list of dicts with keys: airline, flight_number, departure_airport,
    arrival_airport, departure_date, price_amount, price_currency, booking_reference, source.
    Returns an empty list if the user has no email connection or on any error.
    """
    token_info = await _get_valid_token(user_id)
    access_token = token_info.get("access_token") if token_info else None

    if not access_token:
        if token_info is None:
            logger.info("fetch_email_flights | user=%s | no email connection", user_id)
        else:
            logger.warning(
                "fetch_email_flights | user=%s | no valid access token (refresh_failed=%s, has_refresh_token=%s)",
                user_id,
                token_info.get("refresh_failed"),
                token_info.get("has_refresh_token"),
            )
        return []

    after_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime(
        "%Y/%m/%d"
    )
    query = f"{_FLIGHT_QUERY} after:{after_date}"

    summaries = await _fetch_message_summaries(access_token, query)
    if not summaries:
        logger.info("fetch_email_flights | user=%s | no emails found", user_id)
        return []

    results = await _extract_with_llm(_FLIGHT_EXTRACTION_PROMPT, summaries)
    logger.info(
        "fetch_email_flights | user=%s | emails=%d | flights=%d",
        user_id,
        len(summaries),
        len(results),
    )
    return results
