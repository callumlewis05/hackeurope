"""Request/response schemas and LangGraph agent state."""

import operator
from typing import Annotated, Any, NotRequired, Optional, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────
# API Request
# ─────────────────────────────────────────────


class IntentRequest(BaseModel):
    """Incoming payload from the Chrome Extension.

    user_id is no longer sent by the client — it comes from the
    authenticated JWT instead.
    """

    domain: str = Field(
        ...,
        description="Website domain (e.g. 'skyscanner.net', 'amazon.co.uk')",
    )
    intent: dict[str, Any] = Field(
        ...,
        description="Flexible intent payload – structure varies by domain",
    )


# ─────────────────────────────────────────────
# API Response
# ─────────────────────────────────────────────


class EconomicsDetail(BaseModel):
    compute_cost: Optional[float] = None
    money_saved: Optional[float] = None
    platform_fee: Optional[float] = None


class AgentResponse(BaseModel):
    id: UUID
    is_safe: bool
    intervention_message: Optional[str] = None
    risk_factors: list[str] = Field(default_factory=list)
    domain: str
    economics: EconomicsDetail


# ─────────────────────────────────────────────
# Calendar CRUD
# ─────────────────────────────────────────────


class CalendarCreate(BaseModel):
    """Request body for adding a new iCal calendar."""

    name: str = Field(..., description="Display name (e.g. 'Work', 'Personal')")
    ical_url: str = Field(..., description="iCal feed URL (.ics)")


class CalendarOut(BaseModel):
    """Response body for a single calendar entry."""

    id: str
    user_id: str
    name: str
    ical_url: str
    created_at: Optional[str] = None


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Email + password login."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class SignupRequest(BaseModel):
    """Email + password signup (optionally with name)."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password (min 6 chars)")
    name: Optional[str] = Field(None, description="Display name")


class RefreshRequest(BaseModel):
    """Refresh an expired access token."""

    refresh_token: str = Field(..., description="Refresh token from login/signup")


class AuthResponse(BaseModel):
    """Tokens returned after successful login/signup/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Optional[dict] = None


# ─────────────────────────────────────────────
# User
# ─────────────────────────────────────────────


class ProfileOut(BaseModel):
    """Public-facing user profile returned by /api/me."""

    id: str
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None


# ─────────────────────────────────────────────
# Interventions
# ─────────────────────────────────────────────


class InterventionOut(BaseModel):
    """A single intervention / interaction record."""

    id: str
    domain: str
    title: Optional[str] = None
    intent_type: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    mistake_types: list[str] = Field(default_factory=list)
    intent_data: dict[str, Any] = Field(default_factory=dict)
    risk_factors: list[str] = Field(default_factory=list)
    intervention_message: Optional[str] = None
    was_intervened: bool = False
    feedback: bool = True
    compute_cost: Optional[float] = None
    money_saved: Optional[float] = None
    platform_fee: Optional[float] = None
    hour_of_day: Optional[int] = None
    analyzed_at: Optional[str] = None


class DomainBreakdown(BaseModel):
    """Per-domain aggregation inside stats."""

    domain: str
    total: int = 0
    intervened: int = 0
    money_saved: float = 0.0


class InterventionStats(BaseModel):
    """Aggregate statistics across all interventions for a user."""

    total_analyses: int = 0
    total_interventions: int = 0
    total_money_saved: float = 0.0
    total_compute_cost: float = 0.0
    total_platform_fees: float = 0.0
    by_domain: list[DomainBreakdown] = Field(default_factory=list)


class InterventionListResponse(BaseModel):
    """Paginated list of interventions."""

    items: list[InterventionOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ─────────────────────────────────────────────
# Email Connection
# ─────────────────────────────────────────────


class EmailConnectRequest(BaseModel):
    """Request body to connect a Gmail account via OAuth provider token."""

    provider_token: str = Field(..., description="Google OAuth access token")
    provider_refresh_token: Optional[str] = Field(
        None,
        description="Google OAuth refresh token (recommended for long-lived access)",
    )


class EmailStatusOut(BaseModel):
    """Status of the user's email connection."""

    connected: bool = False
    provider: Optional[str] = None
    email_address: Optional[str] = None
    has_refresh_token: bool = False
    connected_at: Optional[str] = None


class EmailReceiptsOut(BaseModel):
    """Parsed receipts or flight bookings extracted from Gmail."""

    items: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    source: str = "gmail"


# ─────────────────────────────────────────────
# LangGraph State
# ─────────────────────────────────────────────


class AgentState(TypedDict):
    """State dict flowing through every node in the LangGraph pipeline."""

    # Request context
    user_id: str
    domain: str
    intent: dict[str, Any]

    # Feature flags (set by context_router)
    requires_calendar: bool
    requires_bank: bool
    requires_purchase_history: bool

    # Fetched context (operator.add lets parallel nodes append)
    calendar_events: Annotated[list[dict], operator.add]
    bank_transactions: Annotated[list[dict], operator.add]
    purchase_history: Annotated[list[dict], operator.add]

    # Audit results
    risk_factors: list[str]
    categories: list[str]
    mistake_types: list[str]
    intervention_message: Optional[str]

    # Economics
    compute_cost: float
    money_saved: float
    platform_fee: float
    hour_of_day: int

    # Best-effort LLM usage metadata produced by drafting_node (optional).
    # This is used by economics/storage to compute costs and persist usage for auditing.
    llm_usage: NotRequired[Optional[dict[str, Any]]]

    # Canonical DB-generated interaction id (UUID string) set by storage_node.
    # Present when the interaction has been persisted so callers can reference it.
    interaction_id: NotRequired[Optional[str]]

    # Set by storage node
    stored: bool
