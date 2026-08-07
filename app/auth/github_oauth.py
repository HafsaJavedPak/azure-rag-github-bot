# app/auth/github_oauth.py

from urllib.parse import urlencode

import requests

from app.config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_OAUTH_REDIRECT_URI

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"


def build_authorize_url(state: str) -> str:
    """
    Builds the URL that starts the OAuth flow — the user is redirected here,
    sees GitHub's consent screen, and (if they approve) GitHub redirects
    them back to our callback with a short-lived code.

    state is a random string generated per login attempt and re-checked on
    callback — CSRF protection, proving the callback actually came from a
    login we initiated rather than an attacker tricking a user into
    completing someone else's OAuth flow.
    """
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_OAUTH_REDIRECT_URI,
        "scope": "repo",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> str:
    """
    Exchanges the short-lived code from the callback for a real access
    token. client_secret only ever appears here, server-side — it's never
    sent to or exposed in the browser, which is what makes it safe for the
    code itself to travel through the browser's URL.
    """
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": GITHUB_OAUTH_REDIRECT_URI,
        },
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        raise ValueError(f"GitHub token exchange failed: {data}")

    return data["access_token"]
