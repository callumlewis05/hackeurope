"""Unified database layer — SQLModel engine, table models, and repository functions.

Connects directly to Supabase's PostgreSQL (or any Postgres) via SQLModel.
Set DATABASE_URL in your .env to your Supabase connection string:

    DATABASE_URL=postgresql://postgres.xxxx:password@aws-0-eu-west-2.pooler.supabase.com:6543/postgres
"""

from __future__ import annotations

import logging
import os
import uuid as _uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Generator, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import Column, ForeignKey, Index, Text, func, text  # noqa: F401
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Session, SQLModel, create_engine, or_, select

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Engine & Session
# ─────────────────────────────────────────────

_DATABASE_URL: str | None = os.getenv("DATABASE_URL")

if not _DATABASE_URL:
    logger.warning(
        "DATABASE_URL is not set — DB operations will fail. "
        "Add it to .env (Supabase → Settings → Database → Connection string)."
    )


def _clean_database_url(url: str) -> str:
    """Strip query params that psycopg2 doesn't understand (e.g. pgbouncer)."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    # Remove keys that aren't valid libpq connection options
    for bad_key in ("pgbouncer",):
        params.pop(bad_key, None)
    cleaned_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=cleaned_query))


_engine = create_engine(
    _clean_database_url(_DATABASE_URL) if _DATABASE_URL else "sqlite:///./fallback.db",
    echo=bool(os.getenv("SQL_ECHO", "")),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session that auto-commits on success."""
    with Session(_engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def purge_all_data() -> None:
    """Drop ALL tables managed by SQLModel and recreate them empty.

    ⚠️  This is destructive — every row in every table will be lost.
    """
    logger.warning("PURGING ALL DATA — dropping all tables…")
    SQLModel.metadata.drop_all(_engine)
    logger.info("All tables dropped. Recreating schema…")
    SQLModel.metadata.create_all(_engine)
    logger.info("Schema recreated. All tables are now empty.")


# ═════════════════════════════════════════════
# Table Models
# ═════════════════════════════════════════════


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"  # type: ignore[assignment]
    __table_args__ = (Index("ix_profiles_email", "email", unique=True),)

    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    email: str = Field(sa_column=Column(Text, nullable=False))

    name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EmailConnection(SQLModel, table=True):
    """Stores Google OAuth tokens so we can read Gmail on behalf of the user."""

    __tablename__ = "email_connections"  # type: ignore[assignment]
    __table_args__ = (Index("ix_ec_user", "user_id", unique=True),)

    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    user_id: _uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    provider: str = Field(default="google", sa_column=Column(Text, nullable=False))
    email_address: Optional[str] = Field(default=None, sa_column=Column(Text))
    access_token: str = Field(sa_column=Column(Text, nullable=False))
    refresh_token: Optional[str] = Field(default=None, sa_column=Column(Text))
    token_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserCalendar(SQLModel, table=True):
    __tablename__ = "user_calendars"  # type: ignore[assignment]
    __table_args__ = (Index("ix_uc_user", "user_id"),)

    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    user_id: _uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    name: str = Field(sa_column=Column(Text, nullable=False))
    ical_url: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FlightBooking(SQLModel, table=True):
    __tablename__ = "flight_bookings"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_fb_user", "user_id"),
        Index("ix_fb_user_date", "user_id", "departure_date"),
    )

    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    user_id: _uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    departure_date: date
    departure_time: Optional[time] = None
    departure_airport: Optional[str] = None
    arrival_time: Optional[time] = None
    arrival_airport: Optional[str] = None
    destination: Optional[str] = None
    price_amount: Optional[float] = None
    price_currency: str = "GBP"
    leg: Optional[str] = None  # 'outbound' | 'return'
    self_transfer: bool = False
    trip_id: Optional[_uuid.UUID] = None
    booked_at: datetime = Field(default_factory=datetime.utcnow)


class Purchase(SQLModel, table=True):
    __tablename__ = "purchases"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_pu_user", "user_id"),
        Index("ix_pu_user_cat", "user_id", "category"),
        Index("ix_pu_user_date", "user_id", "purchased_at"),
    )

    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    user_id: _uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    item_name: str = Field(sa_column=Column(Text, nullable=False))
    category: Optional[str] = None
    price: Optional[float] = None
    currency: str = "GBP"
    quantity: int = 1
    domain: Optional[str] = None
    product_url: Optional[str] = None
    returned: bool = False
    purchased_at: datetime = Field(default_factory=datetime.utcnow)


class Interaction(SQLModel, table=True):
    __tablename__ = "interactions"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_ia_user", "user_id"),
        Index("ix_ia_user_domain", "user_id", "domain"),
        Index("ix_ia_analyzed", "analyzed_at"),
    )

    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    user_id: _uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    domain: str = Field(sa_column=Column(Text, nullable=False))
    title: Optional[str] = None
    intent_type: Optional[str] = None
    intent_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    risk_factors: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    intervention_message: Optional[str] = None
    was_intervened: bool = False
    feedback: bool = True
    compute_cost: Optional[float] = None
    money_saved: Optional[float] = None
    platform_fee: Optional[float] = None
    hour_of_day: Optional[int] = None
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


# ═════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════


def _to_uuid(val: str | _uuid.UUID) -> _uuid.UUID:
    """Coerce a string or UUID into a uuid.UUID."""
    if isinstance(val, _uuid.UUID):
        return val
    return _uuid.UUID(val)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_date(val: str | None) -> date | None:
    """Parse a date string in ISO format or common human-readable formats.

    Handles: '2026-03-14', 'Sat, 14 Mar 2026', '14 Mar 2026', 'March 14, 2026', etc.
    """
    if not val:
        return None
    s = val.strip()

    # ISO format (2026-03-14)
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass

    # RFC 2822 style ("Sat, 14 Mar 2026") — parsedate_to_datetime needs a time,
    # so append one if missing
    try:
        return parsedate_to_datetime(s + " 00:00:00").date()
    except Exception:
        pass

    # Common formats
    for fmt in (
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Last resort: strip leading day name ("Sat, " / "Saturday, ") and retry
    if "," in s:
        after_comma = s.split(",", 1)[1].strip()
        return _parse_date(after_comma)

    logger.warning("_parse_date could not parse: %r", val)
    return None


def _parse_time(val: str | None) -> time | None:
    if not val:
        return None
    try:
        parts = val.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


# ═════════════════════════════════════════════
# Flight Repository
# ═════════════════════════════════════════════


def get_flights_near_dates(
    user_id: str | _uuid.UUID, dates: list[date], window_days: int = 3
) -> list[dict[str, Any]]:
    """Return bookings for user within ±window_days of any given date."""
    if not dates:
        return []

    uid = _to_uuid(user_id)
    earliest = min(dates) - timedelta(days=window_days)
    latest = max(dates) + timedelta(days=window_days)

    try:
        with get_session() as session:
            rows = session.exec(
                select(FlightBooking)
                .where(FlightBooking.user_id == uid)
                .where(FlightBooking.departure_date >= earliest)
                .where(FlightBooking.departure_date <= latest)
                .order_by(FlightBooking.departure_date.asc())  # type: ignore[union-attr]
            ).all()
            return [_flight_to_dict(r) for r in rows]
    except Exception:
        logger.exception("get_flights_near_dates failed user=%s", user_id)
        return []


def get_flights_to_destination(
    user_id: str | _uuid.UUID, destination: str, lookback_days: int = 180
) -> list[dict[str, Any]]:
    """Return recent bookings to the same destination (ILIKE match)."""
    if not destination:
        return []

    uid = _to_uuid(user_id)
    since = date.today() - timedelta(days=lookback_days)
    pattern = f"%{destination.strip()}%"

    try:
        with get_session() as session:
            rows = session.exec(
                select(FlightBooking)
                .where(FlightBooking.user_id == uid)
                .where(FlightBooking.departure_date >= since)
                .where(
                    or_(
                        FlightBooking.arrival_airport.ilike(pattern),  # type: ignore[union-attr]
                        FlightBooking.destination.ilike(pattern),  # type: ignore[union-attr]
                    )
                )
                .order_by(FlightBooking.departure_date.asc())  # type: ignore[union-attr]
            ).all()
            return [_flight_to_dict(r) for r in rows]
    except Exception:
        logger.exception("get_flights_to_destination failed user=%s", user_id)
        return []


def store_flight_booking(
    user_id: str | _uuid.UUID, intent: dict[str, Any]
) -> list[dict[str, Any]]:
    """Insert one row per leg (outbound + optional return) into flight_bookings."""
    uid = _to_uuid(user_id)
    price_info = intent.get("selected_price", {})
    price_amount = _safe_float(price_info.get("amount"))
    price_currency = price_info.get("currency", "GBP")
    trip_id = _uuid.uuid4()

    rows_out: list[dict[str, Any]] = []

    try:
        with get_session() as session:
            for leg_name in ("outbound", "return"):
                leg = intent.get(leg_name)
                if not leg:
                    continue

                dep_date_str = leg.get("departure_date")
                if not dep_date_str:
                    continue

                parsed_date = _parse_date(dep_date_str)
                if not parsed_date:
                    logger.warning(
                        "Skipping leg %s — unparseable date: %r", leg_name, dep_date_str
                    )
                    continue

                booking = FlightBooking(
                    user_id=uid,
                    airline=leg.get("airline"),
                    flight_number=leg.get("flight_number"),
                    departure_date=parsed_date,
                    departure_time=_parse_time(leg.get("departure_time")),
                    departure_airport=leg.get("departure_airport"),
                    arrival_time=_parse_time(leg.get("arrival_time")),
                    arrival_airport=leg.get("arrival_airport"),
                    destination=leg.get("arrival_airport"),
                    price_amount=price_amount,
                    price_currency=price_currency,
                    leg=leg_name,
                    self_transfer=bool(leg.get("self_transfer", False)),
                    trip_id=trip_id,
                )
                session.add(booking)
                rows_out.append(_flight_to_dict(booking))

        logger.info("Stored %d flight leg(s) for user=%s", len(rows_out), user_id)
        return rows_out
    except Exception:
        logger.exception("store_flight_booking failed user=%s", user_id)
        return []


def _flight_to_dict(fb: FlightBooking) -> dict[str, Any]:
    return {
        "id": str(fb.id),
        "user_id": str(fb.user_id),
        "airline": fb.airline,
        "flight_number": fb.flight_number,
        "departure_date": str(fb.departure_date) if fb.departure_date else None,
        "departure_time": str(fb.departure_time) if fb.departure_time else None,
        "departure_airport": fb.departure_airport,
        "arrival_time": str(fb.arrival_time) if fb.arrival_time else None,
        "arrival_airport": fb.arrival_airport,
        "destination": fb.destination,
        "price_amount": fb.price_amount,
        "price_currency": fb.price_currency,
        "leg": fb.leg,
        "self_transfer": fb.self_transfer,
        "trip_id": str(fb.trip_id) if fb.trip_id else None,
        "booked_at": str(fb.booked_at) if fb.booked_at else None,
    }


# ═════════════════════════════════════════════
# Purchase Repository
# ═════════════════════════════════════════════


def get_recent_purchases(
    user_id: str | _uuid.UUID, lookback_days: int = 90
) -> list[dict[str, Any]]:
    """Return all purchases within the lookback window."""
    uid = _to_uuid(user_id)
    since = datetime.utcnow() - timedelta(days=lookback_days)

    try:
        with get_session() as session:
            rows = session.exec(
                select(Purchase)
                .where(Purchase.user_id == uid)
                .where(Purchase.purchased_at >= since)
                .order_by(Purchase.purchased_at.desc())  # type: ignore[union-attr]
            ).all()
            return [_purchase_to_dict(r) for r in rows]
    except Exception:
        logger.exception("get_recent_purchases failed user=%s", user_id)
        return []


def find_similar_items(
    user_id: str | _uuid.UUID,
    item_name: str,
    category: str | None = None,
    lookback_days: int = 365,
) -> list[dict[str, Any]]:
    """Find past purchases similar by name keywords or category."""
    uid = _to_uuid(user_id)
    since = datetime.utcnow() - timedelta(days=lookback_days)
    keywords = [w for w in item_name.split() if len(w) > 2]

    if not keywords and not category:
        return []

    # Build OR conditions: any keyword ILIKE match, or same category
    conditions = []
    for kw in keywords[:5]:
        safe = kw.replace("%", "").replace("_", "")
        conditions.append(Purchase.item_name.ilike(f"%{safe}%"))  # type: ignore[union-attr]
    if category:
        conditions.append(Purchase.category == category)

    try:
        with get_session() as session:
            rows = session.exec(
                select(Purchase)
                .where(Purchase.user_id == uid)
                .where(Purchase.returned == False)  # noqa: E712
                .where(Purchase.purchased_at >= since)
                .where(or_(*conditions))
                .order_by(Purchase.purchased_at.desc())  # type: ignore[union-attr]
            ).all()
            return [_purchase_to_dict(r) for r in rows]
    except Exception:
        logger.exception("find_similar_items failed user=%s", user_id)
        return []


def get_purchases_by_category(
    user_id: str | _uuid.UUID, category: str, lookback_days: int = 180
) -> list[dict[str, Any]]:
    """Return non-returned purchases in a category (impulse detection)."""
    uid = _to_uuid(user_id)
    since = datetime.utcnow() - timedelta(days=lookback_days)

    try:
        with get_session() as session:
            rows = session.exec(
                select(Purchase)
                .where(Purchase.user_id == uid)
                .where(Purchase.category == category)
                .where(Purchase.returned == False)  # noqa: E712
                .where(Purchase.purchased_at >= since)
                .order_by(Purchase.purchased_at.desc())  # type: ignore[union-attr]
            ).all()
            return [_purchase_to_dict(r) for r in rows]
    except Exception:
        logger.exception("get_purchases_by_category failed user=%s", user_id)
        return []


def get_spending_total(user_id: str | _uuid.UUID, lookback_days: int = 30) -> float:
    """Sum price*quantity for non-returned purchases in the window."""
    uid = _to_uuid(user_id)
    since = datetime.utcnow() - timedelta(days=lookback_days)

    try:
        with get_session() as session:
            rows = session.exec(
                select(Purchase)
                .where(Purchase.user_id == uid)
                .where(Purchase.returned == False)  # noqa: E712
                .where(Purchase.purchased_at >= since)
            ).all()
            return sum((r.price or 0) * (r.quantity or 1) for r in rows)
    except Exception:
        logger.exception("get_spending_total failed user=%s", user_id)
        return 0.0


def store_purchase(
    user_id: str | _uuid.UUID, intent: dict[str, Any], domain: str
) -> list[dict[str, Any]]:
    """Insert one row per item in the cart into purchases."""
    uid = _to_uuid(user_id)
    items = intent.get("items", [])
    if not items:
        return []

    rows_out: list[dict[str, Any]] = []

    try:
        with get_session() as session:
            for item in items:
                purchase = Purchase(
                    user_id=uid,
                    item_name=item.get("name", "Unknown item"),
                    category=item.get("category"),
                    price=_safe_float(item.get("price")),
                    currency=item.get("currency", "GBP"),
                    quantity=int(item.get("quantity", 1)),
                    domain=domain,
                    product_url=item.get("url"),
                    returned=False,
                )
                session.add(purchase)
                rows_out.append(_purchase_to_dict(purchase))

        logger.info("Stored %d purchase(s) for user=%s", len(rows_out), user_id)
        return rows_out
    except Exception:
        logger.exception("store_purchase failed user=%s", user_id)
        return []


def _purchase_to_dict(p: Purchase) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "user_id": str(p.user_id),
        "item_name": p.item_name,
        "category": p.category,
        "price": p.price,
        "currency": p.currency,
        "quantity": p.quantity,
        "domain": p.domain,
        "product_url": p.product_url,
        "returned": p.returned,
        "purchased_at": str(p.purchased_at) if p.purchased_at else None,
    }


# ═════════════════════════════════════════════
# Interaction Repository
# ═════════════════════════════════════════════


def store_interaction(
    user_id: str | _uuid.UUID,
    domain: str,
    intent: dict[str, Any],
    risk_factors: list[str],
    intervention_message: str | None,
    economics: dict[str, Any],
    title: str | None = None,
    feedback: bool = True,
) -> dict[str, Any] | None:
    """Log one analysis run into the interactions table."""
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            row = Interaction(
                user_id=uid,
                domain=domain,
                title=title,
                intent_type=intent.get("type"),
                intent_data=intent,
                risk_factors=risk_factors,
                intervention_message=intervention_message,
                was_intervened=bool(intervention_message),
                feedback=feedback,
                compute_cost=economics.get("compute_cost"),
                money_saved=economics.get("money_saved"),
                platform_fee=economics.get("platform_fee"),
                hour_of_day=economics.get("hour_of_day"),
            )
            session.add(row)
            session.flush()
            row_id = str(row.id)

        logger.info(
            "Stored interaction user=%s domain=%s intervened=%s",
            user_id,
            domain,
            bool(intervention_message),
        )
        return {"id": row_id}
    except Exception:
        logger.exception("store_interaction failed user=%s", user_id)
        return None


def _interaction_to_dict(row: Interaction) -> dict[str, Any]:
    """Convert an Interaction row to a plain dict for API responses."""
    return {
        "id": str(row.id),
        "domain": row.domain,
        "title": row.title,
        "intent_type": row.intent_type,
        "intent_data": row.intent_data or {},
        "risk_factors": row.risk_factors or [],
        "intervention_message": row.intervention_message,
        "was_intervened": row.was_intervened,
        "feedback": row.feedback,
        "compute_cost": row.compute_cost,
        "money_saved": row.money_saved,
        "platform_fee": row.platform_fee,
        "hour_of_day": row.hour_of_day,
        "analyzed_at": str(row.analyzed_at) if row.analyzed_at else None,
    }


def list_interactions(
    user_id: _uuid.UUID,
    *,
    domain: str | None = None,
    intervened_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated interactions for a user with optional filters.

    Returns (items, total_count).
    """
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            base = select(Interaction).where(Interaction.user_id == uid)

            if domain:
                base = base.where(Interaction.domain == domain)
            if intervened_only:
                base = base.where(Interaction.was_intervened == True)  # noqa: E712

            # Total count (before pagination)
            count_stmt = select(func.count()).select_from(base.subquery())
            total: int = session.exec(count_stmt).one()

            # Paginated results
            rows = session.exec(
                base.order_by(Interaction.analyzed_at.desc())  # type: ignore[union-attr]
                .offset(offset)
                .limit(limit)
            ).all()

            return [_interaction_to_dict(r) for r in rows], total
    except Exception:
        logger.exception("list_interactions failed user=%s", user_id)
        return [], 0


def get_interaction(
    user_id: _uuid.UUID, interaction_id: _uuid.UUID
) -> dict[str, Any] | None:
    """Return a single interaction by ID, scoped to the user."""
    try:
        with get_session() as session:
            row = session.get(Interaction, interaction_id)
            if not row or row.user_id != _to_uuid(user_id):
                return None
            return _interaction_to_dict(row)
    except Exception:
        logger.exception(
            "get_interaction failed user=%s id=%s", user_id, interaction_id
        )
        return None


def update_interaction_feedback(
    user_id: str | _uuid.UUID, interaction_id: str | _uuid.UUID, feedback: bool
) -> bool:
    """Update the feedback boolean for a single interaction, scoped to the user.

    Returns True on success, False if the interaction was not found or an error occurred.
    """
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            # Ensure we use a UUID instance for lookup
            iid = _to_uuid(interaction_id)
            row = session.get(Interaction, iid)
            if not row or row.user_id != uid:
                logger.info(
                    "update_interaction_feedback: no such interaction or wrong user user=%s id=%s",
                    user_id,
                    interaction_id,
                )
                return False

            # Update the feedback flag and persist
            row.feedback = bool(feedback)
            session.add(row)
            session.flush()

            logger.info(
                "Updated interaction feedback user=%s interaction=%s feedback=%s",
                user_id,
                interaction_id,
                row.feedback,
            )
            return True
    except Exception:
        logger.exception(
            "update_interaction_feedback failed user=%s id=%s", user_id, interaction_id
        )
        return False


def get_interaction_stats(user_id: _uuid.UUID) -> dict[str, Any]:
    """Aggregate statistics across all interactions for a user."""
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            rows = session.exec(
                select(Interaction).where(Interaction.user_id == uid)
            ).all()

            total_analyses = len(rows)
            total_interventions = sum(1 for r in rows if r.was_intervened)
            total_money_saved = sum(r.money_saved or 0.0 for r in rows)
            total_compute_cost = sum(r.compute_cost or 0.0 for r in rows)
            total_platform_fees = sum(r.platform_fee or 0.0 for r in rows)

            # Per-domain breakdown
            domain_map: dict[str, dict[str, Any]] = {}
            for r in rows:
                d = domain_map.setdefault(
                    r.domain,
                    {
                        "domain": r.domain,
                        "total": 0,
                        "intervened": 0,
                        "money_saved": 0.0,
                    },
                )
                d["total"] += 1
                if r.was_intervened:
                    d["intervened"] += 1
                d["money_saved"] += r.money_saved or 0.0

            return {
                "total_analyses": total_analyses,
                "total_interventions": total_interventions,
                "total_money_saved": round(total_money_saved, 2),
                "total_compute_cost": round(total_compute_cost, 6),
                "total_platform_fees": round(total_platform_fees, 2),
                "by_domain": sorted(
                    domain_map.values(), key=lambda x: x["total"], reverse=True
                ),
            }
    except Exception:
        logger.exception("get_interaction_stats failed user=%s", user_id)
        return {
            "total_analyses": 0,
            "total_interventions": 0,
            "total_money_saved": 0.0,
            "total_compute_cost": 0.0,
            "total_platform_fees": 0.0,
            "by_domain": [],
        }


# ═════════════════════════════════════════════
# Profile Repository
# ═════════════════════════════════════════════


def upsert_user(
    user_id: _uuid.UUID,
    email: str,
    name: str | None = None,
    avatar_url: str | None = None,
) -> dict[str, Any]:
    """Create or update a profile so ``profiles.id == auth.users.id``.

    Handles three cases:
    1. **Profile exists with matching id** → update name/avatar.
    2. **No profile with this id, but one exists with the same email**
       (UUID mismatch from earlier bugs) → re-ID the existing row to
       use the canonical auth UUID, updating FKs in child tables inside
       the same transaction.
    3. **No profile at all** → insert a new row keyed by the auth UUID.

    Raises on DB errors so callers can decide how to handle failures
    (instead of silently swallowing them).
    """
    with get_session() as session:
        # ── Case 1: profile already keyed by the auth UUID ───────
        profile = session.get(Profile, user_id)
        if profile:
            if name is not None:
                profile.name = name
            if avatar_url is not None:
                profile.avatar_url = avatar_url
            # Keep email in sync with auth (it may have changed)
            if email:
                profile.email = email
            session.add(profile)
            session.flush()
            return _profile_to_dict(profile)

        # ── Case 2: email collision — profile exists under a stale UUID
        stmt = select(Profile).where(Profile.email == email)
        existing = session.exec(stmt).first()

        if existing:
            old_id = existing.id
            logger.warning(
                "upsert_user: re-IDing profile %s → %s (email=%s)",
                old_id,
                user_id,
                email,
            )
            # Migrate child-table FKs from old_id → user_id.
            # Done via raw UPDATE so we don't have to load every row.
            _child_tables = [
                "email_connections",
                "user_calendars",
                "flight_bookings",
                "purchases",
                "interactions",
            ]
            for tbl in _child_tables:
                session.execute(
                    text(
                        f"UPDATE {tbl} SET user_id = :new WHERE user_id = :old"
                    ).bindparams(new=user_id, old=old_id)
                )

            # Now update the profile row itself
            session.execute(
                text(
                    "UPDATE profiles SET id = :new_id, email = :email, "
                    "name = COALESCE(:name, name), "
                    "avatar_url = COALESCE(:avatar, avatar_url) "
                    "WHERE id = :old_id"
                ).bindparams(
                    new_id=user_id,
                    email=email,
                    name=name,
                    avatar=avatar_url,
                    old_id=old_id,
                )
            )
            session.flush()

            # Re-fetch to return consistent data
            profile = session.get(Profile, user_id)
            if profile:
                return _profile_to_dict(profile)
            # Shouldn't happen, but guard against it
            logger.error("upsert_user: profile disappeared after re-ID %s", user_id)

        # ── Case 3: brand-new user ──────────────────────────────
        profile = Profile(id=user_id, email=email, name=name, avatar_url=avatar_url)
        session.add(profile)
        session.flush()
        return _profile_to_dict(profile)


def get_user(user_id: _uuid.UUID) -> dict[str, Any] | None:
    """Fetch a profile by its primary key. Returns None when not found."""
    with get_session() as session:
        profile = session.get(Profile, user_id)
        if not profile:
            return None
        return _profile_to_dict(profile)


def _profile_to_dict(p: Profile) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "email": p.email,
        "name": p.name,
        "avatar_url": p.avatar_url,
        "created_at": str(p.created_at) if p.created_at else None,
    }


# ═════════════════════════════════════════════
# UserCalendar Repository
# ═════════════════════════════════════════════


def list_calendars(user_id: _uuid.UUID) -> list[dict[str, Any]]:
    try:
        with get_session() as session:
            rows = session.exec(
                select(UserCalendar)
                .where(UserCalendar.user_id == user_id)
                .order_by(UserCalendar.created_at.asc())  # type: ignore[union-attr]
            ).all()
            return [_calendar_to_dict(r) for r in rows]
    except Exception:
        logger.exception("list_calendars failed user=%s", user_id)
        return []


def add_calendar(
    user_id: _uuid.UUID, name: str, ical_url: str
) -> dict[str, Any] | None:
    try:
        with get_session() as session:
            cal = UserCalendar(user_id=user_id, name=name, ical_url=ical_url)
            session.add(cal)
            session.flush()
            return _calendar_to_dict(cal)
    except Exception:
        logger.exception("add_calendar failed user=%s", user_id)
        return None


def delete_calendar(user_id: _uuid.UUID, calendar_id: _uuid.UUID) -> bool:
    try:
        with get_session() as session:
            cal = session.get(UserCalendar, calendar_id)
            if not cal or cal.user_id != user_id:
                return False
            session.delete(cal)
            return True
    except Exception:
        logger.exception("delete_calendar failed user=%s cal=%s", user_id, calendar_id)
        return False


def get_calendar_urls(user_id: _uuid.UUID) -> list[str]:
    """Return just the iCal URLs for a user (used by the calendar fetcher)."""
    try:
        with get_session() as session:
            rows = session.exec(
                select(UserCalendar.ical_url).where(UserCalendar.user_id == user_id)
            ).all()
            return list(rows)
    except Exception:
        logger.exception("get_calendar_urls failed user=%s", user_id)
        return []


def _calendar_to_dict(c: UserCalendar) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "user_id": str(c.user_id),
        "name": c.name,
        "ical_url": c.ical_url,
        "created_at": str(c.created_at) if c.created_at else None,
    }


# ═════════════════════════════════════════════
# Email Connection Repository
# ═════════════════════════════════════════════


def upsert_email_connection(
    user_id: _uuid.UUID,
    access_token: str,
    refresh_token: str | None = None,
    email_address: str | None = None,
    provider: str = "google",
    token_expires_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Create or update the Gmail/email connection for a user.

    Only one connection per user is supported (unique on user_id).
    """
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            stmt = select(EmailConnection).where(EmailConnection.user_id == uid)
            existing = session.exec(stmt).first()

            if existing:
                existing.access_token = access_token
                if refresh_token is not None:
                    existing.refresh_token = refresh_token
                if email_address is not None:
                    existing.email_address = email_address
                if token_expires_at is not None:
                    existing.token_expires_at = token_expires_at
                existing.updated_at = datetime.utcnow()
                session.add(existing)
                session.flush()
                return _email_connection_to_dict(existing)
            else:
                conn = EmailConnection(
                    user_id=uid,
                    provider=provider,
                    email_address=email_address,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expires_at=token_expires_at,
                )
                session.add(conn)
                session.flush()
                return _email_connection_to_dict(conn)
    except Exception:
        logger.exception("upsert_email_connection failed user=%s", user_id)
        return None


def get_email_connection(user_id: _uuid.UUID) -> dict[str, Any] | None:
    """Return the email connection for a user, or None."""
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            stmt = select(EmailConnection).where(EmailConnection.user_id == uid)
            row = session.exec(stmt).first()
            if not row:
                return None
            return _email_connection_to_dict(row)
    except Exception:
        logger.exception("get_email_connection failed user=%s", user_id)
        return None


def get_email_connection_raw(user_id: _uuid.UUID) -> dict[str, Any] | None:
    """Return the email connection INCLUDING tokens (for internal use only)."""
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            stmt = select(EmailConnection).where(EmailConnection.user_id == uid)
            row = session.exec(stmt).first()
            if not row:
                return None
            return {
                "id": str(row.id),
                "user_id": str(row.user_id),
                "provider": row.provider,
                "email_address": row.email_address,
                "access_token": row.access_token,
                "refresh_token": row.refresh_token,
                "token_expires_at": row.token_expires_at,
            }
    except Exception:
        logger.exception("get_email_connection_raw failed user=%s", user_id)
        return None


def delete_email_connection(user_id: _uuid.UUID) -> bool:
    """Remove the email connection for a user. Returns True if deleted."""
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            stmt = select(EmailConnection).where(EmailConnection.user_id == uid)
            row = session.exec(stmt).first()
            if not row:
                return False
            session.delete(row)
            return True
    except Exception:
        logger.exception("delete_email_connection failed user=%s", user_id)
        return False


def update_email_token(
    user_id: _uuid.UUID,
    access_token: str,
    token_expires_at: datetime | None = None,
) -> bool:
    """Update just the access token (after a refresh). Returns True on success."""
    uid = _to_uuid(user_id)
    try:
        with get_session() as session:
            stmt = select(EmailConnection).where(EmailConnection.user_id == uid)
            row = session.exec(stmt).first()
            if not row:
                return False
            row.access_token = access_token
            if token_expires_at is not None:
                row.token_expires_at = token_expires_at
            row.updated_at = datetime.utcnow()
            session.add(row)
            return True
    except Exception:
        logger.exception("update_email_token failed user=%s", user_id)
        return False


def _email_connection_to_dict(c: EmailConnection) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "user_id": str(c.user_id),
        "provider": c.provider,
        "email_address": c.email_address,
        "has_refresh_token": c.refresh_token is not None,
        "token_expires_at": str(c.token_expires_at) if c.token_expires_at else None,
        "created_at": str(c.created_at) if c.created_at else None,
        "updated_at": str(c.updated_at) if c.updated_at else None,
    }
