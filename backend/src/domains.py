"""Domain handlers and registry — all in one module.

Each handler knows how to:
  • Declare which data sources it needs (calendar, bank, purchase history)
  • Fetch context data (DB-backed)
  • Build LLM prompts for audit and drafting
  • Extract price / hour-of-day for economics
  • Store confirmed actions to the DB

The registry maps website domains to handlers via suffix matching.
"""

from __future__ import annotations

import datetime
import logging
import uuid as _uuid
from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any

import httpx
from icalendar import Calendar

from src import db

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════
# iCal Fetcher
# ═════════════════════════════════════════════


def _fmt_ical_dt(dt: Any) -> str:
    """Format an icalendar date/datetime property to a string."""
    if dt is None:
        return ""
    v = dt.dt if hasattr(dt, "dt") else dt
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    return v.isoformat()


def _parse_ical_feed(content: bytes, start: date, end: date) -> list[dict]:
    """Parse raw .ics bytes and return events within [start, end]."""
    cal = Calendar.from_ical(content)
    events: list[dict] = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        summary = str(component.get("summary", ""))

        if not dtstart:
            continue

        dt_val = dtstart.dt
        ev_date = dt_val.date() if isinstance(dt_val, datetime.datetime) else dt_val

        if not (start <= ev_date <= end):
            continue

        events.append(
            {
                "summary": summary,
                "start": _fmt_ical_dt(dtstart),
                "end": _fmt_ical_dt(dtend),
            }
        )

    return events


def fetch_user_calendar_events(
    user_id: str, start: date, end: date
) -> list[dict] | None:
    """Fetch events from ALL of a user's saved iCal calendars.

    Queries the user_calendars table for URLs, fetches each feed,
    and merges the results. Returns None if the user has no calendars
    (so the caller falls back to mock data).
    """
    try:
        uid = _uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None

    urls = db.get_calendar_urls(uid)
    if not urls:
        return None

    all_events: list[dict] = []
    for url in urls:
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            events = _parse_ical_feed(resp.content, start, end)
            all_events.extend(events)
            logger.info(
                "iCal fetch | user=%s | %s | events=%d", user_id, url, len(events)
            )
        except Exception:
            logger.exception(
                "Failed to fetch/parse iCal for user=%s url=%s", user_id, url
            )
            continue

    logger.info(
        "iCal fetch | user=%s | total=%d from %d calendar(s)",
        user_id,
        len(all_events),
        len(urls),
    )
    return all_events


# ═════════════════════════════════════════════
# Abstract Base
# ═════════════════════════════════════════════


class DomainHandler(ABC):
    """Strategy interface every domain handler must implement."""

    @abstractmethod
    def context_requirements(self, intent: dict[str, Any]) -> dict[str, bool]:
        """Return {"requires_calendar": bool, "requires_bank": bool, "requires_purchase_history": bool}."""
        ...

    @abstractmethod
    def fetch_calendar(self, intent: dict[str, Any]) -> list[dict]: ...

    @abstractmethod
    def fetch_bank(self, intent: dict[str, Any]) -> list[dict]: ...

    @abstractmethod
    def fetch_purchase_history(self, intent: dict[str, Any]) -> list[dict]: ...

    @abstractmethod
    def build_audit_prompt(
        self,
        intent: dict[str, Any],
        calendar_events: list[dict],
        bank_transactions: list[dict],
        purchase_history: list[dict],
    ) -> str: ...

    @abstractmethod
    def build_drafting_prompt(
        self, risk_factors: list[str], intent: dict[str, Any]
    ) -> str: ...

    @abstractmethod
    def extract_item_price(self, intent: dict[str, Any]) -> float: ...

    @abstractmethod
    def extract_hour_of_day(self, intent: dict[str, Any]) -> int: ...

    @abstractmethod
    def store(
        self, user_id: str, intent: dict[str, Any], domain: str
    ) -> list[dict]: ...


# ═════════════════════════════════════════════
# Flight Handler
# ═════════════════════════════════════════════


class FlightDomainHandler(DomainHandler):
    """Handles flight-booking intents (Skyscanner, Google Flights, etc.)."""

    def context_requirements(self, intent: dict[str, Any]) -> dict[str, bool]:
        return {
            "requires_calendar": True,
            "requires_bank": True,
            "requires_purchase_history": False,
        }

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _leg_dates(intent: dict[str, Any]) -> list[date]:
        dates: list[date] = []
        for leg in ("outbound", "return"):
            raw = intent.get(leg, {}).get("departure_date")
            if raw:
                try:
                    dates.append(date.fromisoformat(raw))
                except (ValueError, TypeError):
                    pass
        return dates

    @staticmethod
    def _calendar_window(dates: list[date], days: int = 3) -> tuple[date, date]:
        if not dates:
            today = date.today()
            return today, today
        return min(dates) - timedelta(days=days), max(dates) + timedelta(days=days)

    @staticmethod
    def _extract_destination(intent: dict[str, Any]) -> str:
        arrival = intent.get("outbound", {}).get("arrival_airport", "")
        parts = arrival.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isalpha() and parts[0].isupper():
            return parts[1]
        return arrival.strip()

    # ── data fetching ────────────────────────────────────────────────

    def fetch_calendar(self, intent: dict[str, Any]) -> list[dict]:
        leg_dates = self._leg_dates(intent)
        start, end = self._calendar_window(leg_dates)

        user_id = intent.get("_user_id", "")
        if not user_id:
            logger.info("calendar_fetch | no user_id, returning empty")
            return []

        events = fetch_user_calendar_events(user_id, start, end)
        if events is None:
            logger.info(
                "calendar_fetch | user has no calendars | window=%s→%s", start, end
            )
            return []

        logger.info(
            "calendar_fetch | user calendars | window=%s→%s | events=%d",
            start,
            end,
            len(events),
        )
        return events

    def fetch_bank(self, intent: dict[str, Any]) -> list[dict]:
        """Query DB for existing flight bookings near these dates + destination."""
        leg_dates = self._leg_dates(intent)
        destination = self._extract_destination(intent)
        user_id = intent.get("_user_id", "")

        nearby: list[dict] = []
        dest_flights: list[dict] = []

        if user_id and leg_dates:
            try:
                nearby = db.get_flights_near_dates(user_id, leg_dates, window_days=3)
            except Exception:
                logger.exception("DB query for nearby flights failed")

        if user_id and destination:
            try:
                dest_flights = db.get_flights_to_destination(
                    user_id, destination, lookback_days=180
                )
            except Exception:
                logger.exception("DB query for destination flights failed")

        # Merge + deduplicate
        seen: set[str] = set()
        merged: list[dict] = []
        for f in nearby + dest_flights:
            fid = f.get("id", "")
            if fid and fid not in seen:
                seen.add(fid)
                merged.append(f)

        if merged:
            logger.info("flight DB fetch | user=%s | results=%d", user_id, len(merged))
            return merged

        # Mock fallback for demo / new users
        logger.info("flight DB fetch | no results, using mock fallback")
        return [
            {
                "merchant": "EasyJet",
                "destination": "Barcelona",
                "amount": 89,
                "currency": "GBP",
                "date": "2026-02-20",
                "source": "mock_fallback",
            },
        ]

    def fetch_purchase_history(self, intent: dict[str, Any]) -> list[dict]:
        return []

    # ── prompts ──────────────────────────────────────────────────────

    def build_audit_prompt(
        self,
        intent: dict[str, Any],
        calendar_events: list[dict],
        bank_transactions: list[dict],
        purchase_history: list[dict],
    ) -> str:
        outbound = intent.get("outbound", {})
        return_leg = intent.get("return", {})
        dep_time = outbound.get("departure_time", "unknown")
        arr_time = outbound.get("arrival_time", "unknown")
        ret_dep_time = return_leg.get("departure_time", "unknown")
        ret_arr_time = return_leg.get("arrival_time", "unknown")
        dep_date = outbound.get("departure_date", "unknown")
        ret_date = return_leg.get("departure_date", "unknown")

        return f"""You are an AI protecting a neurodivergent user from double-booking flights, scheduling conflicts, and travel fatigue.

**Flight the user wants to book RIGHT NOW:**
{intent}

**Their calendar events for ±3 days around each flight leg:**
{calendar_events}

**Their existing flight bookings and travel history:**
{bank_transactions}

Analyse the above data and look for ALL of the following risk categories:

1. **Schedule conflict** – A calendar event that overlaps with, or falls
   dangerously close to, a flight departure or arrival window (including
   time to get to/from the airport — assume ~2 hours each way).

2. **Double booking** – The user already has a flight booked to the same
   destination around the same dates, or overlapping travel dates.

3. **Fatigue / exhaustion risk** – Consider the full travel timeline:
   • Outbound departs {dep_date} at {dep_time}, arrives {arr_time}
   • Return departs {ret_date} at {ret_dep_time}, arrives {ret_arr_time}
   Will the user be exhausted? Examples:
   - Arriving late at night then having an early morning event
   - A red-eye flight followed by a work commitment
   - Very short turnaround between arriving home and the next obligation

4. **Too-early / too-late flight** – Flag if any flight:
   • Departs before 06:00 (very early, sleep disruption)
   • Arrives after 23:00 (very late, safety and fatigue concern)
   • Departs within 2 hours of the user waking up for an early event

5. **Wasted money** – An existing transaction showing they already paid
   for a similar trip that covers the same or overlapping period.

6. **Self-transfer warning** – If any leg in the intent has
   `"self_transfer": true`, the passenger must collect their luggage,
   go through security again, and re-check in at the connecting
   airport.  This is stressful, risky for tight connections, and
   especially overwhelming for neurodivergent travellers.  Always
   flag this clearly.

Return ONLY raw JSON: {{"risks": ["risk description 1", "risk description 2"]}}
If there are absolutely NO risks, return: {{"risks": []}}"""

    def build_drafting_prompt(
        self, risk_factors: list[str], intent: dict[str, Any]
    ) -> str:
        outbound = intent.get("outbound", {})
        dep = outbound.get("departure_airport", "")
        arr = outbound.get("arrival_airport", "")
        flight_desc = f"{dep} → {arr}" if dep and arr else "this flight"

        return (
            "Write a single short, empathetic warning message for a neurodivergent "
            f"user who is about to book a flight ({flight_desc}). "
            f"Address these risks:\n{risk_factors}\n\n"
            "Start with an appropriate emoji. Keep it under 2 sentences. "
            "Be warm and supportive, not patronising. If the risk involves "
            "tiredness or scheduling stress, acknowledge how exhausting travel "
            "can be and gently suggest they double-check. If the risk involves "
            "a self-transfer, explain clearly that they'll need to collect their "
            "luggage, go through security again, and re-check in — and that "
            "this can be overwhelming and stressful, especially with tight connections."
        )

    # ── economics ────────────────────────────────────────────────────

    def extract_item_price(self, intent: dict[str, Any]) -> float:
        try:
            return float(intent.get("selected_price", {}).get("amount", 0))
        except (TypeError, ValueError):
            return 0.0

    def extract_hour_of_day(self, intent: dict[str, Any]) -> int:
        try:
            time_str = intent.get("outbound", {}).get("departure_time", "12:00")
            return int(time_str.split(":")[0])
        except (TypeError, ValueError, IndexError):
            return 12

    # ── storage ──────────────────────────────────────────────────────

    def store(self, user_id: str, intent: dict[str, Any], domain: str) -> list[dict]:
        try:
            return db.store_flight_booking(user_id, intent)
        except Exception:
            logger.exception("Failed to store flight booking user=%s", user_id)
            return []


# ═════════════════════════════════════════════
# Shopping Handler
# ═════════════════════════════════════════════


class ShoppingDomainHandler(DomainHandler):
    """Handles product-purchase intents (Amazon, etc.)."""

    def context_requirements(self, intent: dict[str, Any]) -> dict[str, bool]:
        return {
            "requires_calendar": False,
            "requires_bank": True,
            "requires_purchase_history": True,
        }

    def fetch_calendar(self, intent: dict[str, Any]) -> list[dict]:
        return []

    def fetch_bank(self, intent: dict[str, Any]) -> list[dict]:
        """Recent purchases from DB (for duplicate / impulse detection)."""
        user_id = intent.get("_user_id", "")
        if user_id:
            try:
                recent = db.get_recent_purchases(user_id, lookback_days=90)
                if recent:
                    logger.info(
                        "shopping DB | user=%s | recent=%d", user_id, len(recent)
                    )
                    return recent
            except Exception:
                logger.exception("DB query for recent purchases failed")

        logger.info("shopping DB | no results, using mock fallback")
        return [
            {
                "merchant": "Amazon.co.uk",
                "item": "Sony WH-1000XM4 Headphones",
                "amount": 249.99,
                "currency": "GBP",
                "date": "2026-03-10",
                "source": "mock_fallback",
            },
            {
                "merchant": "Amazon.co.uk",
                "item": "Anker Soundcore Life Q35",
                "amount": 79.99,
                "currency": "GBP",
                "date": "2026-04-01",
                "source": "mock_fallback",
            },
            {
                "merchant": "Amazon.co.uk",
                "item": "USB-C Hub",
                "amount": 34.99,
                "currency": "GBP",
                "date": "2026-04-18",
                "source": "mock_fallback",
            },
        ]

    def fetch_purchase_history(self, intent: dict[str, Any]) -> list[dict]:
        """Similar items from DB by name keywords and category."""
        user_id = intent.get("_user_id", "")
        items = intent.get("items", [])

        if user_id and items:
            all_similar: list[dict] = []
            seen_ids: set[str] = set()

            for item in items:
                item_name = item.get("name", "")
                category = item.get("category")
                if not item_name:
                    continue

                try:
                    for match in db.find_similar_items(
                        user_id, item_name, category, lookback_days=365
                    ):
                        mid = match.get("id", "")
                        if mid and mid not in seen_ids:
                            seen_ids.add(mid)
                            all_similar.append(match)
                except Exception:
                    logger.exception("find_similar_items failed item=%s", item_name)

                if category:
                    try:
                        for cp in db.get_purchases_by_category(
                            user_id, category, lookback_days=180
                        ):
                            cpid = cp.get("id", "")
                            if cpid and cpid not in seen_ids:
                                seen_ids.add(cpid)
                                all_similar.append(cp)
                    except Exception:
                        logger.exception(
                            "get_purchases_by_category failed cat=%s", category
                        )

            if all_similar:
                logger.info(
                    "shopping DB | user=%s | similar=%d", user_id, len(all_similar)
                )
                return all_similar

        logger.info("shopping DB | no similar items, using mock fallback")
        return [
            {
                "item_name": "Sony WH-1000XM4 Noise Cancelling Headphones",
                "category": "Electronics",
                "price": 249.99,
                "currency": "GBP",
                "purchased_at": "2026-03-10",
                "returned": False,
                "source": "mock_fallback",
            },
            {
                "item_name": "Anker Soundcore Life Q35 Headphones",
                "category": "Electronics",
                "price": 79.99,
                "currency": "GBP",
                "purchased_at": "2026-04-01",
                "returned": False,
                "source": "mock_fallback",
            },
            {
                "item_name": "Logitech MX Master 3S Mouse",
                "category": "Electronics",
                "price": 89.99,
                "currency": "GBP",
                "purchased_at": "2026-02-15",
                "returned": False,
                "source": "mock_fallback",
            },
        ]

    def _get_spending_context(self, user_id: str) -> float:
        if not user_id:
            return 0.0
        try:
            return db.get_spending_total(user_id, lookback_days=30)
        except Exception:
            logger.exception("get_spending_total failed user=%s", user_id)
            return 0.0

    # ── prompts ──────────────────────────────────────────────────────

    def build_audit_prompt(
        self,
        intent: dict[str, Any],
        calendar_events: list[dict],
        bank_transactions: list[dict],
        purchase_history: list[dict],
    ) -> str:
        user_id = intent.get("_user_id", "")
        spending_30d = self._get_spending_context(user_id)

        items = intent.get("items", [])
        item_names = [i.get("name", "Unknown") for i in items]
        categories = list(
            {i.get("category", "Unknown") for i in items if i.get("category")}
        )
        cart_total = self.extract_item_price(intent)

        return f"""You are an AI protecting a neurodivergent user from impulsive or duplicate online purchases.

**What the user is about to buy:**
Items: {item_names}
Categories: {categories}
Cart total: £{cart_total:.2f}
Full intent data: {intent}

**Their recent purchases (last 90 days):**
{bank_transactions}

**Similar or related items they already own:**
{purchase_history}

**Spending summary:**
Total spent in last 30 days: £{spending_30d:.2f}

Analyse the above data and look for ALL of the following risk patterns:

1. **Duplicate purchase** – They already own the same or a very similar
   item (e.g. same product line, overlapping features, same brand and
   category). Pay special attention to items that are clearly just a
   newer version of something they already have.

2. **Impulse buying** – Signs of impulsive behaviour:
   • Multiple purchases in the same category within a short window
     (e.g. 3+ electronics purchases in the same month)
   • Buying late at night (current hour context will be provided)
   • Rapidly adding items without apparent need

3. **Budget concern** – The cart total is unusually high relative to
   their recent 30-day spending of £{spending_30d:.2f}, or
   the item is a luxury purchase they may not have budgeted for.

4. **Unnecessary upgrade** – They already own a previous-generation
   version that still works (e.g. XM4 → XM5 headphones, iPhone 15 →
   iPhone 16). Flag this even if the older model is slightly different.

Return ONLY raw JSON: {{"risks": ["risk description 1", "risk description 2"]}}
If there are absolutely NO risks, return: {{"risks": []}}"""

    def build_drafting_prompt(
        self, risk_factors: list[str], intent: dict[str, Any]
    ) -> str:
        items = intent.get("items", [])
        item_name = items[0].get("name", "this item") if items else "this item"

        return f"""Write a 1-2 sentence empathetic, non-judgmental warning for a neurodivergent user
who is about to purchase "{item_name}" on Amazon.

The detected risks are:
{risk_factors}

Be short and direct – never shame or lecture. Acknowledge the appeal of the
purchase while gently flagging the concern. If the risk is about already owning
something similar, mention it specifically. If it's about impulse buying,
be understanding about how tempting online shopping can be.
Start with an appropriate emoji. Keep it concise enough to fit in a browser popup."""

    # ── economics ────────────────────────────────────────────────────

    def extract_item_price(self, intent: dict[str, Any]) -> float:
        cart_total = intent.get("cart_total", {})
        if cart_total:
            try:
                return float(cart_total.get("amount", 0))
            except (TypeError, ValueError):
                pass
        # Fallback: sum items
        total = 0.0
        for item in intent.get("items", []):
            try:
                total += float(item.get("price", 0)) * int(item.get("quantity", 1))
            except (TypeError, ValueError):
                continue
        return total

    def extract_hour_of_day(self, intent: dict[str, Any]) -> int:
        return datetime.datetime.now().hour

    # ── storage ──────────────────────────────────────────────────────

    def store(self, user_id: str, intent: dict[str, Any], domain: str) -> list[dict]:
        try:
            return db.store_purchase(user_id, intent, domain)
        except Exception:
            logger.exception("Failed to store purchase user=%s", user_id)
            return []


# ═════════════════════════════════════════════
# Fallback Handler
# ═════════════════════════════════════════════


class FallbackHandler(DomainHandler):
    """Generic handler for unrecognised domains — never crashes."""

    def context_requirements(self, intent: dict[str, Any]) -> dict[str, bool]:
        return {
            "requires_calendar": False,
            "requires_bank": True,
            "requires_purchase_history": True,
        }

    def fetch_calendar(self, intent: dict[str, Any]) -> list[dict]:
        return []

    def fetch_bank(self, intent: dict[str, Any]) -> list[dict]:
        return [
            {
                "merchant": "Generic Online Store",
                "item": "Recent purchase",
                "amount": 50.00,
                "currency": "GBP",
                "date": "2026-04-15",
            }
        ]

    def fetch_purchase_history(self, intent: dict[str, Any]) -> list[dict]:
        return []

    def build_audit_prompt(
        self,
        intent: dict[str, Any],
        calendar_events: list[dict],
        bank_transactions: list[dict],
        purchase_history: list[dict],
    ) -> str:
        return (
            "You are an AI assistant protecting a neurodivergent user from "
            "impulsive or mistaken online actions.\n\n"
            f"**Action the user wants to take:**\n{intent}\n\n"
            f"**Their recent transactions:**\n{bank_transactions}\n\n"
            f"**Their purchase history:**\n{purchase_history}\n\n"
            "Look for duplicate purchases, unusually high spending, or any "
            "clearly wasteful or conflicting action.\n\n"
            'Return ONLY raw JSON: {"risks": ["risk 1", "risk 2"]}\n'
            'If there are NO risks return: {"risks": []}'
        )

    def build_drafting_prompt(
        self, risk_factors: list[str], intent: dict[str, Any]
    ) -> str:
        return (
            "Write a single short, empathetic warning for a neurodivergent user "
            f"about these potential concerns:\n{risk_factors}\n\n"
            "Start with an appropriate emoji. Keep it under 2 sentences. Be warm, not patronising."
        )

    def extract_item_price(self, intent: dict[str, Any]) -> float:
        for key in ("amount", "price", "total"):
            if key in intent:
                try:
                    return float(intent[key])
                except (TypeError, ValueError):
                    continue
        for val in intent.values():
            if isinstance(val, dict):
                for key in ("amount", "price", "total"):
                    if key in val:
                        try:
                            return float(val[key])
                        except (TypeError, ValueError):
                            continue
        return 0.0

    def extract_hour_of_day(self, intent: dict[str, Any]) -> int:
        return datetime.datetime.now().hour

    def store(self, user_id: str, intent: dict[str, Any], domain: str) -> list[dict]:
        logger.info(
            "FallbackHandler.store — skipping domain-specific persistence for domain=%s",
            domain,
        )
        return []


# ═════════════════════════════════════════════
# Domain Registry
# ═════════════════════════════════════════════

_REGISTRY: dict[str, DomainHandler] = {}

_flight = FlightDomainHandler()
_shopping = ShoppingDomainHandler()

for _d in ("skyscanner.net", "skyscanner.com", "skyscanner.co.uk"):
    _REGISTRY[_d] = _flight

for _d in (
    "amazon.co.uk",
    "amazon.com",
    "amazon.de",
    "amazon.fr",
    "amazon.es",
    "amazon.it",
):
    _REGISTRY[_d] = _shopping


def _normalise(domain: str) -> str:
    d = domain.strip().lower()
    return d[4:] if d.startswith("www.") else d


def get_domain_handler(domain: str) -> DomainHandler:
    """Look up the handler for a domain (exact match, then suffix match, then fallback)."""
    clean = _normalise(domain)

    if clean in _REGISTRY:
        return _REGISTRY[clean]

    for key, handler in _REGISTRY.items():
        if clean.endswith(f".{key}"):
            return handler

    logger.warning("No handler for domain '%s' — using fallback", domain)
    return FallbackHandler()


def register_domain(domain_key: str, handler: DomainHandler) -> None:
    """Register a new domain handler at runtime."""
    _REGISTRY[_normalise(domain_key)] = handler
