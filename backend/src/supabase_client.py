"""Supabase client singleton for admin auth operations.

Provides a cached Supabase client using the service-role key so the
backend can query and manage users in auth.users.  The key function
is ``sync_profile_from_auth`` which pulls canonical user data from
Supabase Auth and upserts it into the local ``profiles`` table,
guaranteeing that ``profiles.id == auth.users.id`` always holds.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from supabase import Client, create_client

from src.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────

_client: Client | None = None


def get_supabase_client() -> Client | None:
    """Return a cached Supabase client (service-role).

    Returns ``None`` when the required env vars are missing so callers
    can degrade gracefully.
    """
    global _client
    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning(
            "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — "
            "Supabase admin client unavailable."
        )
        return None

    _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    logger.info("Supabase admin client initialised (%s)", SUPABASE_URL)
    return _client


# ─────────────────────────────────────────────
# Auth → Profile sync
# ─────────────────────────────────────────────


def get_auth_user(user_id: _uuid.UUID | str) -> dict[str, Any] | None:
    """Fetch a single user from Supabase Auth (admin API).

    Returns a plain dict with id, email, user_metadata, created_at etc.
    or ``None`` on failure / missing client.
    """
    client = get_supabase_client()
    if client is None:
        return None

    uid = str(user_id)
    try:
        resp = client.auth.admin.get_user_by_id(uid)
        if resp and resp.user:
            u = resp.user
            return {
                "id": str(u.id),
                "email": u.email or "",
                "user_metadata": u.user_metadata or {},
                "created_at": str(u.created_at) if u.created_at else None,
            }
        return None
    except Exception:
        logger.exception("get_auth_user failed uid=%s", uid)
        return None


def sync_profile_from_auth(user_id: _uuid.UUID | str) -> dict[str, Any] | None:
    """Pull canonical user data from Supabase Auth and upsert into profiles.

    This is the **only** path that should write to the ``profiles`` table.
    It guarantees ``profiles.id == auth.users.id`` because the UUID comes
    directly from the auth provider, not from JWT claims or client input.

    Returns the upserted profile dict, or ``None`` on failure.
    """
    from src import db  # deferred to avoid circular imports

    auth_user = get_auth_user(user_id)
    if auth_user is None:
        logger.warning(
            "sync_profile_from_auth: could not fetch auth user %s — "
            "falling back to db.upsert_user with id only",
            user_id,
        )
        # Graceful degradation: if Supabase SDK is unavailable we still
        # create/update the profile row with whatever we have.
        return None

    uid = _uuid.UUID(auth_user["id"])
    email = auth_user.get("email", "")
    meta = auth_user.get("user_metadata", {})
    name = meta.get("full_name") or meta.get("name")
    avatar_url = meta.get("avatar_url")

    profile = db.upsert_user(
        user_id=uid,
        email=email,
        name=name,
        avatar_url=avatar_url,
    )

    if profile and profile.get("created_at"):
        logger.debug("sync_profile_from_auth: synced user %s (%s)", uid, email)
    else:
        logger.warning(
            "sync_profile_from_auth: upsert_user returned incomplete for %s", uid
        )

    return profile


def sync_all_profiles() -> dict[str, Any]:
    """Bulk-sync every auth user into the local profiles table.

    Useful as a one-off migration or periodic reconciliation job.
    Returns a summary dict with counts.
    """
    from src import db  # deferred to avoid circular imports

    client = get_supabase_client()
    if client is None:
        return {"error": "Supabase client not available", "synced": 0, "failed": 0}

    synced = 0
    failed = 0
    skipped = 0
    errors: list[str] = []

    try:
        page = 1
        per_page = 100
        while True:
            resp = client.auth.admin.list_users(page=page, per_page=per_page)
            users = resp if isinstance(resp, list) else getattr(resp, "users", []) or []

            if not users:
                break

            for u in users:
                uid_str = str(u.id)
                email: str = u.email or ""

                if not uid_str:
                    skipped += 1
                    continue

                try:
                    uid = _uuid.UUID(uid_str)
                    meta: dict[str, Any] = u.user_metadata or {}

                    result = db.upsert_user(
                        user_id=uid,
                        email=email,
                        name=meta.get("full_name") or meta.get("name"),
                        avatar_url=meta.get("avatar_url"),
                    )
                    if result and result.get("created_at"):
                        synced += 1
                    else:
                        failed += 1
                        errors.append(f"{uid_str}: upsert returned incomplete")
                except Exception as exc:
                    failed += 1
                    errors.append(f"{uid_str}: {exc}")

            if len(users) < per_page:
                break
            page += 1

    except Exception:
        logger.exception("sync_all_profiles: failed to list auth users")
        return {
            "error": "Failed to list auth users",
            "synced": synced,
            "failed": failed,
            "skipped": skipped,
            "errors": errors[:20],
        }

    summary: dict[str, Any] = {
        "synced": synced,
        "failed": failed,
        "skipped": skipped,
    }
    if errors:
        summary["errors"] = errors[:20]  # cap for readability

    logger.info("sync_all_profiles complete: %s", summary)
    return summary
