"""Verify Supabase access tokens by asking the official Auth user endpoint."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import Header, HTTPException

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)


def auth_settings() -> tuple[str, str]:
    project_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    public_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not project_url.startswith("https://") or not public_key or "your_" in project_url or "your_" in public_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured. Add the Supabase URL and public key to the local .env file.")
    return project_url, public_key


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Return identity only when Supabase confirms the bearer token is valid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to access this workspace.")
    project_url, public_key = auth_settings()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Your sign-in session is invalid. Please sign in again.")
    request = Request(
        f"{project_url}/auth/v1/user",
        headers={"apikey": public_key, "Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=6) as response:
            user = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in (401, 403):
            raise HTTPException(status_code=401, detail="Your sign-in session is invalid or expired. Please sign in again.") from None
        raise HTTPException(status_code=503, detail="Supabase authentication is temporarily unavailable.") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="Could not verify your sign-in. Check your connection and try again.") from None

    user_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Supabase did not return a valid signed-in user.")
    # Store only the provider's verified ID; Supabase remains the account source of truth.
    from backend import course_store
    course_store.register_user(user_id)
    return {"id": user_id, "email": str(user.get("email") or "")}
