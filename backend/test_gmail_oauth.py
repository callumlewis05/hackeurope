"""Standalone Google OAuth test script.

Opens your browser → Google consent screen → captures the auth code via a
tiny local HTTP server → exchanges it for access + refresh tokens → stores
them in the email_connections table so the pipeline can use Gmail data.

Usage:
    python test_gmail_oauth.py

Prerequisites:
    1. GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET set in .env
    2. In Google Cloud Console → Credentials → your OAuth client:
       Add http://localhost:8976/callback to "Authorized redirect URIs"
    3. The database must be reachable (DATABASE_URL in .env)
    4. Gmail API must be enabled in Google Cloud Console
    5. Your Google account must be added as a test user in the OAuth consent screen
"""

import http.server
import sys
import threading
import urllib.parse
import webbrowser

import httpx
from dotenv import load_dotenv

load_dotenv()

from src import db
from src.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

REDIRECT_PORT = 8976
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

# ─────────────────────────────────────────────
# Tiny callback server
# ─────────────────────────────────────────────

_auth_code = None
_auth_error = None
_server_done = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth redirect and extracts the auth code."""

    def do_GET(self):
        global _auth_code, _auth_error

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            body = (
                "<html><body>"
                "<h2>&#10003; Authorization successful!</h2>"
                "<p>You can close this tab and go back to the terminal.</p>"
                "</body></html>"
            )
            self.send_response(200)
        elif "error" in params:
            _auth_error = params["error"][0]
            body = (
                "<html><body>"
                "<h2>&#10007; Authorization failed</h2>"
                "<p>Error: " + str(_auth_error) + "</p>"
                "</body></html>"
            )
            self.send_response(400)
        else:
            body = "<html><body><p>Unexpected request.</p></body></html>"
            self.send_response(400)

        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())
        _server_done.set()

    def log_message(self, format, *args):
        pass


def _run_callback_server():
    """Start a one-shot HTTP server to receive the OAuth callback."""
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.timeout = 120
    while not _server_done.is_set():
        server.handle_request()
    server.server_close()


# ─────────────────────────────────────────────
# OAuth flow
# ─────────────────────────────────────────────


def build_auth_url():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )


def exchange_code(code):
    """Exchange the auth code for access + refresh tokens."""
    resp = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print("")
        print("ERROR: Token exchange failed: " + str(resp.status_code))
        print(resp.text)
        sys.exit(1)
    return resp.json()


def get_email(access_token):
    """Resolve the email address from the access token."""
    resp = httpx.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": "Bearer " + access_token},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json().get("email")
    return None


def get_user_id_by_email(email):
    """Find the user in profiles by email."""
    from sqlmodel import select

    from src.db import Profile, get_session

    with get_session() as session:
        stmt = select(Profile).where(Profile.email == email)
        profile = session.exec(stmt).first()
        if profile:
            return profile.id
    return None


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────


def main():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        print("ERROR: GOOGLE_CLIENT_ID and/or GOOGLE_CLIENT_SECRET not set in .env")
        sys.exit(1)

    print("=" * 60)
    print("  Google OAuth Test -- Gmail Integration")
    print("=" * 60)
    print("")
    print("  Client ID:    " + GOOGLE_CLIENT_ID[:25] + "...")
    print("  Redirect URI: " + REDIRECT_URI)
    print("  Scopes:       " + ", ".join(SCOPES))
    print("")
    print("  Make sure you have added this EXACT redirect URI")
    print("  in Google Cloud Console -> Credentials -> OAuth client:")
    print("    " + REDIRECT_URI)
    print("")

    # Start callback server in background
    server_thread = threading.Thread(target=_run_callback_server, daemon=True)
    server_thread.start()

    # Open browser
    auth_url = build_auth_url()
    print("Opening browser for Google sign-in...")
    print("  (If it does not open, visit this URL manually:)")
    print("  " + auth_url)
    print("")
    webbrowser.open(auth_url)

    # Wait for callback
    print("Waiting for authorization (up to 2 minutes)...")
    _server_done.wait(timeout=120)

    if _auth_error:
        print("")
        print("ERROR: Authorization error: " + str(_auth_error))
        sys.exit(1)

    if not _auth_code:
        print("")
        print("ERROR: No authorization code received (timed out?)")
        sys.exit(1)

    print("")
    print("Got auth code: " + _auth_code[:20] + "...")

    # Exchange for tokens
    print("")
    print("Exchanging code for tokens...")
    tokens = exchange_code(_auth_code)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    print("  Access token:  " + access_token[:25] + "...")
    if refresh_token:
        print("  Refresh token: received")
    else:
        print("  Refresh token: NOT received")
    print("  Expires in:    " + str(expires_in) + "s")

    # Get email
    print("")
    print("Resolving email address...")
    email = get_email(access_token)
    if email:
        print("  Email: " + email)
    else:
        print("  WARNING: Could not resolve email (will store without it)")

    # Find user in DB
    print("")
    print("Looking up user in profiles table...")
    user_id = None
    if email:
        user_id = get_user_id_by_email(email)

    if not user_id:
        from sqlmodel import select

        from src.db import Profile, get_session

        with get_session() as session:
            profiles = session.exec(select(Profile)).all()
            if profiles:
                print("")
                print("  Available users:")
                for i, p in enumerate(profiles):
                    print(
                        "    [" + str(i) + "] " + p.email + " (id: " + str(p.id) + ")"
                    )
                print("")
                choice = input("  Enter user number to connect Gmail to: ").strip()
                try:
                    idx = int(choice)
                    user_id = profiles[idx].id
                    email = email or profiles[idx].email
                    print("  Selected: " + profiles[idx].email)
                except (ValueError, IndexError):
                    print("  ERROR: Invalid choice")
                    sys.exit(1)
            else:
                print(
                    "  ERROR: No users in profiles table. Sign up first via /api/auth/signup"
                )
                sys.exit(1)
    else:
        print("  Found user: " + str(user_id))

    # Store tokens
    print("")
    print("Storing tokens in email_connections...")
    from datetime import datetime, timedelta

    conn = db.upsert_email_connection(
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        email_address=email,
        token_expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
    )

    if conn:
        print("  Stored! Connection ID: " + conn["id"])
    else:
        print("  ERROR: Failed to store tokens")
        sys.exit(1)

    # Quick test: search Gmail
    print("")
    print("Quick test -- searching Gmail for recent receipts...")
    try:
        resp = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": "Bearer " + access_token},
            params={
                "q": "subject:(receipt OR order OR confirmation) -label:spam",
                "maxResults": 5,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            messages = resp.json().get("messages", [])
            print(
                "  Found "
                + str(len(messages))
                + " receipt-related emails (showing up to 5)"
            )
            for m in messages[:5]:
                msg_resp = httpx.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                    + m["id"],
                    headers={"Authorization": "Bearer " + access_token},
                    params={"format": "metadata", "metadataHeaders": ["Subject"]},
                    timeout=10,
                )
                if msg_resp.status_code == 200:
                    headers = msg_resp.json().get("payload", {}).get("headers", [])
                    subject = "(no subject)"
                    for h in headers:
                        if h["name"] == "Subject":
                            subject = h["value"]
                            break
                    if len(subject) > 80:
                        subject = subject[:80] + "..."
                    print("    -> " + subject)
        elif resp.status_code == 403:
            print("  WARNING: Gmail API not enabled. Enable it at:")
            print(
                "    https://console.developers.google.com/apis/api/gmail.googleapis.com/overview"
            )
        else:
            print(
                "  WARNING: Gmail search returned "
                + str(resp.status_code)
                + ": "
                + resp.text[:200]
            )
    except Exception as e:
        print("  WARNING: Gmail test failed: " + str(e))

    # Search for flight-related emails too
    print("")
    print("Quick test -- searching Gmail for flight bookings...")
    try:
        resp = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": "Bearer " + access_token},
            params={
                "q": "subject:(flight OR booking OR itinerary OR boarding OR e-ticket) -label:spam",
                "maxResults": 5,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            messages = resp.json().get("messages", [])
            print(
                "  Found "
                + str(len(messages))
                + " flight-related emails (showing up to 5)"
            )
            for m in messages[:5]:
                msg_resp = httpx.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                    + m["id"],
                    headers={"Authorization": "Bearer " + access_token},
                    params={"format": "metadata", "metadataHeaders": ["Subject"]},
                    timeout=10,
                )
                if msg_resp.status_code == 200:
                    headers = msg_resp.json().get("payload", {}).get("headers", [])
                    subject = "(no subject)"
                    for h in headers:
                        if h["name"] == "Subject":
                            subject = h["value"]
                            break
                    if len(subject) > 80:
                        subject = subject[:80] + "..."
                    print("    -> " + subject)
        elif resp.status_code == 403:
            print("  WARNING: Gmail API not enabled.")
        else:
            print("  WARNING: Gmail search returned " + str(resp.status_code))
    except Exception as e:
        print("  WARNING: Gmail test failed: " + str(e))

    print("")
    print("=" * 60)
    print("  Gmail integration is ready!")
    print("")
    print("  The pipeline will now automatically pull email data")
    print("  when analyzing intents via POST /api/analyze.")
    print("")
    print("  You can also test directly:")
    print("    GET /api/email/status")
    print("    GET /api/email/receipts")
    print("    GET /api/email/flights")
    print("=" * 60)


if __name__ == "__main__":
    main()
