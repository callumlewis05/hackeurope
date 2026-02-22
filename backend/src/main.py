"""HackEurope Agent — FastAPI application.

Single entry point: creates the app, mounts CORS, defines all endpoints.
Auth is handled via Supabase JWT verification.

Endpoints:
  GET  /health                       — liveness probe (no auth)
  POST /api/auth/signup              — create account via Supabase Auth
  POST /api/auth/login               — email+password login via Supabase Auth
  POST /api/auth/refresh             — refresh an expired access token
  GET  /api/me                       — authenticated user profile
  GET  /api/calendars                — list user's iCal calendars
  POST /api/calendars                — add a calendar
  DELETE /api/calendars/{id}         — remove a calendar
  GET  /api/interventions            — list intervention history (paginated)
  GET  /api/interventions/stats      — aggregate intervention statistics
  GET  /api/interventions/{id}       — single intervention by ID
  POST /api/analyze                  — run the agent pipeline
  POST /api/email/connect            — connect Gmail via Google OAuth token
  GET  /api/email/status             — check email connection status
  DELETE /api/email/disconnect       — disconnect Gmail
  GET  /api/email/receipts           — fetch purchase receipts from Gmail
  GET  /api/email/flights            — fetch flight bookings from Gmail
"""

import logging
import os
import uuid as _uuid
from typing import Annotated, Any, cast

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.runnables import RunnableConfig

from src import db, gmail
from src.config import (
    CORS_ORIGINS,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)
from src.graph import build_agent
from src.schemas import (
    AgentResponse,
    AgentState,
    AuthResponse,
    CalendarCreate,
    CalendarOut,
    EconomicsDetail,
    EmailConnectRequest,
    EmailReceiptsOut,
    EmailStatusOut,
    IntentRequest,
    InterventionListResponse,
    InterventionOut,
    InterventionStats,
    LoginRequest,
    ProfileOut,
    RefreshRequest,
    SignupRequest,
)
from src.supabase_client import sync_all_profiles, sync_profile_from_auth

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
app = FastAPI(
    title="HackEurope Agent",
    description="AI guardian agent that protects neurodivergent users from impulsive online actions.",
    version="0.5.0",
)

# When origins is ["*"], disable credentials (Starlette silently drops the
# Access-Control-Allow-Origin header for credentialed requests with "*").
# For explicit origin lists, credentials are safe to enable.
_allow_all = CORS_ORIGINS == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Build the agent graph once (in-memory checkpointer shared across requests)
_agent = build_agent()

# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

_SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
_bearer_scheme = HTTPBearer()

# Cache for the JWKS fetched from Supabase
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient | None:
    """Lazily create and cache a PyJWKClient pointing at Supabase's JWKS endpoint."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    if SUPABASE_URL:
        _jwks_client = jwt.PyJWKClient(
            f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
        return _jwks_client
    return None


def _supabase_auth_headers(*, use_service_role: bool = False) -> dict[str, str]:
    """Standard headers for Supabase Auth REST API calls.

    When *use_service_role* is True the service-role key is sent instead
    of the anon key.  This lets the server bypass email-confirmation on
    signup and perform other admin operations.
    """
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _ensure_supabase_configured() -> None:
    """Raise 500 if Supabase Auth env vars are missing."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL and SUPABASE_ANON_KEY must be configured on the server.",
        )
    if not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning(
            "SUPABASE_SERVICE_ROLE_KEY is not set — signup will require email confirmation."
        )


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a Supabase JWT.

    Supports two verification strategies:
    1. **ES256 (preferred)** — fetches the public key from Supabase's
       JWKS endpoint and verifies the signature.  Used by newer
       Supabase projects that issue ES256 tokens.
    2. **HS256 (fallback)** — uses the symmetric SUPABASE_JWT_SECRET.
       Kept for backward-compat with older Supabase projects.

    Raises HTTPException on any failure.
    """
    # Peek at the token header to decide which path to take
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    alg = header.get("alg", "")

    try:
        # ── ES256 path (JWKS) ──────────────────────────────────
        if alg == "ES256":
            jwks = _get_jwks_client()
            if jwks is None:
                raise HTTPException(
                    status_code=500,
                    detail="SUPABASE_URL is not configured — cannot verify ES256 tokens.",
                )
            signing_key = jwks.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
            )
            return payload

        # ── HS256 path (symmetric secret) ──────────────────────
        if not _SUPABASE_JWT_SECRET:
            raise HTTPException(
                status_code=500,
                detail="SUPABASE_JWT_SECRET is not configured on the server.",
            )
        payload = jwt.decode(
            token,
            _SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> dict[str, Any]:
    """FastAPI dependency that extracts the user from the Authorization header.

    Sync strategy (in priority order):
    1. **Supabase SDK** — ``sync_profile_from_auth`` fetches the canonical
       user record from ``auth.users`` via the admin API and upserts it
       into ``profiles``.  This guarantees ``profiles.id == auth.users.id``.
    2. **JWT fallback** — if the SDK is unavailable (missing env vars,
       network blip, etc.) we fall back to ``db.upsert_user`` with the
       claims embedded in the JWT.  Less authoritative but still keeps
       the profile table populated.
    3. **Bare JWT** — if both DB writes fail the request still succeeds
       (auth is valid) and we return the JWT data directly.
    """
    payload = _decode_token(credentials.credentials)

    user_id_str: str = payload.get("sub", "")
    email: str = payload.get("email", "")
    user_meta: dict = payload.get("user_metadata", {})

    if not user_id_str:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim.")

    try:
        user_id = _uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user id in token.")

    name = user_meta.get("full_name") or user_meta.get("name")
    avatar_url = user_meta.get("avatar_url")

    # ── 1. Primary path: sync from Supabase Auth via SDK ─────────
    profile: dict[str, Any] | None = None
    try:
        profile = sync_profile_from_auth(user_id)
    except Exception:
        logger.exception(
            "sync_profile_from_auth failed for user=%s — trying JWT fallback",
            user_id,
        )

    # ── 2. Fallback: upsert from JWT claims ──────────────────────
    if not profile or not profile.get("created_at"):
        try:
            profile = db.upsert_user(
                user_id=user_id,
                email=email,
                name=name,
                avatar_url=avatar_url,
            )
        except Exception:
            logger.exception(
                "JWT-fallback upsert_user also failed for user=%s", user_id
            )
            profile = None

    # ── 3. Return profile or bare JWT data ───────────────────────
    if profile and profile.get("created_at"):
        return {
            "id": user_id,
            "email": profile.get("email", email),
            "name": profile.get("name", name),
            "avatar_url": profile.get("avatar_url", avatar_url),
            "created_at": profile.get("created_at"),
        }

    logger.warning(
        "Profile sync failed for user=%s email=%s — returning bare JWT data",
        user_id,
        email,
    )
    return {
        "id": user_id,
        "email": email,
        "name": name,
        "avatar_url": avatar_url,
        "created_at": None,
    }


# Type alias for cleaner endpoint signatures
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


# ─────────────────────────────────────────────
# Routes — Public
# ─────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "HackEurope LangGraph Engine Online"}


# ─────────────────────────────────────────────
# Routes — Auth (Supabase proxy)
# ─────────────────────────────────────────────


@app.post("/api/auth/signup", response_model=AuthResponse)
async def signup(body: SignupRequest):
    """Create a new account via Supabase Auth and return tokens.

    Uses the admin API (service-role key) to create the user with
    email already confirmed, then immediately logs them in so the
    response contains usable access + refresh tokens.

    Profile sync uses ``sync_profile_from_auth`` so the local row is
    guaranteed to carry the correct auth UUID.
    """
    _ensure_supabase_configured()

    # ── 1. Create the user via the Admin API (auto-confirmed) ────
    admin_body: dict[str, Any] = {
        "email": body.email,
        "password": body.password,
        "email_confirm": True,
    }
    if body.name:
        admin_body["user_metadata"] = {"full_name": body.name}

    async with httpx.AsyncClient() as client:
        create_resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=_supabase_auth_headers(use_service_role=True),
            json=admin_body,
        )

    create_data = create_resp.json()

    if create_resp.status_code >= 400:
        detail = (
            create_data.get("error_description")
            or create_data.get("msg")
            or create_data.get("message")
            or str(create_data)
        )
        raise HTTPException(status_code=create_resp.status_code, detail=detail)

    user_data = create_data.get("user") or create_data

    # ── 2. Log the new user in to obtain tokens ──────────────────
    async with httpx.AsyncClient() as client:
        login_resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers=_supabase_auth_headers(),
            json={
                "email": body.email,
                "password": body.password,
            },
        )

    login_data = login_resp.json()

    if login_resp.status_code >= 400:
        # User was created but login failed — unusual but possible
        detail = (
            login_data.get("error_description")
            or login_data.get("msg")
            or login_data.get("message")
            or str(login_data)
        )
        raise HTTPException(status_code=login_resp.status_code, detail=detail)

    # Prefer user object from login (has latest metadata)
    user_data = login_data.get("user") or user_data

    # ── 3. Sync into local profiles table via Supabase SDK ───────
    user_id_str = user_data.get("id") or ""
    if user_id_str:
        try:
            uid = _uuid.UUID(user_id_str)
            profile = sync_profile_from_auth(uid)
            if not profile:
                # SDK unavailable — fall back to direct upsert
                user_meta = user_data.get("user_metadata", {})
                db.upsert_user(
                    user_id=uid,
                    email=user_data.get("email", body.email),
                    name=user_meta.get("full_name") or body.name,
                    avatar_url=user_meta.get("avatar_url"),
                )
        except Exception:
            logger.exception("Failed to sync signup user to profiles")

    return AuthResponse(
        access_token=login_data.get("access_token", ""),
        refresh_token=login_data.get("refresh_token", ""),
        expires_in=login_data.get("expires_in", 0),
        user=user_data,
    )


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    """Authenticate with email + password via Supabase Auth and return tokens."""
    _ensure_supabase_configured()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers=_supabase_auth_headers(),
            json={
                "email": body.email,
                "password": body.password,
            },
        )

    data = resp.json()

    if resp.status_code >= 400:
        detail = (
            data.get("error_description")
            or data.get("msg")
            or data.get("message")
            or str(data)
        )
        raise HTTPException(status_code=resp.status_code, detail=detail)

    user_data = data.get("user")

    # Sync into local profiles table via Supabase SDK
    if user_data:
        try:
            uid = _uuid.UUID(user_data["id"])
            profile = sync_profile_from_auth(uid)
            if not profile:
                # SDK unavailable — fall back to direct upsert
                user_meta = user_data.get("user_metadata", {})
                db.upsert_user(
                    user_id=uid,
                    email=user_data.get("email", body.email),
                    name=user_meta.get("full_name") or user_meta.get("name"),
                    avatar_url=user_meta.get("avatar_url"),
                )
        except Exception:
            logger.exception("Failed to sync login user to profiles")

    return AuthResponse(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        expires_in=data.get("expires_in", 0),
        user=user_data,
    )


@app.post("/api/auth/refresh", response_model=AuthResponse)
async def refresh_token(body: RefreshRequest):
    """Exchange a refresh token for a new access token via Supabase Auth."""
    _ensure_supabase_configured()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "refresh_token"},
            headers=_supabase_auth_headers(),
            json={
                "refresh_token": body.refresh_token,
            },
        )

    data = resp.json()

    if resp.status_code >= 400:
        detail = (
            data.get("error_description")
            or data.get("msg")
            or data.get("message")
            or str(data)
        )
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return AuthResponse(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        expires_in=data.get("expires_in", 0),
        user=data.get("user"),
    )


# ─────────────────────────────────────────────
# Routes — User
# ─────────────────────────────────────────────


@app.get("/api/me", response_model=ProfileOut)
async def me(user: CurrentUser):
    """Return the authenticated user's profile.

    The profile is created/updated by the get_current_user dependency
    (via db.upsert_user) so we can return the user dict directly —
    no separate DB lookup needed.
    """
    return {
        "id": str(user["id"]),
        "email": user.get("email", ""),
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "created_at": user.get("created_at"),
    }


# ─────────────────────────────────────────────
# Routes — Calendars
# ─────────────────────────────────────────────


@app.get("/api/calendars", response_model=list[CalendarOut])
async def list_calendars(user: CurrentUser):
    """List all iCal calendars for the authenticated user."""
    return db.list_calendars(user["id"])


@app.post("/api/calendars", response_model=CalendarOut, status_code=201)
async def add_calendar(body: CalendarCreate, user: CurrentUser):
    """Add a new iCal calendar for the authenticated user."""
    cal = db.add_calendar(
        user_id=user["id"],
        name=body.name,
        ical_url=body.ical_url,
    )
    if not cal:
        raise HTTPException(status_code=500, detail="Failed to save calendar.")
    return cal


@app.delete("/api/calendars/{calendar_id}", status_code=204)
async def delete_calendar(calendar_id: _uuid.UUID, user: CurrentUser):
    """Delete one of the authenticated user's calendars."""
    ok = db.delete_calendar(user_id=user["id"], calendar_id=calendar_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Calendar not found.")


# ─────────────────────────────────────────────
# Routes — Interventions
# ─────────────────────────────────────────────


@app.get("/api/interventions", response_model=InterventionListResponse)
async def list_interventions(
    user: CurrentUser,
    domain: str | None = None,
    intervened_only: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    """List the authenticated user's intervention history.

    Optional query params:
      - **domain**: filter by website domain (e.g. `skyscanner.net`)
      - **intervened_only**: if `true`, only return analyses where a risk was flagged
      - **limit** / **offset**: pagination (defaults 50 / 0)
    """
    items, total = db.list_interactions(
        user_id=user["id"],
        domain=domain,
        intervened_only=intervened_only,
        limit=min(limit, 200),
        offset=offset,
    )
    return InterventionListResponse(
        items=[InterventionOut(**i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/api/interventions/stats", response_model=InterventionStats)
async def intervention_stats(user: CurrentUser):
    """Return aggregate statistics across all interventions for the
    authenticated user — total analyses, money saved, per-domain breakdown, etc."""
    return db.get_interaction_stats(user["id"])


@app.get("/api/interventions/{intervention_id}", response_model=InterventionOut)
async def get_intervention(intervention_id: _uuid.UUID, user: CurrentUser):
    """Return a single intervention record by ID."""
    record = db.get_interaction(user_id=user["id"], interaction_id=intervention_id)
    if not record:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    return record


@app.put("/api/interventions/{intervention_id}/feedback", status_code=204)
async def update_intervention_feedback_endpoint(
    intervention_id: _uuid.UUID, body: dict[str, bool], user: CurrentUser
):
    """Update the feedback boolean for an intervention.

    Expects a JSON body like: {"feedback": true}
    Returns 204 No Content on success, 404 if the interaction is not found,
    or 422 for invalid input.
    """
    # Validate body shape
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=422,
            detail="Request body must be a JSON object with a boolean 'feedback' field.",
        )
    feedback_val = body.get("feedback")
    if not isinstance(feedback_val, bool):
        raise HTTPException(
            status_code=422,
            detail="Request body must include a boolean 'feedback' field.",
        )

    # Attempt to update the interaction (scoped to the authenticated user)
    ok = db.update_interaction_feedback(
        user_id=user["id"], interaction_id=intervention_id, feedback=feedback_val
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="Intervention not found or not owned by user."
        )
    # 204 No Content — return nothing
    return None


# ─────────────────────────────────────────────
# Routes — Email (Gmail) Integration
# ─────────────────────────────────────────────


@app.post("/api/email/connect", response_model=EmailStatusOut, status_code=201)
async def connect_email(body: EmailConnectRequest, user: CurrentUser):
    """Connect a Gmail account by storing the Google OAuth tokens.

    The frontend should obtain a Google OAuth access token (and ideally a
    refresh token) via Supabase Auth or a direct OAuth flow, then POST
    them here.
    """
    user_id = user["id"]

    # Resolve the email address from the token
    email_address = await gmail.resolve_email_address(body.provider_token)

    conn = db.upsert_email_connection(
        user_id=user_id,
        access_token=body.provider_token,
        refresh_token=body.provider_refresh_token,
        email_address=email_address,
    )
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to save email connection.")

    logger.info(
        "Email connected | user=%s | email=%s", user_id, email_address or "unknown"
    )
    return EmailStatusOut(
        connected=True,
        provider=conn.get("provider", "google"),
        email_address=conn.get("email_address"),
        has_refresh_token=conn.get("has_refresh_token", False),
        connected_at=conn.get("created_at"),
    )


@app.get("/api/email/status", response_model=EmailStatusOut)
async def email_status(user: CurrentUser):
    """Check whether the authenticated user has a Gmail connection."""
    conn = db.get_email_connection(user["id"])
    if not conn:
        return EmailStatusOut(connected=False)
    return EmailStatusOut(
        connected=True,
        provider=conn.get("provider", "google"),
        email_address=conn.get("email_address"),
        has_refresh_token=conn.get("has_refresh_token", False),
        connected_at=conn.get("created_at"),
    )


@app.delete("/api/email/disconnect", status_code=204)
async def disconnect_email(user: CurrentUser):
    """Remove the Gmail connection for the authenticated user."""
    ok = db.delete_email_connection(user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="No email connection found.")
    logger.info("Email disconnected | user=%s", user["id"])


@app.get("/api/email/receipts", response_model=EmailReceiptsOut)
async def email_receipts(user: CurrentUser, lookback_days: int = 90):
    """Fetch purchase receipts from the user's connected Gmail.

    Uses LLM-based extraction to parse email subjects/snippets into
    structured receipt data (merchant, item, amount, currency, date).
    """
    user_id = str(user["id"])
    conn = db.get_email_connection(user["id"])
    if not conn:
        raise HTTPException(
            status_code=404, detail="No email connection. Connect Gmail first."
        )

    items = await gmail.fetch_email_receipts(user_id, lookback_days=lookback_days)
    return EmailReceiptsOut(items=items, count=len(items), source="gmail")


@app.get("/api/email/flights", response_model=EmailReceiptsOut)
async def email_flights(user: CurrentUser, lookback_days: int = 180):
    """Fetch flight booking confirmations from the user's connected Gmail.

    Uses LLM-based extraction to parse email subjects/snippets into
    structured flight data (airline, flight_number, airports, dates, price).
    """
    user_id = str(user["id"])
    conn = db.get_email_connection(user["id"])
    if not conn:
        raise HTTPException(
            status_code=404, detail="No email connection. Connect Gmail first."
        )

    items = await gmail.fetch_email_flights(user_id, lookback_days=lookback_days)
    return EmailReceiptsOut(items=items, count=len(items), source="gmail")


# ─────────────────────────────────────────────
# Routes — Analyze
# ─────────────────────────────────────────────


@app.post("/api/analyze", response_model=AgentResponse)
async def analyze_intent(req: IntentRequest, user: CurrentUser):
    """Receive an intent from the Chrome Extension, run the LangGraph
    agent pipeline, and return a risk assessment with economics."""

    user_id = str(user["id"])

    logger.info(
        "analyze_intent | user=%s | domain=%s | type=%s",
        user_id,
        req.domain,
        req.intent.get("type", "unknown"),
    )

    initial_state: AgentState = {
        "user_id": user_id,
        "domain": req.domain,
        "intent": req.intent,
        "requires_calendar": False,
        "requires_bank": False,
        "requires_purchase_history": False,
        "calendar_events": [],
        "bank_transactions": [],
        "purchase_history": [],
        "risk_factors": [],
        "intervention_message": None,
        "compute_cost": 0.0,
        "money_saved": 0.0,
        "platform_fee": 0.0,
        "hour_of_day": 12,
        "stored": False,
    }

    config = cast(RunnableConfig, {"configurable": {"thread_id": user_id}})

    try:
        final_state = await _agent.ainvoke(initial_state, config=config)
    except Exception:
        logger.exception("Agent pipeline failed for user=%s", user_id)
        raise HTTPException(
            status_code=500,
            detail="The agent pipeline encountered an internal error.",
        )

    risk_factors = final_state.get("risk_factors", [])

    # The canonical interaction id must come from the server (DB).
    # Prefer the id exposed by the storage node; if it's missing, attempt to
    # persist the interaction now. If persistence fails or no id is returned,
    # surface a clear 500 error so the client knows the operation did not
    # complete successfully.
    interaction_id = final_state.get("interaction_id")

    if not interaction_id:
        if user_id:
            try:
                store_res = db.store_interaction(
                    user_id=user_id,
                    domain=req.domain,
                    intent=req.intent,
                    risk_factors=risk_factors,
                    intervention_message=final_state.get("intervention_message"),
                    economics={
                        "compute_cost": final_state.get("compute_cost"),
                        "money_saved": final_state.get("money_saved"),
                        "platform_fee": final_state.get("platform_fee"),
                        "hour_of_day": final_state.get("hour_of_day"),
                    },
                    title=None,
                )
            except Exception:
                logger.exception(
                    "analyze_intent | store_interaction failed for user=%s", user_id
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to persist interaction to the server.",
                )
            if not store_res or not store_res.get("id"):
                # DB did not return an id — treat as failure
                logger.error(
                    "analyze_intent | store_interaction returned no id user=%s res=%r",
                    user_id,
                    store_res,
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to persist interaction to the server.",
                )
            interaction_id = store_res.get("id")
        else:
            # No authenticated user — cannot persist an interaction
            logger.error("analyze_intent | no user_id available to persist interaction")
            raise HTTPException(
                status_code=500,
                detail="No user_id available; cannot persist interaction.",
            )

    # Coerce the DB-provided id into a UUID object for the response schema.
    try:
        id_val = _uuid.UUID(interaction_id)
    except Exception:
        logger.exception(
            "analyze_intent | invalid interaction id from DB: %r", interaction_id
        )
        raise HTTPException(
            status_code=500, detail="Invalid interaction id returned by the server."
        )

    return AgentResponse(
        id=id_val,
        is_safe=len(risk_factors) == 0,
        intervention_message=final_state.get("intervention_message"),
        risk_factors=risk_factors,
        domain=req.domain,
        economics=EconomicsDetail(
            compute_cost=final_state.get("compute_cost"),
            money_saved=final_state.get("money_saved"),
            platform_fee=final_state.get("platform_fee"),
        ),
    )


# ─────────────────────────────────────────────
# Routes — Admin
# ─────────────────────────────────────────────


@app.post("/api/admin/sync-profiles")
async def admin_sync_profiles(user: CurrentUser):
    """Bulk-sync every Supabase Auth user into the local profiles table.

    This is an admin-only endpoint useful for:
    - One-off migration to reconcile auth ↔ profiles UUID mismatches.
    - Periodic reconciliation to catch any drift.

    Requires a valid authenticated session (any logged-in user can
    trigger it for now — restrict to admin roles in production).
    """
    logger.info("admin_sync_profiles triggered by user=%s", user["id"])
    result = sync_all_profiles()
    return result
